"""Score raw job postings against a config.

Dedupes by job link, applies title exclusions, sums skill weights for matched
skill variants found in the title or description, penalizes postings that
require more years than the candidate has, bonuses title matches against the
target roles, drops non-positive scores, sorts descending, and writes the
result to --scored-out.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TITLE_MATCH_BONUS_DEFAULT = 6
EXPERIENCE_REGEX = re.compile(r"(\d+)\s*\+?\s*(?:to\s*\d+\s*)?years?", re.IGNORECASE)


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = item.get("link") or item.get("jobUrl") or item.get("id") or json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def title_of(item: dict) -> str:
    return (item.get("title") or item.get("jobTitle") or "").strip()


def description_of(item: dict) -> str:
    return (item.get("description") or item.get("descriptionText") or item.get("descriptionHtml") or "")


def excluded_by_title(title: str, excludes: list[str]) -> bool:
    t = title.lower()
    return any(term.lower() in t for term in excludes)


def match_skills(text: str, core_skills: dict) -> tuple[int, list[str]]:
    total = 0
    matched: list[str] = []
    lowered = text.lower()
    for skill_name, spec in core_skills.items():
        weight = int(spec.get("weight", 1))
        variants = spec.get("variants", [skill_name])
        for variant in variants:
            if variant.lower() in lowered:
                total += weight
                matched.append(skill_name)
                break
    return total, matched


def title_bonus(title: str, target_roles: list[str], bonus: int) -> int:
    t = title.lower()
    return bonus if any(role.lower() in t for role in target_roles) else 0


def experience_penalty(text: str, candidate_years: int, cap: int) -> int:
    max_required = 0
    for match in EXPERIENCE_REGEX.finditer(text):
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if 0 < n <= 30 and n > max_required:
            max_required = n
    if max_required <= candidate_years:
        return 0
    gap = min(max_required - candidate_years, cap)
    return gap


def max_possible_raw_score(config: dict) -> int:
    skills = config.get("core_skills", {})
    max_skill = sum(int(spec.get("weight", 1)) for spec in skills.values())
    bonus = int(config.get("title_match_bonus", TITLE_MATCH_BONUS_DEFAULT))
    return max(1, max_skill + bonus)


def normalize_score(raw: int, max_raw: int) -> int:
    return max(0, min(100, round(raw / max_raw * 100)))


def score_item(item: dict, config: dict, max_raw: int) -> dict | None:
    title = title_of(item)
    if not title:
        return None
    if excluded_by_title(title, config.get("exclude_title_terms", [])):
        return None

    target_roles = config.get("target_roles", [])
    title_match_bonus = int(config.get("title_match_bonus", TITLE_MATCH_BONUS_DEFAULT))
    require_title_match = bool(config.get("require_title_match", False))
    bonus = title_bonus(title, target_roles, title_match_bonus)
    if require_title_match and bonus == 0:
        return None

    description = description_of(item)
    text = f"{title}\n{description}"

    skill_score, matched = match_skills(text, config.get("core_skills", {}))
    penalty = experience_penalty(
        text,
        int(config.get("experience_years", 0)),
        int(config.get("max_experience_years_penalty", 5)),
    )
    raw = skill_score + bonus - penalty
    if raw <= 0:
        return None
    normalized = normalize_score(raw, max_raw)
    if normalized < int(config.get("min_match_score", 0)):
        return None

    return {
        "match_score": normalized,
        "source": item.get("source", "LinkedIn"),
        "job_title": title,
        "company": item.get("companyName") or item.get("company") or "",
        "location": item.get("location") or "",
        "experience_required": item.get("experienceLevel") or item.get("seniorityLevel") or "",
        "seniority": item.get("seniorityLevel") or "",
        "employment_type": item.get("employmentType") or "",
        "skills_matched": ", ".join(sorted(set(matched))),
        "posted": item.get("postedTime") or item.get("postedAt") or item.get("listedAt") or "",
        "applicants": item.get("applicantsCount") or item.get("applicants") or "",
        "job_description": description,
        "apply_link": item.get("link") or item.get("jobUrl") or item.get("applyUrl") or "",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--raw-in", required=True, type=Path)
    parser.add_argument("--scored-out", required=True, type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    raw = json.loads(args.raw_in.read_text())
    if not isinstance(raw, list):
        print("ERROR: raw input must be a JSON list", file=sys.stderr)
        return 1

    deduped = dedupe(raw)
    max_raw = max_possible_raw_score(config)
    scored = [row for item in deduped if (row := score_item(item, config, max_raw))]
    scored.sort(key=lambda r: r["match_score"], reverse=True)

    args.scored_out.parent.mkdir(parents=True, exist_ok=True)
    args.scored_out.write_text(json.dumps(scored, indent=2, ensure_ascii=False))
    print(f"Scored {len(scored)} postings out of {len(deduped)} unique (of {len(raw)} raw) → {args.scored_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
