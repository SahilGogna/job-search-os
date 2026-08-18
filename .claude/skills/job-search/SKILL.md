---
name: job-search
description: Use when the candidate wants to run a job search — "find jobs for me", "run job search", "search for jobs", "what's new today". Requires context/profile.md and configs/search.json to already exist (run the onboard skill first if not). Fetches LinkedIn postings (and, if configs/companies.json exists, direct company career-site postings too), scores them against the profile, pushes results to Google Sheets, and generates tailored resumes for the best matches.
---

## Prerequisites

1. `context/profile.md` and `configs/search.json` must both exist. If either is missing, tell the candidate to run onboarding first (say: "I don't have your profile yet — let's onboard you first") and stop. Do not improvise a config from a conversation alone.
2. Ensure the project venv is ready: if `.venv/` doesn't exist, create it and `pip install -r requirements.txt`.
3. Verify `.env` has `APIFY_TOKEN`, `JSON_KEY_BASE_64`, `SHEET_ID`. If any is missing, stop and tell the candidate exactly which one.
4. Verify a LaTeX engine is on PATH (`tectonic` or `pdflatex`) for the resume-tailoring step below. If neither is found, try `brew install tectonic`. If that also fails, tell the candidate and continue without step 5 (fetch/score/push still run; tailoring is skipped) rather than blocking the whole search on a missing toolchain — say so explicitly in the summary line.

If any of the required steps below fails, print the error and stop. Do not silently fall back or skip a required step without saying so.

## Steps

1. **Fetch — LinkedIn**: `python scripts/fetch_jobs.py --config configs/search.json --raw-out outputs/raw_linkedin.json`
   - Verifies each posting is still open by hitting `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>` — a listing with no `top-card-layout__cta--primary` button is dropped as closed. Serial + 1s delay (~5 min for a few hundred postings). Disable with `"verify_listings": false` in the config only if a fast fetch is needed and closed listings will be filtered downstream. Postings the verifier can't reach are kept.

2. **Fetch — company career sites** (optional): if `configs/companies.json` exists, also run `python scripts/fetch_companies.py --config configs/companies.json --raw-out outputs/raw_companies.json`. Hits each company's public Greenhouse/Lever/Workday API directly — companies with no confirmed API (`"ats": "custom"`) are skipped and logged, not fatal. If `configs/companies.json` doesn't exist, skip this step entirely and proceed with LinkedIn only — don't block the search on an optional source.

3. **Score**: `python scripts/score_jobs.py --config configs/search.json --raw-in outputs/raw_linkedin.json [outputs/raw_companies.json] --scored-out outputs/scored.json`
   - `--raw-in` takes one or more paths — pass both files if step 2 ran, otherwise just the LinkedIn one.
   - Match Score is 0–100: `round((skill_weights_matched + title_bonus − experience_penalty) / (sum_of_all_skill_weights + title_match_bonus) × 100)`. Anything that computes to ≤0 is dropped. Postings below `min_match_score` are dropped.
   - Dedupes twice: first by exact link, then by normalized (company, title) so the same posting mirrored across LinkedIn and a company's own site collapses to one row (keeping whichever copy has the richer description).

4. **Push**: `python scripts/push_to_sheets.py --scored-in outputs/scored.json --tab-name <YYYY-MM-DD>`
   - Tab is date-based — a new day starts a fresh tab. Same-day re-runs **merge** into the existing tab keyed by apply link — the fresher row wins on collision.

5. **Tailor resumes**: `python scripts/generate_resumes.py --config configs/search.json --profile context/profile.md --scored-in outputs/scored.json --template templates/resume_template.tex --out-dir outputs/tailored_resumes`
   - Generates one PDF per posting scoring above `resume_tailoring_min_score` (default 60) into `outputs/tailored_resumes/<YYYY-MM>/<YYYY-MM-DD>/`, reordering the candidate's existing skills/bullets toward that posting's matched keywords — never inventing content. Skip this step (with a note in the summary) if no LaTeX engine was found in Prerequisites.

6. Print the sheet URL and a one-line summary: "Pulled X raw (Y LinkedIn, Z company sites), kept N after scoring, tailored M resumes (score > 60), wrote to tab `<date>`."

## URL construction (what fetch_jobs.py does under the hood)

For every target role the fetcher builds two LinkedIn search URLs:
1. `keywords=<role>&location=<region, country>&f_TPR=r86400[&f_E=<seniority>]` — province-wide.
2. If `include_remote_in_country`: `keywords=<role>&location=<country>&f_WT=2&f_TPR=r86400[&f_E=<seniority>]`

So 5 target roles with remote enabled produce 10 URLs. Total results requested from Apify = `results_per_search × url_count`. The scorer then drops postings whose `location` string doesn't match any `region_aliases` and isn't a remote posting in `country`. Empty posting locations fail-open.

## What fetch_companies.py does under the hood

Reads `configs/companies.json`'s `companies` list, dispatching each by its `ats` field (verified against real API responses, not guessed):
- **Greenhouse**: `GET boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`
- **Lever**: `GET api.lever.co/v0/postings/{org}?mode=json`
- **Workday**: `POST {tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs` (paginated), then one `GET .../job{externalPath}` per posting for the full description

`results_per_company` in `configs/companies.json` caps how many postings are pulled per company (default 30). Adding a new company: confirm its actual ATS and identifiers first (visit its careers page, or probe the guessed API URL) — don't guess tenant/board/org values blind, they need to be real. Companies without a confirmed API stay in the config as `"ats": "custom"` with a note, and are skipped at fetch time rather than blocking the run.
