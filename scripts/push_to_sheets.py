"""Append scored postings to a Google Sheet.

Opens the sheet identified by SHEET_ID, creates a tab named --tab-name
(defaults to today's UTC date), writes the header row plus data rows sorted by
Match Score descending, then bolds the header, freezes row 1, and applies a
basic filter over the used range.

Service account credentials come from the JSON_KEY_BASE_64 env var, which
holds a base64-encoded service account JSON key.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys
from datetime import date
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

HEADERS = [
    "Match Score",
    "Source",
    "Job Title",
    "Company",
    "Location",
    "Experience Required",
    "Seniority",
    "Employment Type",
    "Skills Matched",
    "Posted",
    "Applicants",
    "Job Description",
    "Apply Link",
    "Fetched At",
]

FIELD_ORDER = [
    "match_score",
    "source",
    "job_title",
    "company",
    "location",
    "experience_required",
    "seniority",
    "employment_type",
    "skills_matched",
    "posted",
    "applicants",
    "job_description",
    "apply_link",
    "fetched_at",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def load_credentials_from_env(env_var: str = "JSON_KEY_BASE_64") -> Credentials:
    encoded = os.environ.get(env_var)
    if not encoded:
        raise RuntimeError(f"{env_var} not set in environment")
    encoded = "".join(encoded.split())
    padding = (-len(encoded)) % 4
    if padding:
        encoded += "=" * padding
    try:
        decoded = base64.b64decode(encoded)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError(f"{env_var} is not valid base64: {exc}") from exc
    try:
        info = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{env_var} did not decode to valid JSON: {exc}") from exc
    return Credentials.from_service_account_info(info, scopes=SCOPES)


def open_sheet(creds: Credentials, sheet_id: str):
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def get_or_create_tab(spreadsheet, tab_name: str, cols: int):
    try:
        return spreadsheet.worksheet(tab_name)
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=cols)


def _row_value(row: list, idx: int) -> str:
    return row[idx] if idx < len(row) else ""


def merge_rows(existing: list[list], new_field_rows: list[list]) -> list[list]:
    """Union new rows with existing tab rows, keyed on apply_link. Fresh row wins.

    If the existing header doesn't match current HEADERS (schema drift), we
    discard existing data and treat the tab as empty — the caller wipes and
    rewrites from scratch.
    """
    link_col = FIELD_ORDER.index("apply_link")
    score_col = FIELD_ORDER.index("match_score")

    by_link: dict[str, list] = {}
    if existing and existing[0] == HEADERS:
        for row in existing[1:]:
            key = _row_value(row, link_col)
            if key:
                by_link[key] = row

    for row in new_field_rows:
        key = _row_value(row, link_col)
        if key:
            by_link[key] = row  # fresh row wins on collision

    merged = list(by_link.values())
    merged.sort(
        key=lambda r: int(_row_value(r, score_col)) if _row_value(r, score_col).isdigit() else 0,
        reverse=True,
    )
    return merged


def rows_from_scored(scored: list[dict]) -> list[list]:
    return [[str(row.get(field, "")) for field in FIELD_ORDER] for row in scored]


def format_tab(spreadsheet, ws, num_rows: int, num_cols: int) -> None:
    ws.freeze(rows=1)
    ws.format("1:1", {"textFormat": {"bold": True}})
    if num_rows >= 1:
        end_col_letter = gspread.utils.rowcol_to_a1(1, num_cols).rstrip("0123456789")
        end_row = num_rows + 1
        try:
            ws.set_basic_filter(f"A1:{end_col_letter}{end_row}")
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: could not apply basic filter: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scored-in", required=True, type=Path)
    parser.add_argument("--tab-name", default=None)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    sheet_id = os.environ.get("SHEET_ID")
    if not sheet_id:
        print("ERROR: SHEET_ID not set in environment", file=sys.stderr)
        return 1

    try:
        creds = load_credentials_from_env()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    scored = json.loads(args.scored_in.read_text())

    tab_name = args.tab_name or date.today().isoformat()
    spreadsheet = open_sheet(creds, sheet_id)
    ws = get_or_create_tab(spreadsheet, tab_name, cols=len(HEADERS))

    existing = ws.get_all_values()
    new_field_rows = rows_from_scored(scored)
    merged = merge_rows(existing, new_field_rows)

    ws.clear()
    ws.update(values=[HEADERS] + merged, range_name="A1", value_input_option="USER_ENTERED")
    format_tab(spreadsheet, ws, num_rows=len(merged), num_cols=len(HEADERS))

    prior = max(0, len(existing) - 1) if existing and existing[0] == HEADERS else 0
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={ws.id}"
    print(f"Wrote {len(merged)} rows to tab '{tab_name}' (this run: {len(new_field_rows)}, prior in tab: {prior})")
    print(sheet_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
