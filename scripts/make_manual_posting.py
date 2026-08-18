"""Turn a pasted job description into a single scored row.

For a job the candidate found anywhere -- a referral, a job board this project
doesn't scrape, an email from a recruiter. Produces a one-item file in exactly
the shape generate_resumes.py already consumes, so the tailoring path needs no
special-casing: it just gets a different --scored-in.

Scoring reuses score_jobs.py's own match_skills()/experience_penalty()/
normalize_score(), so the reported match reflects the same rules the pipeline
uses everywhere else -- not a made-up number, and not an assumed 100%. A low
score here is real information ("this JD only matches 45% of your profile"),
worth surfacing before generating anything.

The posting deliberately skips score_item()'s location/age/title filters: the
candidate explicitly asked for this one, so filters meant for bulk-scraped
listings don't apply. Pair with generate_resumes.py --only-posting-ids to
bypass the score threshold too.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from score_jobs import (  # noqa: E402
    experience_penalty,
    make_posting_id,
    match_skills,
    max_possible_raw_score,
    normalize_score,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--jd-file", required=True, type=Path, help="plain-text job description")
    parser.add_argument("--company", default="", help="company name (used in the output filename)")
    parser.add_argument("--title", default="", help="job title (used in the output filename)")
    parser.add_argument("--location", default="")
    parser.add_argument("--apply-link", default="")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    if not args.jd_file.exists():
        print(f"ERROR: JD file not found: {args.jd_file}", file=sys.stderr)
        return 1

    config = json.loads(args.config.read_text())
    description = args.jd_file.read_text()
    if not description.strip():
        print("ERROR: JD file is empty", file=sys.stderr)
        return 1

    title = args.title.strip() or "Untitled Role"
    company = args.company.strip() or "Unknown Company"
    text = f"{title}\n{description}"

    skill_score, matched = match_skills(text, config.get("core_skills", {}))
    penalty = experience_penalty(
        text,
        int(config.get("experience_years", 0)),
        int(config.get("max_experience_years_penalty", 5)),
    )
    # No title bonus: target_roles describe what we search for, and this posting
    # was chosen by hand -- rewarding an accidental title match would inflate it.
    raw = max(0, skill_score - penalty)
    normalized = normalize_score(raw, max_possible_raw_score(config))

    row = {
        "match_score": normalized,
        "posting_id": make_posting_id(args.apply_link, company, title, args.location, "Manual"),
        "source": "Manual JD",
        "job_title": title,
        "company": company,
        "location": args.location,
        "experience_required": "",
        "seniority": "",
        "employment_type": "",
        "skills_matched": ", ".join(sorted(set(matched))),
        "posted": "",
        "applicants": "",
        "job_description": description,
        "apply_link": args.apply_link,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "new_since_last_run": "",
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([row], indent=2, ensure_ascii=False))

    print(
        f"Manual posting: {title} at {company} — match score {normalized}, "
        f"posting_id {row['posting_id']}, skills matched: {row['skills_matched'] or 'none'}"
    )
    print(f"→ {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
