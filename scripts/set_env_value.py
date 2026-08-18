"""Write a single key into .env without the value passing through anything visible.

This is the ONLY sanctioned way to write .env. Claude must never construct an
Edit against .env directly -- doing so would require reading the whole file
first (exposing every other stored secret) just to build a valid match string.

Two input modes, both keeping the value out of the command line, because argv is
visible to anyone who can run `ps` and often lands in shell history:

    # value piped on stdin
    printf '%s' "$VALUE" | python scripts/set_env_value.py --key APIFY_TOKEN --stdin

    # a service-account JSON file, base64-encoded in-process
    python scripts/set_env_value.py --key JSON_KEY_BASE_64 --from-file-base64 key.json

The second mode exists specifically so the encoded credential never has to be
printed to a terminal and pasted -- the blob IS the credential.

Output is only ever "Set <KEY>". The file's contents are never echoed.

Scope note, stated honestly: a value the user types into chat is already in the
conversation -- that is inherent and not something this script can undo. What it
prevents is re-reading *stored* secrets, and exposing values via argv or shell
output.
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = REPO_ROOT / ".env"
EXAMPLE_ENV_PATH = REPO_ROOT / "example.env"


def read_lines() -> list[str]:
    if ENV_PATH.exists():
        return ENV_PATH.read_text().splitlines()
    if EXAMPLE_ENV_PATH.exists():
        # Seed from the template so the file keeps its documented shape.
        return EXAMPLE_ENV_PATH.read_text().splitlines()
    return []


def upsert(lines: list[str], key: str, value: str) -> list[str]:
    """Replace the line defining `key`, or append one. Every other line -- including
    comments, blanks, and other secrets -- is preserved byte-for-byte."""
    out = []
    replaced = False
    for line in lines:
        stripped = line.lstrip()
        if not stripped.startswith("#") and "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                if not replaced:
                    out.append(f"{key}={value}")
                    replaced = True
                continue  # drop any duplicate definitions of the same key
        out.append(line)
    if not replaced:
        out.append(f"{key}={value}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--stdin", action="store_true", help="read the value from stdin")
    group.add_argument(
        "--from-file-base64",
        type=Path,
        metavar="PATH",
        help="read this file and store its base64 encoding (for service-account JSON keys)",
    )
    args = parser.parse_args()

    if args.stdin:
        value = sys.stdin.read().strip()
        if not value:
            print("ERROR: no value received on stdin", file=sys.stderr)
            return 1
    else:
        path = args.from_file_base64
        if not path.exists():
            print(f"ERROR: file not found: {path}", file=sys.stderr)
            return 1
        value = base64.b64encode(path.read_bytes()).decode("ascii")

    lines = upsert(read_lines(), args.key, value)
    ENV_PATH.write_text("\n".join(lines).rstrip("\n") + "\n")
    ENV_PATH.chmod(0o600)  # owner-only, in case it was created fresh here

    print(f"Set {args.key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
