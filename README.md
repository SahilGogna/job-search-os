# Job Hunter

## What we're building

A local Python project that turns a resume PDF into a live list of matching job postings — from LinkedIn *and* company career sites — in a Google Sheet, plus a tailored resume PDF for every strong match and a read-only Gmail dashboard tracking what happened to each application. No deployment. No external LLM calls. Claude Code is the reasoning layer.

## How it works end to end

1. Open Claude Code in this project folder. If it's your first time (no `context/profile.md` yet), it runs the **onboard** skill: give it your fullest resume PDF — a detailed, multi-page one covering every role, not a one-pager — and it reads it itself, figures out skills, location, and years of experience, proposes a list of target roles and **checks that list with you before locking it in**, then writes `context/profile.md` (your full profile) and `configs/search.json` (the derived search plan). It then invokes the **connections** skill, which walks you through `.env` (`APIFY_TOKEN`, `JSON_KEY_BASE_64`, `SHEET_ID`) one value at a time and confirms Gmail is connected — never blocking the rest of setup if you'd rather finish it later. Finally it asks whether you want Gmail application tracking enabled — say yes and it runs an initial scan right there.
2. From then on, just say *"find jobs for me"* — the **job-search** skill runs:
   - `scripts/fetch_jobs.py`, which calls Apify's LinkedIn Jobs Scraper (Curious Coder), filtered to the last 24 hours
   - `scripts/fetch_companies.py` (if `configs/companies.json` exists), which hits company career sites directly — Greenhouse, Lever, and Workday's public JSON APIs
   - `scripts/score_jobs.py`, which merges both sources, dedupes across them, and ranks postings against `configs/search.json`
   - `scripts/push_to_sheets.py`, which appends the ranked list to a Google Sheet
3. Claude Code prints the sheet URL and a one-line summary, then offers resumes — say yes and the **tailor-resumes** skill takes over: pick all, the top N, everything above a bar, or specific postings. You can also paste a JD for a job found anywhere else and get a resume for that. Kept separate from the search on purpose: by the time it runs, your results are already safely in the sheet.
4. Got a new cert, a new project, or a new resume? Say so — the **update-profile** skill handles all of it: small edits applied directly, a new resume PDF parsed and diffed against your profile so you can accept only what you want.
5. Anytime, say *"check my applications"* (or "update my dashboard") — the **application-tracker** skill does a read-only scan of Gmail for application-related emails (confirmations, interviews, offers, rejections), classifies each one, upserts the result into a dedicated **Applications** tab, and republishes a private **dashboard** (counts + "time to follow up" / "send a thank-you" flags) as a Claude Artifact at a stable URL. This dashboard is entirely independent of the job-postings Sheet — it's built purely from Gmail, doesn't know or care what's in the Sheet. It never modifies Gmail — no labels, no message changes, no drafted/sent emails, read-only.

## Why this design

* Claude Code does the resume parsing and search planning natively. No OpenAI or Anthropic API call from inside the code. The scripts are dumb: they consume a config and produce data
* Onboarding happens once, not on every search — your profile persists in `context/profile.md` instead of being re-derived from the PDF each time
* Every step is inspectable. If a run pulls weak results, open `configs/search.json` and see exactly what Claude Code decided
* Sources are portal-agnostic by design: every fetcher tags a `source` field and produces the same raw item shape, so `score_jobs.py`/`push_to_sheets.py` never needed to change to support company career sites alongside LinkedIn
* Google Sheets is the deliverable so you can filter, sort, and share without opening Excel
* Resume tailoring only reorders/emphasizes content already in your profile — it never invents experience

## Tech stack

* Python 3.11 or newer
* Apify REST API (Curious Coder LinkedIn Jobs Scraper)
* Greenhouse, Lever, and Workday public JSON APIs for company career sites
* Google Sheets API via service account
* `pdfplumber` for reading resumes
* `pandas` for data handling
* `gspread` and `google-auth` for Sheets writes
* `pyyaml` for reading `context/profile.md`'s structured data
* A LaTeX engine (`tectonic` or `pdflatex`) for compiling tailored resumes

## Project structure

