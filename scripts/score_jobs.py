"""Score raw job postings against a config.

Dedupes by job link, then by normalized (company, title) to collapse the same
posting mirrored across sources (e.g. LinkedIn + a company's own careers
site), applies title exclusions, sums skill weights for matched skill
variants found in the title or description, penalizes postings that require
more years than the candidate has, bonuses title matches against the target
roles, drops non-positive scores, sorts descending, and writes the result to
--scored-out.

--raw-in accepts one or more paths (e.g. LinkedIn's raw.json and companies'
raw_companies.json) -- all are concatenated before dedup/scoring.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

TITLE_MATCH_BONUS_DEFAULT = 6
MAX_POSTING_AGE_DAYS_DEFAULT = 7
EXPERIENCE_REGEX = re.compile(r"(\d+)\s*\+?\s*(?:to\s*\d+\s*)?years?", re.IGNORECASE)
WORKDAY_RELATIVE_DATE_REGEX = re.compile(r"posted\s+(today|yesterday|(\d+)\+?\s*days?\s*ago)", re.IGNORECASE)


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


def company_of(item: dict) -> str:
    return (item.get("companyName") or item.get("company") or "").strip()


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def dedupe_cross_source(items: list[dict]) -> list[dict]:
    """Fold postings sharing a normalized (company, title) -- e.g. the same job
    mirrored on LinkedIn and a company's own careers site under a different
    link. Keeps whichever copy has the richer (longer) description. Postings
    missing a company or title can't be safely folded, so each is kept as-is."""
    by_key: dict[tuple[str, str], dict] = {}
    order: list = []
    for item in items:
        company, title = _normalize(company_of(item)), _normalize(title_of(item))
        if not company or not title:
            order.append(item)  # keep unfoldable items in place, unkeyed
            continue
        key = (company, title)
        if key not in by_key:
            by_key[key] = item
            order.append(key)
        elif len(description_of(item)) > len(description_of(by_key[key])):
            by_key[key] = item
    return [entry if isinstance(entry, dict) else by_key[entry] for entry in order]


def excluded_by_title(title: str, excludes: list[str]) -> bool:
    t = title.lower()
    return any(term.lower() in t for term in excludes)


def _word_match(needle: str, haystack: str) -> bool:
    """Word-boundary-safe containment check -- not a naive substring `in`.

    Naive substring matching is how "ON" (Ontario) used to false-positive
    match inside "London" (the "on" in "Lond-on"). \\b anchors to word edges.
    """
    if not needle:
        return False
    return re.search(rf"\b{re.escape(needle.lower())}\b", haystack) is not None


def passes_location_filter(item: dict, config: dict) -> bool:
    """Keep postings anywhere in the candidate's country, or remote-in-country.

    Country-wide, not province-restricted -- a posting in any city within
    `location.country` passes, as does a remote posting whose text mentions
    that country. `location.region`/`region_aliases` are NOT used here (they
    still drive fetch_jobs.py's LinkedIn URL construction, a separate,
    fetch-time concern). Fail-open on empty posting location so we don't drop
    rows we can't classify.
    """
    loc = config.get("location") or {}
    country = (loc.get("country") or "").strip()
    allow_remote = bool(loc.get("include_remote_in_country", True))

    if not country:
        return True

    posting_loc = (item.get("location") or "").strip().lower()
    if not posting_loc:
        return True

    if _word_match(country, posting_loc):
        return True

    if allow_remote:
        workplace = str(item.get("workplaceType") or item.get("workType") or "").lower()
        text = " ".join(
            [
                posting_loc,
                workplace,
                (item.get("title") or "").lower(),
                description_of(item).lower(),
            ]
        )
        if _word_match(country, text) and _word_match("remote", text):
            return True

    return False


def posted_at_of(item: dict) -> str:
    return str(item.get("postedTime") or item.get("postedAt") or item.get("posted") or item.get("listedAt") or "")


