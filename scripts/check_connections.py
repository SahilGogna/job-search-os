"""Report the status of this project's connections without ever exposing a secret.

This is the ONLY sanctioned way to learn whether .env is set up correctly.
Claude must never read, cat, grep, or sed .env itself -- not to check whether a
key is present, not to mask values, not to "just verify." This script loads
.env inside its own process and emits nothing but a status word per key.

Nothing here prints a secret value, a fragment of one, or its length. Exception
text from the underlying libraries is deliberately NOT echoed either: a failed
Google Sheets call can embed the spreadsheet id in a URL, and a failed HTTP call
can embed whatever was in the request. Failures are classified into fixed,
hand-written messages instead.

Gmail is intentionally not checkable here: MCP connector tools aren't reachable
from a subprocess, so that check stays a direct `list_labels` tool call made by
the connections skill.

Exit code 0 only if every checked key is valid, 1 otherwise -- so callers can
branch without parsing this output.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

APIFY_WHOAMI_URL = "https://api.apify.com/v2/users/me"
REQUEST_TIMEOUT = 20

# Values shipped in example.env -- present in .env but meaningless.
PLACEHOLDERS = {
    "your_apify_api_token",
    "your_base64_encoded_service_account_json_key",
    "your_google_sheet_id",
}

VALID_SCOPES = ("apify", "sheets")


def _classify_presence(value: str | None) -> str | None:
    """Return a status string if the value is absent/placeholder, else None."""
    if value is None or not value.strip():
        return "missing"
    if value.strip().strip("\"'") in PLACEHOLDERS:
        return "missing (still the example.env placeholder)"
    return None


def check_apify() -> tuple[bool, str]:
    token = os.environ.get("APIFY_TOKEN")
    presence = _classify_presence(token)
    if presence:
        return False, f"APIFY_TOKEN: {presence}"

    try:
        # Bearer header, never a URL query param -- a token in the URL would end
        # up inside requests' exception messages and any log that records them.
        resp = requests.get(
            APIFY_WHOAMI_URL,
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return False, "APIFY_TOKEN: could not reach Apify (network error)"

    if resp.status_code == 200:
        return True, "APIFY_TOKEN: valid"
    if resp.status_code in (401, 403):
        return False, "APIFY_TOKEN: invalid (rejected by Apify -- wrong or revoked token)"
    return False, f"APIFY_TOKEN: invalid (Apify returned HTTP {resp.status_code})"


def check_sheets() -> tuple[bool, str]:
    """Validates JSON_KEY_BASE_64 and SHEET_ID together -- a successful open
    proves both are correct, and neither is useful without the other."""
    from push_to_sheets import load_credentials_from_env, open_sheet

    key_presence = _classify_presence(os.environ.get("JSON_KEY_BASE_64"))
    if key_presence:
        return False, f"JSON_KEY_BASE_64: {key_presence}"

    # The single most common way to get this key wrong is to paste the JSON file's
    # contents instead of storing its base64 form. That fails the same way a typo does,
    # so name it specifically -- the fix ("give the file's path") is completely
    # different from the fix for a corrupted blob. Checking the first character tells us
    # the shape without revealing anything about the value.
    if os.environ["JSON_KEY_BASE_64"].strip().strip("\"'").startswith("{"):
        return False, (
            "JSON_KEY_BASE_64: invalid (this is raw JSON, not base64 -- don't paste the "
            "key file's contents; give Claude the file's path instead and it will encode it)"
        )

    try:
        creds = load_credentials_from_env()
    except RuntimeError:
        # RuntimeError text names the env var and the parse failure, but we
        # classify rather than echo it, to stay strictly value-free.
        return False, "JSON_KEY_BASE_64: invalid (not valid base64, or not a service-account JSON key)"
    except Exception:  # noqa: BLE001
        return False, "JSON_KEY_BASE_64: invalid (could not build credentials from it)"

    # The service account's own email is not a secret -- it's the address the
    # candidate must share their sheet with, so surfacing it is useful.
    account = getattr(creds, "service_account_email", "unknown")

    sheet_presence = _classify_presence(os.environ.get("SHEET_ID"))
    if sheet_presence:
        return False, f"JSON_KEY_BASE_64: valid (service account: {account})\nSHEET_ID: {sheet_presence}"

    sheet_id = os.environ["SHEET_ID"].strip().strip("\"'")
    try:
        open_sheet(creds, sheet_id)
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if "SpreadsheetNotFound" in name:
            detail = "not found, or not shared with the service account above"
        elif "APIError" in name or "Forbidden" in name:
            detail = "permission denied -- share the sheet with the service account above as Editor"
        else:
            detail = f"could not open it ({name})"
        return False, f"JSON_KEY_BASE_64: valid (service account: {account})\nSHEET_ID: invalid ({detail})"

    return True, f"JSON_KEY_BASE_64: valid (service account: {account})\nSHEET_ID: valid"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scope",
        default="apify,sheets",
        help=f"comma-separated subset of {VALID_SCOPES} (Gmail is checked by the skill, not here)",
    )
    args = parser.parse_args()

    scopes = [s.strip().lower() for s in args.scope.split(",") if s.strip()]
    unknown = [s for s in scopes if s not in VALID_SCOPES]
    if unknown:
        print(
            f"ERROR: unknown scope(s) {unknown}; valid scopes are {list(VALID_SCOPES)}",
            file=sys.stderr,
        )
        return 2

    load_dotenv(REPO_ROOT / ".env")

    all_ok = True
    for scope in scopes:
        ok, message = check_apify() if scope == "apify" else check_sheets()
        print(message)
        all_ok = all_ok and ok

    print("ALL CONNECTIONS VALID" if all_ok else "SOME CONNECTIONS NEED ATTENTION")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
