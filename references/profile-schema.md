# Profile schema and derivation rules

Shared reference for the `onboard` and `update-profile` skills. Both read and write the same two files, so the rules live here once rather than being restated (and drifting) in two skill files.

---

## 1. Resume extraction rules

When parsing a resume PDF (`pdfplumber`), extract across the **entire** document — every page, every role. Do not stop at the most recent position.

- **Full name, email, phone**
- **Location** — resolve to `{city, region, country}` using this priority order:
  1. Address line on the resume
  2. Most recent employer or education location
  3. Phone country/area code (Canadian `+1 437` → Toronto, Ontario, Canada; `+1 415` → San Francisco, California, USA)
  4. Default to `{city: "Toronto", region: "Ontario", country: "Canada"}` only if nothing else fits
- **Links** — LinkedIn, GitHub, portfolio
- **Professional summary** — write one from the overall arc of the roles if the resume has no explicit summary line
- **Every** work-history entry — title, company, location, dates, bullets, **verbatim** (not summarized)
- **Education** — degree, institution, dates
- **Certifications**
- **Skills** — the complete inventory, in **natural display form** (`Power BI`, `SQL`, `Python`), *not* the snake_case identifiers used for `core_skills` keys in the config. This matters: `generate_resumes.py` matches config keys against this list by folding case and underscores, but renders these strings as-is into the PDF — they must read like a resume, not like variable names.

  **Group them into categories** (§2 shows the shape). Use the resume's own skill headings when it has them — that's the candidate's own framing and beats any inference. Otherwise fall back to a small standard set, dropping any that come out empty:

  `Languages` · `Databases` · `BI & Visualization` · `Cloud & DevOps` · `Frameworks & Tools`

  Aim for 3–6 categories. One category holding almost everything defeats the purpose, and a dozen near-empty ones read as padding. Category names become the bold row labels on every generated resume, so they're visible to employers — **show the grouping to the candidate for confirmation** rather than locking in your inference.

  Each category is capped at `max_skill_lines` rows (default 2, ≈15 skills) when rendered. Over that, the least posting-relevant are dropped from that resume — so an overstuffed category quietly costs the candidate visibility. Splitting it is better.
- **Projects** and **Leadership/extracurricular** — only if such sections exist
- **`experience_years`** — stated, or computed from role dates

**Never invent a role, bullet, project, or certification that isn't in the source.**

---

## 2. `context/profile.md` schema

YAML frontmatter, then a short human-readable rendering of the same content (for quick reading; scripts only parse the frontmatter).

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
gmail_tracking_enabled: false   # set during onboarding's Gmail opt-in
summary: One or two sentences — who they are, what they do, what they're looking for.
skills:                # category -> list; category names are the resume's row labels
  Languages:
    - Python
    - SQL
  BI & Visualization:
    - Power BI
    - Tableau
education:
  - degree: B.Sc. Computer Science
    institution: University of Toronto
    dates: "2018 - 2022"
certifications:        # omit if none
  - name: AWS Solutions Architect – Associate
    issuer: Amazon Web Services
    date: "2026-07"
experience:
  - title: Data Analyst
    company: Acme Corp
    location: Toronto, ON
    dates: "Jan 2023 - Present"
    bullets:
      - Verbatim bullet from the resume
      - Another verbatim bullet
projects:              # omit if none
  - title: Project Name
    description: One-line description
leadership:            # omit if none
  - title: Role/Org Name
    description: One-line description
---

# Jane Doe — Profile

(short narrative mirroring the frontmatter)
```

`skills` is a **mapping of category to list**. A flat list is the older shape: `generate_resumes.py` still accepts it and renders it as a single `Skills` row, so an un-migrated profile keeps working — but it gets one row's worth of space for everything, so migrate it (`update-profile` Step 2c) when you next touch the profile.

`projects`, `leadership`, and `certifications` are optional. `generate_resumes.py` drops those resume sections entirely when absent rather than leaving placeholder headings, so omitting them is correct — not a gap to fill with invented content.

---

## 3. `configs/search.json` derivation

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
  "max_skill_lines": 2,
  "core_skills": {
    "python": {"weight": 3, "variants": ["python", "pandas", "numpy"]}
  },
  "exclude_title_terms": ["senior", "sr.", "lead", "principal", "staff", "manager", "director"],
  "max_experience_years_penalty": 5
}
```

- **`target_roles`** — 5–8 close, specific variants around the resume's focus; prefer specific over broad. **Always confirm this list with the candidate before writing it** — a resume can support several directions, and they may want to exclude roles they're qualified for but don't want, or add ones they're stretching toward.
- **`location.region_aliases`** — province spelling variants LinkedIn uses. Only affects `fetch_jobs.py`'s search-URL construction (one of its two searches is province-scoped). The scorer's own filter is **country-wide**, not province-restricted.
- **`seniority_filter_codes`** — 1=intern, 2=entry, 3=associate, 4=mid-senior, 5=director, 6=executive. Match to `experience_years`.
- **`exclude_title_terms`** — include senior/lead/principal/staff/manager/director if under 5 years' experience.
- **`core_skills`** — **flatten every skill category first**, then weight each entry by how central it is to the candidate's story. The categories are a resume-layout concern only; scoring sees one pooled set, so the config is unaffected by how skills are grouped. Keys are snake_case (`power_bi`); `variants` are the natural-language forms matched against posting text.
- **`title_match_bonus`** — default 6.
- **`min_match_score`** — default 50; below this, postings are dropped before the sheet write.
- **`resume_tailoring_min_score`** — default 60; the threshold `tailor-resumes` offers by default.
- **`max_skill_lines`** — default 2. Rows each skill category may occupy on a generated resume before the least posting-relevant entries are dropped. Raise it if a candidate genuinely needs three lines for one category; splitting the category is usually better.
- **`max_posting_age_days`** — default 7. A posting whose date can't be parsed is kept, not dropped, and counted separately in the score summary.