```
job-hunter/
  CLAUDE.md                short manifest — points at the skills below
  .claude/skills/
    onboard/SKILL.md               first run only: resume → profile + config, then connections
    update-profile/SKILL.md         every later change: a cert, a project, or a new resume
    connections/SKILL.md            .env setup + live verification; Gmail connector check
    job-search/SKILL.md            asks sources → fetch → score → sheet (then offers resumes)
    tailor-resumes/SKILL.md         resume PDFs from a search, or from a pasted JD
    application-tracker/SKILL.md    read-only Gmail scan → Applications tab → dashboard Artifact
  references/
    profile-schema.md               profile schema + parsing/derivation rules (shared, single copy)
  README.md                same as this brief, for humans
  connections.md            registry of every external system this project reaches (script vs mcp)
  decisions/log.md          append-only record of meaningful design decisions and why
  example.env              template with placeholders — copy to .env and fill in
  .env                     APIFY_TOKEN, JSON_KEY_BASE_64, SHEET_ID (never committed)
  .gitignore               ignores .env, resumes/, outputs/, context/*.md, archives/, configs/search.json
  requirements.txt
  resumes/                  your resume PDF lives here (resume.pdf)
  context/
    profile.md               your full profile — identity, history, skills, gmail_tracking_enabled (gitignored, contains PII)
  configs/
    search.json                derived search plan, generated by the onboard skill (gitignored, personal)
    companies.json              target companies + their ATS platform for direct career-site fetching (tracked — not personal data)
  templates/
    resume_template.tex        LaTeX template the tailoring step fills in
    resume.cls                  its document class (FAANGPath / Trey Hunner format)
  archives/                  safety snapshots of profile.md/search.json before a re-onboard; gmail_scan_state.json; dashboard_state.json (Artifact URL)
  scripts/
    fetch_jobs.py                 calls Apify, returns raw JSON
    fetch_companies.py             calls Greenhouse/Lever/Workday APIs directly, returns raw JSON
    score_jobs.py                 merges sources, dedupes, filters and ranks against config
    push_to_sheets.py             appends to the Google Sheet (date-based job tabs)
    generate_resumes.py            renders tailored PDFs for strong matches
    update_application_tracker.py   upserts Gmail-derived status into the Applications tab
    build_dashboard_data.py         aggregates the Applications tab into dashboard counts + flags
    check_connections.py            reports connection status — never prints a secret value
    set_env_value.py                the only writer of .env (stdin / --from-file-base64)
    make_manual_posting.py          a pasted JD → one scored row, for tailor-resumes
  outputs/
    raw_linkedin.json, raw_companies.json, scored.json    per-run data
    dashboard_data.json                                     computed dashboard summary (input to the Artifact)
    tailored_resumes/<YYYY-MM>/<YYYY-MM-DD>/                generated PDFs (gitignored, contains PII)
```

## One-time setup

The `/connections` skill (invoked automatically by `/onboard`, or run standalone anytime — "set up my API keys") walks you through this interactively, one value at a time, and validates each with a real call rather than trusting it blindly. What follows is the manual version, for reference or if you'd rather do it yourself.

**How secrets are handled:** Claude never reads `.env` — not even to check whether a key is set. Status comes from `scripts/check_connections.py`, which prints only `valid` / `invalid` / `missing`; writes go through `scripts/set_env_value.py`, which takes the value on stdin (never the command line, which is visible in process listings) or base64-encodes a service-account JSON file in-process so the credential never appears in a terminal. `Read` on `.env` is denied outright in `.claude/settings.local.json`.

Copy `example.env` to `.env` and fill in the three values below.

### Apify
* Get an API token from https://console.apify.com/account/integrations
* Put it in `.env` as `APIFY_TOKEN`

### Google service account

1. Google Cloud Console — create a project (or reuse an existing one)
2. Enable the Google Sheets API and Google Drive API
3. Create a service account, generate a JSON key, download the JSON file
4. Store the key — just give `/connections` the file path and it encodes it in-process:
   ```
   python scripts/set_env_value.py --key JSON_KEY_BASE_64 --from-file-base64 path/to/service-account.json
   ```
   (Doing this by hand with `base64 ... | pbcopy` also works, but the encoded blob *is* the credential — the script avoids putting it on a clipboard or a terminal.)
5. Create a new Google Sheet called something like "Job Hunter Results"
6. Share the sheet with the service account email (the `client_email` field in the JSON key), give it Editor access
7. Copy the Sheet ID from the URL (`https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`) into `.env` as `SHEET_ID`

The JSON key file itself never lives on disk in this project — only its base64 form in `.env`.

### LaTeX engine (for tailored resumes)

Install one of:
```
brew install tectonic      # preferred — self-contained, no full TeX Live needed
```
or use an existing `pdflatex` install (e.g. MacTeX). The job-search skill checks for either automatically and tells you if neither is found.

### Your own resume template (optional)

`templates/resume_template.tex` ships with a working default (FAANGPath / Trey Hunner `resume.cls` format). Swap in your own `.tex` design any time — just keep the placeholder tokens documented in that file's header comment (`FULL_NAME`, `SUMMARY`, `SKILLS_LIST`, `EXPERIENCE_BLOCK`, etc.) and drop any custom `.cls`/`.sty` files in `templates/` alongside it.

