# Job Hunter workflow

When the user says "find jobs for <name>.pdf" or similar:

1. Read the PDF at `resumes/<name>.pdf` using pdfplumber.
2. Extract from the resume:
   * Full name
   * Current or target job titles (from profile summary, most recent role, and experience level)
   * Years of professional experience
   * Core skills (programming languages, tools, cloud, databases, visualization)
   * Location — must resolve to `{city, region, country}`. Sources, in priority order:
     - Address line on the resume
     - Most recent employer or education location
     - Phone country/area code (e.g. Canadian +1 437 → Toronto, Ontario, Canada; +1 415 → San Francisco, California, USA)
     - Default to `{city: "Toronto", region: "Ontario", country: "Canada"}` only if truly nothing else fits
3. Decide search parameters. Write `configs/<name>.json` using this schema:
   ```json
   {
     "candidate_name": "...",
     "target_roles": ["...", "..."],
     "location": {
       "city": "Toronto",
       "region": "Ontario",
       "country": "Canada",
       "radius_km": 100,
       "include_remote_in_country": true
     },
     "experience_years": 2,
     "seniority_filter_codes": [2, 3, 4],
     "results_per_search": 50,
     "title_match_bonus": 6,
     "require_title_match": false,
     "min_match_score": 50,
     "core_skills": {
       "python": {"weight": 3, "variants": ["python", "pandas", "numpy"]}
     },
     "exclude_title_terms": ["senior", "sr.", "lead", "principal", "staff", "manager", "director"],
     "max_experience_years_penalty": 5
   }
   ```
   * `target_roles`: 5 to 8 role variants around the resume's focus. Prefer close, specific titles over broad ones — the scorer weights title matches heavily.
   * `location.radius_km`: default 100. `include_remote_in_country`: default true. Together this means "jobs within 100 km of my city PLUS remote jobs anywhere in my country."
   * `seniority_filter_codes`: LinkedIn codes. 1=intern, 2=entry, 3=associate, 4=mid-senior, 5=director, 6=executive. Pick codes matching years of experience.
   * `exclude_title_terms`: senior, sr., lead, principal, staff, manager, director if the candidate has fewer than 5 years of experience.
   * `core_skills`: pull from the resume, assign weights based on how central each skill is to the candidate's story.
   * `title_match_bonus`: default 6. Bump to 10+ if title alignment must dominate skill matches. Set `require_title_match: true` to drop any posting whose title doesn't contain a target role phrase.
   * `min_match_score`: default 50. Postings scoring below this on the 0–100 scale are dropped before the sheet write. Lower it to widen the sheet, raise it to tighten.
4. Run: `python scripts/fetch_jobs.py --config configs/<name>.json --raw-out outputs/<name>_raw.json`
   * After Apify returns, the fetcher verifies each posting is still open by hitting `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>` — a listing with no `top-card-layout__cta--primary` button is treated as closed and dropped. This is serial + 1s delay (~5 min for a few hundred postings) to stay under LinkedIn's rate limit. Disable with `"verify_listings": false` in the config only if you need a fast fetch and will filter closed listings yourself downstream. Postings the verifier can't reach are kept.
5. Run: `python scripts/score_jobs.py --config configs/<name>.json --raw-in outputs/<name>_raw.json --scored-out outputs/<name>_scored.json`
6. Run: `python scripts/push_to_sheets.py --scored-in outputs/<name>_scored.json --tab-name <YYYY-MM-DD>`
   * The tab is date-based, so a new day starts a fresh tab automatically. Same-day re-runs **merge** into the existing tab keyed by apply link — fresh row wins on collision, so an updated score or newer `Fetched At` overwrites the earlier row for the same posting.
7. Print the sheet URL and a one line summary: "Pulled X raw, kept Y after scoring, wrote to tab <name>"

Match Score is a 0–100 percentage: `round((skill_weights_matched + title_bonus − experience_penalty) / (sum_of_all_skill_weights + title_match_bonus) × 100)`. 100 means a posting hit every core skill and matched a target role title with no over-experience penalty. Anything that would compute to ≤0 is dropped.

If any step fails, print the error and stop. Do not silently fall back.

## Environment
* Use the project venv at `.venv/`. If it doesn't exist, create it and install `requirements.txt` before step 4.
* All scripts read secrets from `.env` (`APIFY_TOKEN`, `JSON_KEY_BASE_64`, `SHEET_ID`). If any is missing, stop and tell the user.

## URL construction (what fetch_jobs.py does under the hood)
For every target role the fetcher builds two LinkedIn search URLs:
1. `keywords=<role>&location=<city, region, country>&distance=<radius_km→miles>&f_TPR=r86400[&f_E=<seniority>]`
2. If `include_remote_in_country`: `keywords=<role>&location=<country>&f_WT=2&f_TPR=r86400[&f_E=<seniority>]`

So 5 target roles with remote enabled produce 10 URLs. Total results requested from Apify = `results_per_search × url_count`.
