---
name: application-tracker
description: Use when the candidate wants to know the status of their job applications — "check my applications", "any updates on my applications", "scan my inbox for job updates", "application status", "what's happened with my applications", "update my dashboard". Also invoked by the onboard skill's Gmail opt-in step. Read-only scan of Gmail for job-application-related emails (confirmations, assessments, interviews, offers, rejections), classified and written to a dedicated "Applications" tab, then aggregated into a private dashboard (counts + flagged follow-ups/thank-yous) published as a Claude Artifact. Does not modify Gmail in any way — no labels, no message/thread mutation. Entirely independent of the job-search Sheet — this dashboard never references job postings, only Gmail-derived application status.
---

## Ground rule: read-only, always

This skill **never** calls `label_thread`, `label_message`, `create_label`, `apply_sensitive_message_label`, `apply_sensitive_thread_label`, `unlabel_message`, or any other Gmail mutation tool. It only reads: `search_threads` and `get_thread`. This is an explicit, non-negotiable constraint the candidate set — the inbox itself is never touched, only read and summarized into the sheet.

## Step 1 — Determine scan window

Check for `archives/gmail_scan_state.json`:
```json
{"last_scanned_at": "2026-08-10T14:00:00Z"}
```
If present, use `after:<date from last_scanned_at>` in the search query. If absent (first run), scan the last 90 days (`newer_than:90d`) — **except** when this skill is being invoked from `onboard`'s Gmail opt-in step, which explicitly requests a **30-day** window for that first scan instead. Use whichever window the invoker specifies; 90 days is only the standalone default.

## Step 2 — Search Gmail broadly

The goal is *all* applied jobs and their status — not restricted to companies already in a job-search sheet tab. Use `search_threads` with a broad query combining application-signal language and known ATS/recruiting sender domains. Something like (adapt/refine based on what actually comes back — this is a starting point, not a fixed template):

```
newer_than:90d (application OR interview OR "thank you for applying" OR assessment OR offer OR unfortunately OR "next steps" OR position OR candidacy) OR from:(myworkday.com OR greenhouse.io OR lever.co OR smartrecruiters.com OR icims.com OR taleo.net OR successfactors.com OR workable.com)
```

Paginate with `pageToken` if there are more results than one page returns. Use `THREAD_VIEW_MINIMAL` (the default) to get subject + snippet cheaply before deciding which threads are worth reading in full.

## Step 3 — Read and classify each candidate thread

For each thread that looks plausibly job-related from its subject/snippet, call `get_thread` to read the full body. Then classify it yourself — there's no fixed keyword-to-status mapping, use judgment on the actual content:

- **Company**: who sent it / who the role is with
- **Role**: best guess at the job title, if determinable
- **Status**: one of `Applied`, `Under Review`, `Assessment`, `Interview`, `Offer`, `Rejected`, `Withdrawn`, `Other`
- Skip threads that turn out irrelevant on inspection (newsletters, unrelated automated mail that happened to match a keyword)

If a company/role has multiple threads (e.g. application ack, then later an interview invite), classify based on the most recent/advanced status for that company+role — the sheet should reflect current state, not a log of every email.

## Step 4 — Write to the Applications tab

Build a JSON list of `{company, role, status, last_updated, thread_link, snippet}` — `thread_link` should be `https://mail.google.com/mail/u/0/#all/<thread_id>`, `last_updated` the ISO date of the most recent relevant message in that thread, `snippet` a short (one-line) human-readable note on what happened (e.g. "Interview scheduled for Aug 20").

Write it to a temp file, then run:
```
python scripts/update_application_tracker.py --updates <path-to-temp.json> --tab-name Applications
```

This upserts into the dedicated **Applications** tab (separate from the date-based job-search tabs), keyed by `thread_link` — re-scanning the same thread updates its row in place rather than duplicating it.

## Step 5 — Update scan state

Write `archives/gmail_scan_state.json` with the current timestamp as `last_scanned_at`, so the next run only scans new mail.

## Step 6 — Compute dashboard data

```
python scripts/build_dashboard_data.py --tab-name Applications --follow-up-after-days 7 --out outputs/dashboard_data.json
```

Reads the Applications tab (the rows just upserted in Step 4) and computes, purely from `Status`/`Last Updated` — **no reference to the job-search Sheet at all, this dashboard is Gmail-only**:
- **Totals**: in progress, interviewed, offers, rejected, withdrawn.
- **Needs follow-up**: rows still `Applied`/`Under Review` after 7+ days of silence.
- **Needs a thank-you**: rows currently at `Interview` status. This is a flag only — it does **not** draft or send anything. It clears on its own once a later scan updates that row past `Interview` (offer/rejected/etc.) — there's no manual dismissal needed.

## Step 7 — Publish or update the dashboard Artifact

Read `outputs/dashboard_data.json` and write the dashboard page yourself (this step can't be scripted — the Artifact tool is only callable by you, not a subprocess). **Before writing it**, load the `artifact-design` skill (and `dataviz` if you use any chart element) — required, not optional, even if this feels like a quick job.

Check `archives/dashboard_state.json` first:
- **If it has an `artifact_url`**: republish to that *same* URL (pass `url` to the Artifact tool) so the candidate's existing bookmark keeps working — never omit `url` on a re-run, or a duplicate artifact gets created by mistake.
- **If absent (first-ever run)**: publish fresh, then write the returned URL into `archives/dashboard_state.json` as `{"artifact_url": "..."}`.

Content: KPI tiles from `totals`, a "Needs Follow-Up" list (company, role, days silent, link to the Gmail thread), a "Needs a Thank-You" list (company, role, link), the `generated_at` timestamp, and a visible note that this is read-only and only updates when asked. No `capabilities` needed — a plain page, regenerated on request, not live-syncing.

## Step 8 — Summary

Print a one-line summary including the dashboard: "Scanned N threads, tracked M applications (X new, Y updated). Dashboard: `<artifact URL>` — P in progress, Q need follow-up, R need a thank-you." Also print the Applications tab's sheet URL (from `update_application_tracker.py`'s stdout).

## Prerequisites

- `.venv/` must exist with `requirements.txt` installed (same as the job-search skill) — this skill's script reuses `push_to_sheets.py`'s credential-loading code.
- `.env` must have `SHEET_ID` and `JSON_KEY_BASE_64` (the same Google service account used by `push_to_sheets.py`). If missing, stop and say which one.
- This skill does **not** require `context/profile.md` or `configs/search.json` — it's independent of onboarding/job-search and can run any time Gmail is connected.