## Config file schema

The onboard skill generates this from your profile. Example:

```json
{
  "candidate_name": "Jane Doe",
  "target_roles": ["Data Analyst", "BI Analyst", "Business Intelligence Analyst", "Analytics Engineer", "Junior Data Analyst", "Reporting Analyst"],
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
    "python":    {"weight": 3, "variants": ["python", "pandas", "numpy"]},
    "sql":       {"weight": 3, "variants": ["sql", "mysql", "postgres"]},
    "power_bi":  {"weight": 3, "variants": ["power bi", "dax", "power query"]},
    "tableau":   {"weight": 2, "variants": ["tableau"]},
    "etl":       {"weight": 3, "variants": ["etl", "elt", "data pipeline"]},
    "cloud":     {"weight": 2, "variants": ["azure", "aws", "snowflake", "bigquery"]},
    "ml_ai":     {"weight": 2, "variants": ["nlp", "rag", "llm", "genai"]}
  },
  "exclude_title_terms": ["senior", "sr.", "lead", "principal", "staff", "manager", "director"],
  "max_experience_years_penalty": 5
}
```

`location.region_aliases` only affects `fetch_jobs.py`'s LinkedIn search-URL construction (one of its two searches is province-scoped, the other is country-wide + remote) — it does **not** restrict what the scorer keeps. The scorer's own location filter is country-wide: any posting located anywhere in `location.country`, or a remote posting mentioning that country, passes — a real fix, not just a design choice: an earlier version matched province code `"ON"` via naive substring search, which falsely matched inside the word "London" (`re.search(r"\bON\b", ...)` word-boundary matching now prevents that). `title_match_bonus` (default 6) is added when the job title contains any of the `target_roles` phrases — bump higher to make title alignment dominate. Set `require_title_match: true` to hard-drop postings whose titles don't match. `resume_tailoring_min_score` (default 60) is the threshold above which `generate_resumes.py` produces a tailored PDF. `max_posting_age_days` (default 7) drops postings older than a week — applies to every source; a posting whose date can't be determined is kept, not dropped, and counted separately in the summary line.

## Company career-site config (`configs/companies.json`)

Optional. If present, `job-search` also fetches postings directly from these companies' own career sites, alongside LinkedIn. Schema:

```json
{
  "results_per_company": 30,
  "companies": [
    {"name": "RBC", "ats": "workday", "tenant": "rbc", "shard": "wd3", "site": "RBCGLOBAL1"},
    {"name": "Some Startup", "ats": "greenhouse", "token": "somestartup"},
    {"name": "Another Co", "ats": "lever", "org": "anotherco"},
    {"name": "No API Co", "ats": "custom", "note": "no public API found — skipped at fetch time"}
  ]
}
```

