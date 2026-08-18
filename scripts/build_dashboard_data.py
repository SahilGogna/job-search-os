"""Compute aggregate dashboard data from the Applications tab.

Reads the Gmail-derived rows update_application_tracker.py already wrote
(Company | Role | Status | Last Updated | Gmail Thread Link | Snippet), and
produces a single JSON summary: totals by status, and two flagged lists
(needs follow-up, needs a thank-you). Pure computation, no Gmail access, no
LLM calls -- this is data plumbing, not judgment. Claude reads the JSON this
writes and turns it into the actual dashboard page; this script's job ends
at the JSON.

This is purely a Gmail-derived view -- it never reads or references the
job-search Sheet tabs. The two are intentionally independent.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from push_to_sheets import load_credentials_from_env, open_sheet

APPLICATIONS_HEADERS = ["Company", "Role", "Status", "Last Updated", "Gmail Thread Link", "Snippet"]
FIELD_ORDER = ["company", "role", "status", "last_updated", "thread_link", "snippet"]

IN_PROGRESS_STATUSES = {"applied", "under review", "assessment"}
FOLLOW_UP_ELIGIBLE_STATUSES = {"applied", "under review"}
THANK_YOU_STATUS = "interview"

DEFAULT_FOLLOW_UP_AFTER_DAYS = 7


def _row_value(row: list, idx: int) -> str:
    return row[idx] if idx < len(row) else ""


def rows_as_dicts(values: list[list]) -> list[dict]:
    """Applications tab rows -> list of field dicts. Tolerates a header row
    that doesn't exactly match (older/newer schema) by mapping positionally
    against the header actually present, not assuming APPLICATIONS_HEADERS."""
    if not values:
        return []
    header = values[0]
    out = []
    for row in values[1:]:
        record = {}
        for idx, col_name in enumerate(header):
            record[col_name] = _row_value(row, idx)
        out.append(record)
    return out


def parse_last_updated(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def days_since(dt: datetime | None, now: datetime) -> int | None:
    if dt is None:
        return None
    return max(0, (now - dt).days)


def compute_dashboard(rows: list[dict], follow_up_after_days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)

    totals = {
        "total_tracked": 0,
        "in_progress": 0,
        "interviewed": 0,
        "offers": 0,
        "rejected": 0,
        "withdrawn": 0,
        "other": 0,
    }
    needs_follow_up = []
    needs_thank_you = []

    for row in rows:
        company = row.get("Company", "")
        role = row.get("Role", "")
        status_raw = row.get("Status", "")
        status = status_raw.strip().lower()
        last_updated_raw = row.get("Last Updated", "")
        thread_link = row.get("Gmail Thread Link", "")

        if not company and not role and not status:
            continue  # skip blank rows

        totals["total_tracked"] += 1
        if status in IN_PROGRESS_STATUSES:
            totals["in_progress"] += 1
        elif status == "interview":
            totals["interviewed"] += 1
        elif status == "offer":
            totals["offers"] += 1
        elif status == "rejected":
            totals["rejected"] += 1
        elif status == "withdrawn":
            totals["withdrawn"] += 1
        else:
            totals["other"] += 1

        last_updated_dt = parse_last_updated(last_updated_raw)
        age_days = days_since(last_updated_dt, now)

        if status in FOLLOW_UP_ELIGIBLE_STATUSES and age_days is not None and age_days >= follow_up_after_days:
            needs_follow_up.append(
                {
                    "company": company,
                    "role": role,
                    "status": status_raw,
                    "last_updated": last_updated_raw,
                    "days_since_update": age_days,
                    "thread_link": thread_link,
                }
            )

        if status == THANK_YOU_STATUS:
            needs_thank_you.append(
                {
                    "company": company,
                    "role": role,
                    "status": status_raw,
                    "last_updated": last_updated_raw,
                    "thread_link": thread_link,
                }
            )

    needs_follow_up.sort(key=lambda r: r["days_since_update"], reverse=True)

    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "follow_up_after_days": follow_up_after_days,
        "totals": totals,
        "needs_follow_up": needs_follow_up,
        "needs_thank_you": needs_thank_you,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tab-name", default="Applications")
    parser.add_argument("--follow-up-after-days", type=int, default=DEFAULT_FOLLOW_UP_AFTER_DAYS)
    parser.add_argument("--out", required=True, type=Path)
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

    spreadsheet = open_sheet(creds, sheet_id)
    try:
        ws = spreadsheet.worksheet(args.tab_name)
    except Exception as exc:  # noqa: BLE001 -- gspread.WorksheetNotFound or similar
        print(
            f"ERROR: tab '{args.tab_name}' not found. Run application-tracker's Gmail scan first. ({exc})",
            file=sys.stderr,
        )
        return 1

    values = ws.get_all_values()
    rows = rows_as_dicts(values)
    dashboard = compute_dashboard(rows, args.follow_up_after_days)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False))

    t = dashboard["totals"]
    print(
        f"Dashboard data: {t['total_tracked']} tracked "
        f"({t['in_progress']} in progress, {t['interviewed']} interviewed, {t['offers']} offers, "
        f"{t['rejected']} rejected, {t['withdrawn']} withdrawn, {t['other']} other), "
        f"{len(dashboard['needs_follow_up'])} need follow-up, {len(dashboard['needs_thank_you'])} need a thank-you "
        f"→ {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
