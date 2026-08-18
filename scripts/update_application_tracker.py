"""Upsert Gmail-derived application status rows into a dedicated Applications tab.

Reads a JSON list of {company, role, status, last_updated, thread_link, snippet}
-- written by the application-tracker skill after it reads and classifies Gmail
threads itself (this script does no classification) -- and upserts them into
--tab-name (default "Applications"), keyed by thread_link so re-scanning the
same thread updates its row in place instead of duplicating it.

This tab is separate from the date-based job-search tabs and is never touched
by push_to_sheets.py's merge logic. Reuses push_to_sheets.py's credential/sheet
helpers directly (same service account, same SHEET_ID) rather than duplicating
that logic -- run this from the repo root as `python scripts/update_application_tracker.py`
so `scripts/` is importable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from push_to_sheets import format_tab, get_or_create_tab, load_credentials_from_env, open_sheet

HEADERS = ["Company", "Role", "Status", "Last Updated", "Gmail Thread Link", "Snippet"]
FIELD_ORDER = ["company", "role", "status", "last_updated", "thread_link", "snippet"]


def _row_value(row: list, idx: int) -> str:
    return row[idx] if idx < len(row) else ""


def merge_rows(existing: list[list], new_field_rows: list[list]) -> list[list]:
    """Upsert by thread_link -- fresh classification wins on collision, same
    shape as push_to_sheets.py's merge_rows but keyed differently."""
    link_col = FIELD_ORDER.index("thread_link")
    updated_col = FIELD_ORDER.index("last_updated")

    by_link: dict[str, list] = {}
    order: list[str] = []
    if existing and existing[0] == HEADERS:
        for row in existing[1:]:
            key = _row_value(row, link_col)
            if key:
                by_link[key] = row
                order.append(key)

    for row in new_field_rows:
        key = _row_value(row, link_col)
        if not key:
            continue
        if key not in by_link:
            order.append(key)
        by_link[key] = row  # fresh classification wins

    merged = [by_link[key] for key in order]
    merged.sort(key=lambda r: _row_value(r, updated_col), reverse=True)
    return merged


def rows_from_updates(updates: list[dict]) -> list[list]:
    return [[str(row.get(field, "")) for field in FIELD_ORDER] for row in updates]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--updates", required=True, type=Path)
    parser.add_argument("--tab-name", default="Applications")
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

    updates = json.loads(args.updates.read_text())
    if not isinstance(updates, list):
        print("ERROR: --updates must be a JSON list", file=sys.stderr)
        return 1

    spreadsheet = open_sheet(creds, sheet_id)
    ws = get_or_create_tab(spreadsheet, args.tab_name, cols=len(HEADERS))

    existing = ws.get_all_values()
    new_field_rows = rows_from_updates(updates)
    merged = merge_rows(existing, new_field_rows)

    ws.clear()
    ws.update(values=[HEADERS] + merged, range_name="A1", value_input_option="USER_ENTERED")
    format_tab(spreadsheet, ws, num_rows=len(merged), num_cols=len(HEADERS))

    prior = max(0, len(existing) - 1) if existing and existing[0] == HEADERS else 0
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit#gid={ws.id}"
    print(f"Wrote {len(merged)} rows to tab '{args.tab_name}' (this scan: {len(new_field_rows)}, prior: {prior})")
    print(sheet_url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