`ats` selects the fetcher: `greenhouse` needs `token` (the `boards.greenhouse.io/<token>` slug), `lever` needs `org` (the `jobs.lever.co/<org>` slug), `workday` needs `tenant` + `shard` + `site` (from that company's `https://<tenant>.<shard>.myworkdayjobs.com/<site>` careers URL). Anything else (including `custom`) is skipped — logged, not fatal.

**Finding these values for a new company**: visit its careers page and watch the network tab, or search for `"<company> careers myworkdayjobs.com"` / check if `boards.greenhouse.io/<guess>` or `jobs.lever.co/<guess>` resolves. Don't guess and commit a value you haven't confirmed — a wrong tenant/token just 404s silently at fetch time (logged as a per-company failure, not caught any other way). The starter list shipped in this repo has each Workday entry verified this way; several other major employers are still marked `"custom"` pending that same check.

## Listing verification

Apify's search-page scraper doesn't tell us whether a posting is still accepting applications. After the fetch, `scripts/fetch_jobs.py` hits `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>` for each result and drops any listing whose Apply button is missing (`top-card-layout__cta--primary`). Serial with a 1s delay to avoid LinkedIn's rate limit — expect ~5 min for a few hundred postings. Set `"verify_listings": false` in the config to skip.

## Match Score

The Sheet's Match Score column is a **0–100 percentage**: `round((skill_weights_matched + title_bonus − experience_penalty) / (sum_of_all_skill_weights + title_match_bonus) × 100)`. 100 means a posting matched every core skill and its title contained a target-role phrase with no over-experience penalty. Postings that score below the config's `min_match_score` (default 50) are dropped before the sheet write.

## Resume tailoring

For every scored posting above `resume_tailoring_min_score` (default 60), `scripts/generate_resumes.py`:

1. Reads the candidate's full profile from `context/profile.md`'s YAML frontmatter
2. Reorders the skills list and each role's bullets so ones overlapping that posting's matched skills surface first — deterministic keyword matching, no LLM calls, never rewrites or invents content
3. Fills `templates/resume_template.tex`'s placeholder tokens with the reordered content
4. Compiles it to a PDF via `tectonic` (or `pdflatex`) into `outputs/tailored_resumes/<YYYY-MM>/<YYYY-MM-DD>/`

Filenames are `<company>_<job-title>_<posting-id>.pdf`, nested by month then day so runs don't pile up in one flat folder — same date-ownership pattern `push_to_sheets.py` uses for its tab names. The intermediate `.tex` files are kept alongside in that day's `tex/` subfolder for inspection.

## Application tracker + dashboard

Independent of job-search and of the job-postings Sheet — run any time by saying "check my applications" or "update my dashboard". The `application-tracker` skill:

1. Searches Gmail broadly for application-signal emails (keywords + known ATS/recruiting sender domains), scoped to since the last scan (`archives/gmail_scan_state.json`) or the last 90 days on first run (30 days if this is the initial scan triggered by onboarding)
2. Reads each plausible thread in full and classifies it itself — Company, Role, Status (`Applied`, `Under Review`, `Assessment`, `Interview`, `Offer`, `Rejected`, `Withdrawn`, `Other`) — no fixed keyword-to-status mapping, judgment call on real content
3. Upserts the results into a dedicated **Applications** tab via `scripts/update_application_tracker.py`, keyed by Gmail thread link — re-scanning the same thread updates its row instead of duplicating it
4. Computes dashboard data via `scripts/build_dashboard_data.py` — totals by status, plus two flagged lists: **needs follow-up** (still `Applied`/`Under Review` after 7+ days of silence) and **needs a thank-you** (currently `Interview` status — a highlighted flag, not a drafted or sent email)
5. Publishes/updates a private **Claude Artifact** dashboard at a stable URL (persisted in `archives/dashboard_state.json` so re-runs update the same page instead of creating a new one each time)

**This is read-only.** It only calls Gmail's `search_threads`/`get_thread` — never `label_thread`, `label_message`, `create_label`, or any other mutation, and never drafts or sends mail. Your inbox is never modified, only read.

The Applications tab is entirely separate from the date-based job-search tabs (`2026-07-21`, etc.) and from `push_to_sheets.py`'s merge logic — it's its own tab, own schema, own scripts. The dashboard itself never references job postings at all — it's built purely from what Gmail says about your applications, independent of whether/how a posting came from this tool.

## Google Sheet layout

Each run writes to a tab named by date, for example `2026-07-21`. Columns:

1. Match Score
2. Source
3. Job Title
4. Company
5. Location
6. Experience Required
7. Seniority
8. Employment Type
9. Skills Matched
10. Posted
11. Applicants
12. Job Description
13. Apply Link
14. Fetched At
15. Posting ID
16. New Since Last Run

Header row bold, freeze first row, filter on all columns, sorted by Match Score descending.

**Same-day re-runs merge into the existing tab.** Rows are keyed by apply link — new postings are appended, and postings that already appear are refreshed with the latest score/details. A new calendar day starts a fresh tab. If the tab's header row doesn't match the current schema (e.g., after a code update that adds a column), the existing rows are discarded and the tab is rewritten with just the current run's data — no half-schema stitching.

**Posting ID** is a stable hash of each posting's apply link (or company+title+location+source if it has no link) — the same posting gets the same ID on every run, which is what makes cross-day comparison possible. **New Since Last Run** compares today's Posting IDs against the most recent *previous* date tab and marks `Yes`/`No` — pure visibility, nothing is ever dropped from the sheet based on this; a still-open posting keeps showing up across days. If there's no comparable previous tab yet (first run, or an older tab from before this column existed), everything is marked `Yes` and the run's printed summary says so explicitly rather than treating it as a silent default.

**Source** is tagged at fetch time (`LinkedIn`, or `<Company> Careers` for direct career-site postings), so adding another portal later just means a new fetch script that tags `Source` differently — score/push code stays unchanged. The **Applications** tab (see above) is a separate, non-date-named tab in the same spreadsheet — not part of this rotation.

## First message to Claude Code

Open Claude Code in the project folder and say:

> Onboard me — here's my resume.

(attach your fullest resume PDF). Once your profile exists, just say:

> Find jobs for me

And whenever you want a status check:

> Check my applications

That's the whole loop.
