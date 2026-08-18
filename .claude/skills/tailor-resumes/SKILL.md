---
name: tailor-resumes
description: Use to generate tailored resume PDFs — "make resumes for these", "tailor my resume for the top matches", "resume for this job", or when the candidate pastes a job description and wants a resume for it. Works from the last job search's results (outputs/scored.json) or from a JD pasted for a role found anywhere else. Offered as a handoff at the end of job-search, and runnable standalone anytime.
---

## What this skill does

Generates a resume PDF tailored to a specific posting — reordering the candidate's existing skills and bullets toward that posting's matched keywords. **It never invents or rewrites content**; everything in the PDF already exists in `context/profile.md`.

Deliberately separate from `job-search`: by the time this runs, the search results are already banked in the sheet. A LaTeX failure or a slow compile can't cost the candidate work that already succeeded, and they get to choose whether resumes are worth generating at all.

## Prerequisites

- `context/profile.md` must exist (run `onboard` if not).
- A LaTeX engine on PATH — `tectonic` or `pdflatex`. If neither is found, try `brew install tectonic`. If that fails, say so and stop; this skill can't do anything without one.
- No `.env` or connections check needed — this touches no external service, only local files.

## Step 1 — Figure out which mode

**From a search** (default): read `outputs/scored.json`. If it's missing, say so and suggest running a search first.

**From a pasted JD**: skip to Step 4.

## Step 2 — Show the options

List the postings scoring above `resume_tailoring_min_score` (from `configs/search.json`, default 60) compactly — score, title, company. Then let them choose:

1. **All** above the threshold
2. **Top N** — "top 5"
3. **Above a different bar** — "anything over 75"
4. **Specific ones** — by company or title
5. **A pasted JD instead** — a role found anywhere (Step 4)

Show the count before generating if it's large: *"That's 18 postings — 18 PDFs. Go ahead?"* Don't compile dozens of documents without a beat.

## Step 3 — Generate

```
python scripts/generate_resumes.py \
  --config configs/search.json \
  --profile context/profile.md \
  --scored-in outputs/scored.json \
  --template templates/resume_template.tex \
  --out-dir outputs/tailored_resumes \
  --only-posting-ids <ids>
```

- Pass `--only-posting-ids` with the `posting_id`s of whatever they picked. **This bypasses the score threshold** — an explicit choice beats the configured minimum, which is what makes options 3–5 work.
- Omit the flag only for option 1 (all above threshold), where the script's own filter is exactly right.

Output lands in `outputs/tailored_resumes/<YYYY-MM>/<YYYY-MM-DD>/`, with the intermediate `.tex` in that day's `tex/` subfolder.

## Step 4 — Pasted JD path

For a role found outside this pipeline entirely:

1. Ask for the JD text (and company + title if not obvious from it). Save the text to a file — `outputs/manual_jd.txt` is fine.
2. Run:
```
python scripts/make_manual_posting.py \
  --config configs/search.json \
  --jd-file outputs/manual_jd.txt \
  --company "<company>" --title "<title>" \
  --out outputs/manual_posting.json
```
   This scores the JD with the same rules the pipeline uses everywhere else and prints the match score plus the `posting_id`.
3. **Report the score honestly before generating.** If it comes back low, say so — *"This JD matches 45% of your profile; the gaps are Airflow and dbt. Still want the resume?"* A low score is useful information, not something to paper over.
4. Generate with `--scored-in outputs/manual_posting.json --only-posting-ids <the id from step 2>`.

Manual-JD resumes are **not** written to the job-postings sheet — they didn't come from a search, and adding them would corrupt the record of what each day's search actually found.

## Step 5 — Report

Name the count and where they landed. If any failed to compile, say which and why — don't report a clean success when some didn't build:

> *"Generated 5 resumes → outputs/tailored_resumes/2026-08/2026-08-18/. One failed (Acme Corp — LaTeX error in the company name escaping); the other four are ready."*
