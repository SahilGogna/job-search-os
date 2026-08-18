---
name: onboard
description: Use the first time this repo is opened (no context/profile.md exists yet), or whenever the candidate wants to update their profile from a new/revised resume ("update my resume", "onboard me", "set up my profile", "I have a new resume"). One-time setup that reads a full multi-page resume, proposes target roles and confirms them with the candidate before locking them in, produces context/profile.md + configs/search.json, and asks whether to enable read-only Gmail application tracking (invoking application-tracker for an initial scan if so). Re-running it later diffs the new resume against the existing profile and asks what to accept, rather than silently overwriting.
---

## What this skill does

Turns a **detailed, multi-page resume** (not a one-pager — ask for the fullest version the candidate has, covering every role, not just the most recent) into two durable files:

- `context/profile.md` — complete candidate context: identity, contact, location, full work history, education, skills, certifications, projects, leadership. This is the source of truth every other skill reads from.
- `configs/search.json` — the LinkedIn search parameters derived from that profile, in the schema the existing scripts (`fetch_jobs.py`, `score_jobs.py`, `generate_resumes.py`) already expect.

It does **not** run any job search itself — that's the `job-search` skill, which requires this to have run first.

## Step 0 — Environment

This skill parses a PDF with `pdfplumber`, which lives in the project venv. Before Step 1: if `.venv/` doesn't exist, create it and `pip install -r requirements.txt`. Onboarding is typically the very first thing that runs in this repo, so don't assume the venv is already set up.

## Step 1 — Get the resume

If `context/profile.md` does not exist: this is a fresh onboarding. Ask the candidate to provide their fullest resume PDF (explicitly: "not just a one-pager — if you have a longer/detailed version with every role, use that"). Save it to `resumes/resume.pdf`.

If `context/profile.md` already exists: this is a **re-onboard**. Go to Step 6 instead of Step 2.

## Step 2 — Parse the resume

Read `resumes/resume.pdf` with pdfplumber. Extract, across the **entire** document (every page, every role — do not stop at "most recent role"):

- Full name, email, phone
- **Location** — resolve to `{city, region, country}` using this priority order:
  1. Address line on the resume
  2. Most recent employer or education location
  3. Phone country/area code (e.g. Canadian +1 437 → Toronto, Ontario, Canada; +1 415 → San Francisco, California, USA)
  4. Default to `{city: "Toronto", region: "Ontario", country: "Canada"}` only if truly nothing else fits
