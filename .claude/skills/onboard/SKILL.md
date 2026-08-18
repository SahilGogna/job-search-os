---
name: onboard
description: First-run setup only — use when there is no context/profile.md yet, or the candidate says "onboard me" / "set me up" / "get me started". Reads a detailed multi-page resume, confirms target roles, writes context/profile.md and configs/search.json, runs the connections skill to get .env and Gmail working, and offers Gmail application tracking. If a profile ALREADY exists, do not run this — use update-profile instead.
---

## What this skill does

One-time setup. Turns a **detailed, multi-page resume** (ask for the fullest version they have — every role, not a one-pager) into:

- `context/profile.md` — the candidate context every other skill reads
- `configs/search.json` — derived search parameters

Then gets connections working and offers Gmail tracking. It does **not** run a job search.

**If `context/profile.md` already exists, stop and hand off to `update-profile`.** That skill owns every kind of profile change — a new cert, a new project, or a whole new resume. Onboarding is first-run only.

## Step 0 — Environment

This parses a PDF with `pdfplumber` from the project venv. If `.venv/` doesn't exist, create it and `pip install -r requirements.txt`. Onboarding is usually the first thing to run in a fresh clone, so don't assume it's there.

## Step 1 — Get the resume

Ask for their fullest resume PDF — explicitly: *"not just a one-pager; if you have a longer version with every role, use that."* Save it to `resumes/resume.pdf`.

## Step 2 — Parse it

Follow the extraction rules in [`references/profile-schema.md`](../../../references/profile-schema.md) §1. Every page, every role, verbatim bullets, nothing invented.

## Step 3 — Confirm target roles

Infer 5–8 target role titles from what you parsed, then **show the list and ask them to confirm, edit, add, or remove** before continuing. Don't silently lock in your inference — a resume can support more than one direction, and they may want to drop roles they're qualified for but don't want, or add ones they're stretching toward.

## Step 4 — Write both files

Write `context/profile.md` (schema: `references/profile-schema.md` §2) and `configs/search.json` (derivation rules: §3), using the confirmed role list from Step 3.

## Step 5 — Connections

Invoke the **`connections`** skill (full scope). It walks them through `.env` one key at a time and checks Gmail — and if everything already works, it just says so and returns.

Never inspect `.env` yourself here or anywhere else. Carry forward whether Gmail came back connected — Step 6 needs it.

## Step 6 — Gmail tracking opt-in

If Step 5 found Gmail **not** connected, say so briefly and skip to Step 7 — don't offer a scan that would fail.

Otherwise ask:

> *"Want me to track your application status by reading your Gmail? It's read-only — I never send, label, or change anything — and it builds a private dashboard you can ask me to refresh anytime: what's in progress, what's been responded to, and flags like 'time to follow up' or 'you interviewed, worth sending a thank-you.'"*

Record the answer as `gmail_tracking_enabled` in `context/profile.md`. This only controls whether onboarding runs a scan *now* — declining doesn't disable anything, they can say "check my applications" whenever and that's consent in the moment.

- **Yes** → invoke `application-tracker`, telling it to use a **30-day** window for this first scan (not its 90-day standalone default). Carry the dashboard URL into Step 7.
- **No** → straight to Step 7.

This dashboard is built purely from Gmail and has nothing to do with `configs/search.json` or the job-postings sheet.

## Step 7 — Close

Three lines, no menu:

```
✓ You're set up. I know your background, what roles you're targeting, and where to search.

Next: say "find jobs for me" whenever you want a search.
[if a scan ran]  Your application dashboard: <url>
[if a gap remains]  Still to connect: <X> — just ask me when you're ready.
```
