"""Fetch job postings directly from company career sites, outside LinkedIn.

Reads --config (configs/companies.json) and dispatches each company by its
"ats" field to the matching public API (Greenhouse, Lever, Workday), verified
against real endpoint responses during implementation -- not guessed. Every
result is normalized into the same raw item shape fetch_jobs.py already
produces (title/companyName/location/description*/link/postedAt/source), so
score_jobs.py needs zero changes to consume it.

Companies with no confirmed public API ("ats": "custom", or any other/unknown
value) are skipped -- logged, not fatal. A single company's fetch failing
(dead endpoint, schema drift) is also logged and skipped rather than aborting
the whole run, same fail-open-and-continue pattern fetch_jobs.py already uses
for per-listing verification.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
LEVER_URL = "https://api.lever.co/v0/postings/{org}"
WORKDAY_LIST_URL = "https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
WORKDAY_DETAIL_URL = "https://{tenant}.{shard}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{external_path}"

DEFAULT_RESULTS_PER_COMPANY = 30
WORKDAY_PAGE_SIZE = 20
REQUEST_TIMEOUT = 20


def fetch_greenhouse(company: dict, limit: int) -> list[dict]:
    url = GREENHOUSE_URL.format(token=company["token"])
    resp = requests.get(url, params={"content": "true"}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    jobs = resp.json().get("jobs", [])[:limit]

    out = []
    for j in jobs:
        out.append(
            {
                "title": j.get("title", ""),
                "companyName": company["name"],
                "location": (j.get("location") or {}).get("name", ""),
                "descriptionHtml": j.get("content", ""),
                "link": j.get("absolute_url", ""),
                "postedAt": j.get("first_published") or j.get("updated_at", ""),
                "source": f"{company['name']} Careers",
            }
        )
    return out


def fetch_lever(company: dict, limit: int) -> list[dict]:
    url = LEVER_URL.format(org=company["org"])
    resp = requests.get(url, params={"mode": "json"}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise RuntimeError(f"unexpected Lever response shape: {data}")

    out = []
    for j in data[:limit]:
        categories = j.get("categories") or {}
        # Lever doesn't always populate descriptionPlain -- some postings only have
        # the HTML `description` field. Emit both so score_jobs.py's description_of()
        # fallback chain (description -> descriptionText -> descriptionHtml) finds one.
        out.append(
            {
                "title": j.get("text", ""),
                "companyName": company["name"],
                "location": categories.get("location", ""),
                "employmentType": categories.get("commitment", ""),
                "descriptionText": j.get("descriptionPlain", ""),
                "descriptionHtml": j.get("description", ""),
                "link": j.get("hostedUrl") or j.get("applyUrl", ""),
                "postedAt": str(j.get("createdAt", "")),
                "source": f"{company['name']} Careers",
            }
        )
    return out


def fetch_workday(company: dict, limit: int) -> list[dict]:
    list_url = WORKDAY_LIST_URL.format(tenant=company["tenant"], shard=company["shard"], site=company["site"])

    postings: list[dict] = []
    offset = 0
    while len(postings) < limit:
        resp = requests.post(
            list_url,
            json={"appliedFacets": {}, "limit": WORKDAY_PAGE_SIZE, "offset": offset, "searchText": ""},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        page = data.get("jobPostings", [])
        if not page:
            break
        postings.extend(page)
        offset += WORKDAY_PAGE_SIZE
        if offset >= data.get("total", 0):
            break
    postings = postings[:limit]

    out = []
    for p in postings:
        external_path = p.get("externalPath", "")
        description = ""
        employment_type = ""
        if external_path:
            try:
                detail_url = WORKDAY_DETAIL_URL.format(
                    tenant=company["tenant"],
                    shard=company["shard"],
                    site=company["site"],
                    external_path=external_path,
                )
                detail_resp = requests.get(detail_url, timeout=REQUEST_TIMEOUT)
                detail_resp.raise_for_status()
                info = detail_resp.json().get("jobPostingInfo", {})
                description = info.get("jobDescription", "")
                employment_type = info.get("timeType", "")
                time.sleep(0.3)  # be polite -- one detail request per posting
            except requests.RequestException as exc:
                print(f"    warning: could not fetch detail for '{p.get('title')}': {exc}", file=sys.stderr)

        link = f"https://{company['tenant']}.{company['shard']}.myworkdayjobs.com/{company['site']}{external_path}"
        out.append(
            {
                "title": p.get("title", ""),
                "companyName": company["name"],
                "location": p.get("locationsText", ""),
                "descriptionHtml": description,
                "employmentType": employment_type,
                "link": link,
                "postedAt": p.get("postedOn", ""),
                "source": f"{company['name']} Careers",
            }
        )
    return out


FETCHERS = {"greenhouse": fetch_greenhouse, "lever": fetch_lever, "workday": fetch_workday}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--raw-out", required=True, type=Path)
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    companies = config.get("companies", [])
    limit = int(config.get("results_per_company", DEFAULT_RESULTS_PER_COMPANY))

    all_items: list[dict] = []
    skipped: list[str] = []
    for company in companies:
        name = company.get("name", "<unnamed>")
        ats = company.get("ats")
        fetcher = FETCHERS.get(ats)
        if fetcher is None:
            skipped.append(name)
            continue
        try:
            items = fetcher(company, limit)
            print(f"  {name}: {len(items)} postings ({ats})")
            all_items.extend(items)
        except Exception as exc:  # noqa: BLE001
            print(f"  warning: {name} ({ats}) fetch failed, skipping: {exc}", file=sys.stderr)

    args.raw_out.parent.mkdir(parents=True, exist_ok=True)
    args.raw_out.write_text(json.dumps(all_items, indent=2, ensure_ascii=False))
    fetched_companies = len(companies) - len(skipped)
    print(
        f"Wrote {len(all_items)} raw postings from {fetched_companies} companies "
        f"({len(skipped)} skipped: no confirmed API) → {args.raw_out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
