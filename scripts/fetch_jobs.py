"""Fetch LinkedIn job postings via Apify's Curious Coder scraper.

Reads a config, builds one LinkedIn search URL per target role (last 24 hours,
seniority filters applied), triggers an Apify actor run, polls until it
finishes, then writes the dataset items to --raw-out.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

APIFY_ACTOR = "curious_coder~linkedin-jobs-scraper"
APIFY_BASE = "https://api.apify.com/v2"
POLL_INTERVAL_SECONDS = 15
POLL_TIMEOUT_SECONDS = 60 * 20

LINKEDIN_GUEST_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{}"
LINKEDIN_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
# The presence of this class marks the "Apply" button on a live guest job page.
# Closed listings render an empty CTA container.
LIVE_MARKER = "top-card-layout__cta--primary"
JOB_ID_REGEX = re.compile(r"/jobs/view/[^?]*?(\d+)")


def _normalize_location(loc) -> dict:
    if isinstance(loc, str):
        return {"country": loc}
    if not isinstance(loc, dict):
        return {"country": "Canada"}
    return loc


def build_search_urls(config: dict) -> list[str]:
    loc = _normalize_location(config.get("location", {}))
    city = (loc.get("city") or "").strip()
    region = (loc.get("region") or "").strip()
    country = (loc.get("country") or "Canada").strip()
    radius_km = int(loc.get("radius_km", 100))
    include_remote = bool(loc.get("include_remote_in_country", True))

    local_parts = [p for p in (city, region, country) if p]
    local_location = ", ".join(local_parts) if local_parts else country
    distance_mi = max(1, round(radius_km * 0.621371))

    seniority_codes = config.get("seniority_filter_codes", [])
    seniority_param = ",".join(str(c) for c in seniority_codes)

    def _url(keywords: str, location: str, extra: list[str]) -> str:
        params = [
            f"keywords={quote_plus(keywords)}",
            f"location={quote_plus(location)}",
            "f_TPR=r86400",
            *extra,
        ]
        if seniority_param:
            params.append(f"f_E={seniority_param}")
        return "https://www.linkedin.com/jobs/search/?" + "&".join(params)

    urls: list[str] = []
    for role in config["target_roles"]:
        urls.append(_url(role, local_location, [f"distance={distance_mi}"]))
        if include_remote:
            urls.append(_url(role, country, ["f_WT=2"]))
    return urls


def start_run(token: str, config: dict) -> str:
    urls = build_search_urls(config)
    per_search = int(config.get("results_per_search", 50))
    payload = {
        "urls": urls,
        "count": per_search * len(urls),
        "scrapeCompany": False,
        "proxy": {"useApifyProxy": True},
    }
    resp = requests.post(
        f"{APIFY_BASE}/acts/{APIFY_ACTOR}/runs",
        params={"token": token},
        json=payload,
        timeout=90,
    )
    resp.raise_for_status()
    run = resp.json()["data"]
    print(f"Started Apify run {run['id']} against {len(urls)} search URL(s)")
    return run["id"]


def wait_for_run(token: str, run_id: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    while True:
        resp = requests.get(
            f"{APIFY_BASE}/actor-runs/{run_id}",
            params={"token": token},
            timeout=30,
        )
        resp.raise_for_status()
        run = resp.json()["data"]
        status = run["status"]
        print(f"  run {run_id} status={status}")
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            if status != "SUCCEEDED":
                raise RuntimeError(f"Apify run ended with status {status}")
            return run
        if time.time() > deadline:
            raise TimeoutError(f"Apify run {run_id} did not finish within timeout")
        time.sleep(POLL_INTERVAL_SECONDS)


def _extract_job_id(link: str) -> str | None:
    if not link:
        return None
    match = JOB_ID_REGEX.search(link)
    return match.group(1) if match else None


def _fetch_guest(session: requests.Session, job_id: str) -> requests.Response | None:
    try:
        return session.get(LINKEDIN_GUEST_URL.format(job_id), timeout=15)
    except requests.RequestException:
        return None


def _is_listing_live(job_id: str, session: requests.Session) -> bool | None:
    """True if live, False if confirmed closed, None if we couldn't tell."""
    resp = _fetch_guest(session, job_id)
    if resp is None:
        return None
    if resp.status_code == 429:
        time.sleep(30)
        resp = _fetch_guest(session, job_id)
        if resp is None or resp.status_code != 200:
            return None
    elif resp.status_code != 200:
        return None
    return LIVE_MARKER in resp.text


def filter_live_listings(items: list[dict], delay_seconds: float = 1.0) -> list[dict]:
    """Serially verify each posting is still open on LinkedIn's public guest endpoint.

    Sequential + short delay avoids most 429s; a single 30s backoff-and-retry
    handles the ones that slip through. Postings we can't verify are kept
    (fail-open) so a bad verifier network doesn't nuke the whole run.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": LINKEDIN_UA})

    kept: list[dict] = []
    dropped = 0
    unknown = 0
    for item in items:
        job_id = _extract_job_id(item.get("link") or "")
        if not job_id:
            unknown += 1
            kept.append(item)
            continue
        live = _is_listing_live(job_id, session)
        if live is False:
            dropped += 1
            continue
        if live is None:
            unknown += 1
        kept.append(item)
        time.sleep(delay_seconds)
    print(f"Verified listings: kept {len(kept)} (dropped {dropped} closed, {unknown} unknown)")
    return kept


def fetch_dataset_items(token: str, dataset_id: str) -> list[dict]:
    resp = requests.get(
        f"{APIFY_BASE}/datasets/{dataset_id}/items",
        params={"token": token, "format": "json", "clean": "true"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--raw-out", required=True, type=Path)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print("ERROR: APIFY_TOKEN not set in environment", file=sys.stderr)
        return 1

    config = json.loads(args.config.read_text())

    run_id = start_run(token, config)
    run = wait_for_run(token, run_id)
    items = fetch_dataset_items(token, run["defaultDatasetId"])
    if config.get("verify_listings", True):
        items = filter_live_listings(items)
    for item in items:
        item["source"] = "LinkedIn"

    args.raw_out.parent.mkdir(parents=True, exist_ok=True)
    args.raw_out.write_text(json.dumps(items, indent=2, ensure_ascii=False))
    print(f"Wrote {len(items)} raw postings to {args.raw_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