- Links (LinkedIn, GitHub, portfolio, etc.)
- Professional summary (write one if the resume doesn't have an explicit summary line, from the overall arc of the roles below)
- **Every** work-history entry: title, company, location, dates, bullets — verbatim from the resume, not summarized
- Education: degree, institution, dates
- Certifications
- Complete skills inventory, **written in natural/display form** (e.g. "Power BI", "SQL", "Python") — not the snake_case identifiers used internally in `configs/search.json`'s `core_skills` keys. This matters: `generate_resumes.py` matches config skill keys against this list by folding case/underscores, but the PDF renders these skill names as-is, so they must read like a resume, not a variable name.
- Projects (if any project/portfolio section exists)
- Leadership / extracurricular (if any such section exists)
- `experience_years`: total professional experience, stated or computed from role dates

## Step 3 — Write `context/profile.md`

YAML frontmatter with all of the above, followed by a short human-readable markdown rendering of the same content (for quick reading — not read by scripts). Schema:

```yaml
---
name: Jane Doe
email: jane@example.com
phone: "+1 416 555 0100"
location:
  city: Toronto
  region: Ontario
  country: Canada
links:
  linkedin: https://linkedin.com/in/janedoe
  github: https://github.com/janedoe
experience_years: 3
gmail_tracking_enabled: false   # set by Step 7 — whether onboarding should proactively run application-tracker
summary: One or two sentences — who they are, what they do, what they're looking for.
skills:
  - Python
  - SQL
  - Power BI
education:
  - degree: B.Sc. Computer Science
    institution: University of Toronto
    dates: "2018 - 2022"
experience:
  - title: Data Analyst
    company: Acme Corp
    location: Toronto, ON
    dates: "Jan 2023 - Present"
    bullets:
      - Verbatim bullet from the resume
      - Another verbatim bullet
projects:            # omit the key entirely (or leave as []) if the resume has none
  - title: Project Name
    description: One-line description
leadership:           # omit the key entirely (or leave as []) if the resume has none
  - title: Role/Org Name
    description: One-line description
---

# Jane Doe — Profile

(short human-readable narrative mirroring the frontmatter, for quick reading)
```

`projects` and `leadership` are optional — `generate_resumes.py` drops those resume sections entirely when absent rather than leaving placeholder text, so it's safe (and correct) to omit them when the resume has nothing there. Never invent a project, role, or bullet that isn't on the resume.

## Step 4 — Confirm target roles

Before deriving the search config, infer a candidate list of 5–8 target role titles from the profile (same rule as Step 5 below: close, specific variants around the resume's focus, not broad umbrella titles). **Show this list to the candidate and ask them to confirm, edit, add, or remove roles before continuing** — don't silently lock in your inference. A resume can support more than one direction (e.g. a Data Analyst background that could target Data Analyst, Product Analyst, or something narrower/broader), and the candidate may want to exclude roles they're qualified for but don't want, or add ones they're stretching toward. Use their confirmed list, not your first guess, in Step 5.

## Step 5 — Derive `configs/search.json`

Using the profile and the candidate-confirmed target roles from Step 4, apply the same decision rules as before:

```json
{
  "candidate_name": "...",
  "target_roles": ["...", "..."],
  "location": {
    "city": "Toronto",
    "region": "Ontario",
    "country": "Canada",
    "region_aliases": ["Ontario", "ON"],
    "include_remote_in_country": true
  },
  "experience_years": 2,
  "seniority_filter_codes": [2, 3, 4],
  "results_per_search": 50,
  "title_match_bonus": 6,
  "require_title_match": false,
  "min_match_score": 50,
  "resume_tailoring_min_score": 60,
  "max_posting_age_days": 7,
  "core_skills": {
    "python": {"weight": 3, "variants": ["python", "pandas", "numpy"]}
  },
  "exclude_title_terms": ["senior", "sr.", "lead", "principal", "staff", "manager", "director"],
  "max_experience_years_penalty": 5
}
```

- `target_roles`: the list confirmed with the candidate in Step 4 — 5–8 role variants around the resume's focus, close/specific titles preferred over broad ones.
- `location.region_aliases`: spelling variants of the province LinkedIn may use in posting-location strings — used only by `fetch_jobs.py`'s LinkedIn URL construction (one of its two search URLs is province-scoped). The post-fetch scoring filter itself is country-wide, not province-restricted — any posting anywhere in `location.country`, or remote-in-country, passes.
- `seniority_filter_codes`: 1=intern, 2=entry, 3=associate, 4=mid-senior, 5=director, 6=executive — pick codes matching `experience_years`.
- `exclude_title_terms`: senior, sr., lead, principal, staff, manager, director if fewer than 5 years of experience.
- `core_skills`: pull from `profile.md`'s skills list; assign weights based on how central each is to the candidate's story. Keys are snake_case identifiers (e.g. `power_bi`); `variants` lists the natural-language forms to match against posting text.
- `title_match_bonus`: default 6.
- `max_posting_age_days`: default 7 — postings older than this are dropped. Applies across all sources; if a posting's date can't be determined (rare, mainly some Workday listings), it's kept rather than dropped, and counted in the score summary.
- `min_match_score`: default 50 — postings below this are dropped before the sheet write.
- `resume_tailoring_min_score`: default 60 — postings above this get a tailored resume generated by the job-search skill's final step.

## Step 6 — Re-onboard: diff and ask

When `context/profile.md` already exists and the candidate provides a new/updated resume:

1. Parse the new resume exactly as in Step 2, into a scratch copy — do not touch the existing files yet.
2. Diff it against the current `context/profile.md` frontmatter: new/changed roles, new/removed skills, changed location, changed contact info, etc. Present the concrete differences to the candidate in plain language (not a raw diff dump).
3. Ask what to do: accept everything, accept specific items, or keep the current profile as-is. Only apply what's confirmed.
4. Before writing anything, snapshot the current `context/profile.md` and `configs/search.json` to `archives/onboard-{YYYY-MM-DD-HHMM}/` as a safety net — regardless of what gets accepted.
5. Apply the confirmed changes to `context/profile.md`. If anything relevant to `configs/search.json` changed (skills, experience level, location), re-derive `target_roles` and re-run Step 4's confirmation with the candidate before writing the rest of Step 5; otherwise leave `configs/search.json` untouched.

## Step 7 — Gmail tracking opt-in

Ask directly, as its own clear question — not buried in other prose, and not skipped:

> *"Do you want me to track your application status by reading your Gmail? This is read-only — I never send or label anything, only read and summarize — and it builds a private dashboard you can ask me to update anytime, showing what's in progress, what's been responded to, and flagging things like 'time to follow up' or 'you had an interview, might want to send a thank-you.'"*

Store the answer in `context/profile.md` frontmatter as `gmail_tracking_enabled: true|false`. This only controls whether onboarding *proactively* runs a first scan below — declining doesn't disable the capability; the candidate can still say "check my applications" manually at any later point, which counts as consent in that moment.

- **If yes**: invoke the `application-tracker` skill now, telling it to use a **30-day** scan window for this specific first run (not its own 90-day standalone default — see that skill's Step 1). Let it run through its own steps (scan, classify, write the Applications tab, build the dashboard, publish the Artifact). Carry its resulting dashboard URL into Step 8's closing message.
- **If no**: skip straight to Step 8, no scan.

This dashboard is entirely independent of `configs/search.json`/job postings — it's Gmail-only, built from application-status emails, and never references what jobs were found or applied to.

## Step 8 — Close

One-line confirmation of what was written, then point the candidate at the job-search skill: "Say 'find jobs for me' whenever you want to run a search." If Step 7 ran a scan, also include the dashboard URL: "Your application dashboard: `<url>`."