def posting_age_days(posted_raw: str) -> int | None:
    """Best-effort age of a posting in days, across the three date shapes this
    pipeline's sources actually produce. Returns None if undeterminable --
    callers keep (don't drop) postings with an unknown age, just count them.

    - Greenhouse: ISO 8601 (first_published/updated_at)
    - Lever: epoch milliseconds, as a numeric string (createdAt)
    - Workday: relative text ("Posted Today", "Posted 5 Days Ago", "Posted 30+ Days Ago")
    """
    raw = (posted_raw or "").strip()
    if not raw:
        return None

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        pass

    if raw.isdigit():
        try:
            dt = datetime.fromtimestamp(int(raw) / 1000, tz=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt).days)
        except (ValueError, OSError, OverflowError):
            pass

    match = WORKDAY_RELATIVE_DATE_REGEX.search(raw)
    if match:
        word = match.group(1).lower()
        if word == "today":
            return 0
        if word == "yesterday":
            return 1
        if match.group(2):
            return int(match.group(2))

    return None


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


def make_posting_id(apply_link: str, company: str, title: str, location: str, source: str) -> str:
    """Stable ID for a posting, derived from its identity, not assigned randomly
    -- the same posting produces the same ID across separate runs/days, which
    is what makes cross-sheet "new since last run" comparison possible.
    apply_link is preferred (it's already the key dedupe()/dedupe_cross_source()
    collapse on); falls back to a normalized company+title+location+source
    tuple only if a posting genuinely has no link."""
    basis = apply_link.strip().lower() or f"{company}|{title}|{location}|{source}".strip().lower()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:12]


def score_item(item: dict, config: dict, max_raw: int) -> dict | None:
    title = title_of(item)
    if not title:
        return None
    if excluded_by_title(title, config.get("exclude_title_terms", [])):
        return None
    if not passes_location_filter(item, config):
        return None

    max_age_days = int(config.get("max_posting_age_days", MAX_POSTING_AGE_DAYS_DEFAULT))
    age = posting_age_days(posted_at_of(item))
    if age is not None and age > max_age_days:
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

    company = item.get("companyName") or item.get("company") or ""
    location = item.get("location") or ""
    source = item.get("source", "LinkedIn")
    apply_link = item.get("link") or item.get("jobUrl") or item.get("applyUrl") or ""

    return {
        "match_score": normalized,
        "posting_id": make_posting_id(apply_link, company, title, location, source),
        "source": source,
        "job_title": title,
        "company": company,
        "location": location,
        "experience_required": item.get("experienceLevel") or item.get("seniorityLevel") or "",
        "seniority": item.get("seniorityLevel") or "",
        "employment_type": item.get("employmentType") or "",
        "skills_matched": ", ".join(sorted(set(matched))),
        "posted": posted_at_of(item),
        "applicants": item.get("applicantsCount") or item.get("applicants") or "",
        "job_description": description,
        "apply_link": apply_link,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--raw-in", required=True, type=Path, nargs="+")
    parser.add_argument("--scored-out", required=True, type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text())

    raw: list = []
    for raw_in in args.raw_in:
        items = json.loads(raw_in.read_text())
        if not isinstance(items, list):
            print(f"ERROR: raw input must be a JSON list: {raw_in}", file=sys.stderr)
            return 1
        raw.extend(items)

    deduped = dedupe_cross_source(dedupe(raw))
    max_raw = max_possible_raw_score(config)
    scored = [row for item in deduped if (row := score_item(item, config, max_raw))]
    scored.sort(key=lambda r: r["match_score"], reverse=True)

    posting_ids = [row["posting_id"] for row in scored]
    duplicate_ids = len(posting_ids) - len(set(posting_ids))
    if duplicate_ids:
        print(f"WARNING: {duplicate_ids} posting_id collision(s) detected among scored rows", file=sys.stderr)
    unknown_age = sum(1 for row in scored if posting_age_days(row["posted"]) is None and row["posted"])

    args.scored_out.parent.mkdir(parents=True, exist_ok=True)
    args.scored_out.write_text(json.dumps(scored, indent=2, ensure_ascii=False))
    print(
        f"Scored {len(scored)} postings out of {len(deduped)} unique (of {len(raw)} raw) → {args.scored_out} "
        f"({len(set(posting_ids))} distinct posting IDs verified, {unknown_age} had unknown post date and were kept)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
