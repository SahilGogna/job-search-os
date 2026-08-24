---
name: onboard
description: First-run setup only — use when there is no context/profile.md yet, or the candidate says "onboard me" / "set me up" / "get me started". Reads a detailed multi-page resume, confirms target roles, writes context/profile.md and configs/search.json, runs the connections skill to get .env and Gmail working, and offers Gmail application tracking. If a profile ALREADY exists, do not run this — use update-profile instead.
---

## What this skill does

One-time setup. Turns a **detailed, multi-page resume** (ask for the fullest version they
have — every role, not a one-pager) into:

- `context/profile.md` — the candidate context every other skill reads
- `configs/search.json` — derived search parameters

Then gets connections working and offers Gmail tracking. It does **not** run a job search.

**If `context/profile.md` already exists, stop and hand off to `update-profile`.** That
skill owns every kind of profile change — a new cert, a new project, or a whole new
resume. Onboarding is first-run only.

**Never inspect `.env`** — here or anywhere else. `connections` owns that boundary, and
no credential ever enters this conversation.

## Resuming

Setup is split into phases so it can be interrupted and picked up later — it's long, and
the Google Cloud leg in particular often needs a second sitting.

After finishing each phase, record it in `context/setup-state.md`:

```markdown
# Setup state
- [x] Phase 0 — preflight (2026-08-24)
- [x] Phase 1 — resume received
- [ ] Phase 2 — target roles
```

**On entry, read `context/setup-state.md` if it exists**, resume at the first incomplete
phase, and say in one line which phases you're skipping and why. Never silently redo
completed work, and never silently skip work that wasn't done.

## Phase 0 — Preflight

Three things, in this order, before touching the resume.

**Environment.** This parses a PDF with `pdfplumber` from the project venv. If `.venv/`
doesn't exist, create it and `.venv/bin/pip install -r requirements.txt`. Onboarding is
usually the first thing to run in a fresh clone, so don't assume it's there.

**Connections status.** Run:
```
.venv/bin/python scripts/check_connections.py --scope apify,sheets
```
and separately call Gmail's `list_labels` to see whether that connector is authorized.

**Then tell them what's ahead.** This phase collects nothing and blocks nothing — it
exists so they learn up front what they'll need, instead of hitting it at the point of
failure. Name every gap and what it blocks:

> *"Before we start: your resume is all I need for the next few minutes. Three things
> aren't connected yet, and we'll set them up after — an Apify token (job search needs
> it), a Google service account plus a sheet (that's where results get written; it's the
> longest part, about ten minutes in the Google Cloud console), and the Gmail connector
> (that's how I track what happens to your applications)."*

All three are required. Gmail is not an optional extra — without it there's no application
tracking and no dashboard, which is half of what this tool does. Name it alongside the
other two, in the same breath, not as a footnote.

If everything is already valid, say so in one line and move on.

Credential setup deliberately comes **later** (Phase 4), not now: the profile work is
fast and worth doing first, and they can go create the Google Cloud project in the
meantime knowing what's coming.

## Phase 1 — Get the resume

Ask for their fullest resume PDF — explicitly: *"not just a one-pager; if you have a
longer version with every role, use that."*

Where it comes from, in strict order of preference:

1. **A resume attached to this conversation** — use it. This is the normal case and it
   takes priority over anything on disk.
2. Otherwise, ask for an **absolute file path** and read that.

**Never go looking for a resume on the filesystem** — not in a source folder, not in
Downloads, not anywhere. Don't glob for `*.pdf`, and don't read a resume you weren't
pointed at. Picking up a stale or wrong document silently poisons everything downstream.

Copy whichever one you were given to `resumes/resume.pdf`.

## Phase 2 — Parse it, and confirm target roles

Follow the extraction rules in
[`references/profile-schema.md`](../../../references/profile-schema.md) §1. Every page,
every role, verbatim bullets, nothing invented.

Then infer 5–8 target role titles from what you parsed, and **show the list and ask them
to confirm, edit, add, or remove** before continuing. Don't silently lock in your
inference — a resume can support more than one direction, and they may want to drop roles
they're qualified for but don't want, or add ones they're stretching toward.

## Phase 3 — Write the files, then review them together

Write `context/profile.md` (schema: `references/profile-schema.md` §2) and
`configs/search.json` (derivation rules: §3), using the confirmed role list from Phase 2.

Write first, then review — so an interruption during review doesn't lose the parse.

**Then surface what you built and get it confirmed.** This is the candidate's own
history; a parsing slip here propagates into every resume and every match score, and they
are the only one who can catch it. Show a compact summary:

- Every role: title, employer, dates — one line each, in order
- Education, and any certifications
- The **skill categories** you grouped their skills into, with the skills in each
  (§1 covers the grouping rules; this is inference, so it needs a human look)
- Resolved location and `experience_years`
- Counts for projects and leadership entries

Then point them at the file itself for the full detail:

> *"Full version is in `context/profile.md` — worth a read. In VS Code, `Cmd+Shift+V` on
> macOS or `Ctrl+Shift+V` on Windows opens a rendered preview. Anything wrong or missing?"*

Apply whatever corrections they name, re-show the affected part, and only advance once
they've confirmed. If they say it's fine without reading it, take that as confirmation
and move on — don't push.

## Phase 4 — Connections

Invoke the **`connections`** skill (full scope) for whatever Phase 0 flagged. It scaffolds
`.env`, hands over the complete Apify and Google Cloud sequences up front, and verifies
each key before advancing — and if everything already works, it just says so and returns.

Carry forward whether Gmail came back connected — Phase 5 needs it.

## Phase 5 — Gmail tracking opt-in

If Gmail is **not** connected, don't skip past it — go back through the `connections`
skill's Gmail step and ask them to connect it now. It's a required connection, and this is
the moment it pays off. Only continue to Phase 6 if they've been asked and still decline
or can't do it right now; in that case carry that forward, because Phase 6's close has to
report setup as incomplete.

Once it's connected, ask:

> *"Want me to track your application status by reading your Gmail? It's read-only — I
> never send, label, or change anything — and it builds a private dashboard you can ask
> me to refresh anytime: what's in progress, what's been responded to, and flags like
> 'time to follow up' or 'you interviewed, worth sending a thank-you.'"*

Record the answer as `gmail_tracking_enabled` in `context/profile.md`. This only controls
whether onboarding runs a scan *now* — declining doesn't disable anything, they can say
"check my applications" whenever and that's consent in the moment.

- **Yes** → invoke `application-tracker`, telling it to use a **30-day** window for this
  first scan (not its 90-day standalone default). Carry the dashboard URL into Phase 6.
- **No** → straight to Phase 6.

This dashboard is built purely from Gmail and has nothing to do with `configs/search.json`
or the job-postings sheet.

## Phase 6 — Close

Mark every phase complete in `context/setup-state.md`, then close.

**If every required connection is up** — Apify, Sheets, and Gmail — three lines, no menu:

```
✓ You're set up. I know your background, what roles you're targeting, and where to search.

Next: say "find jobs for me" whenever you want a search.
[if a scan ran]  Your application dashboard: <url>
```

**If any required connection is still missing**, don't print a ✓. Say setup is incomplete,
name what's missing, and say what it costs them — a missing required connection is not a
footnote on a success message:

```
Setup is incomplete — <X> still needs connecting.

Working now: <what they can already do>
Blocked until <X> is connected: <what they can't>

Say "set up my connections" whenever you're ready and we'll finish it.
```

For Gmail specifically, name the cost plainly: no application tracking and no dashboard,
so nothing will notice interview invites, rejections, or follow-ups that are due.
