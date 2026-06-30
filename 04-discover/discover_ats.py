"""Discover which ATS (Ashby / Greenhouse / Lever) each company uses.

For each company in companies.csv we already have a list of slug_candidates.
For each ATS, we hit the public JSON endpoint with each candidate slug.
If we get a 200 + valid JSON, we record the hit. First hit wins.

We probe 6700+ companies × 3 ATSes × 2-3 slug variants — that's ~50k probes.
Use ThreadPoolExecutor with conservative concurrency to avoid rate limits.

Output: companies_with_ats.csv (same schema + populated `ats` and `ats_slug`).
        discovery_log.txt with summary stats.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import COMPANIES, COMPANIES_WITH_ATS, DISCOVERY_LOG

# Probe endpoints — each returns True only if the slug has >0 active postings.
# Workable was tried and dropped: Cloudflare-protects after even moderate probing,
# and their apply flow forces candidates to create an account per company.
ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
LEVER_URL = "https://api.lever.co/v0/postings/{slug}?mode=json&limit=1"
SMARTRECRUITERS_URL = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
RECRUITEE_URL = "https://{slug}.recruitee.com/api/offers"

HEADERS = {"User-Agent": "job-hunt/0.2 (educational)"}
TIMEOUT = 8
MAX_WORKERS = 30

session = requests.Session()
session.headers.update(HEADERS)


def _get_json(url: str):
    try:
        r = session.get(url, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None


def probe_ashby(slug: str) -> bool:
    data = _get_json(ASHBY_URL.format(slug=slug))
    return isinstance(data, dict) and bool(data.get("jobs"))


def probe_greenhouse(slug: str) -> bool:
    data = _get_json(GREENHOUSE_URL.format(slug=slug))
    return isinstance(data, dict) and bool(data.get("jobs"))


def probe_lever(slug: str) -> bool:
    data = _get_json(LEVER_URL.format(slug=slug))
    return isinstance(data, list) and len(data) > 0


def probe_smartrecruiters(slug: str) -> bool:
    # SmartRecruiters returns 200 for nonexistent slugs too — must check totalFound
    data = _get_json(SMARTRECRUITERS_URL.format(slug=slug))
    return isinstance(data, dict) and (data.get("totalFound") or 0) > 0


def probe_recruitee(slug: str) -> bool:
    data = _get_json(RECRUITEE_URL.format(slug=slug))
    return isinstance(data, dict) and bool(data.get("offers"))


PROBES = [
    ("Ashby", probe_ashby),
    ("Greenhouse", probe_greenhouse),
    ("Lever", probe_lever),
    ("SmartRecruiters", probe_smartrecruiters),
    ("Recruitee", probe_recruitee),
]


def discover_for_row(row: dict) -> dict:
    """Try each ATS × each slug candidate. Stop at first hit."""
    # Skip work if we already know the ATS (from the tab catalog)
    if row.get("ats") and row.get("ats_slug"):
        return row

    candidates = [s for s in row.get("slug_candidates", "").split(";") if s]
    if not candidates:
        return row

    # Try at most the top 3 slug candidates per company
    for slug in candidates[:3]:
        for ats_name, probe in PROBES:
            if probe(slug):
                row["ats"] = ats_name
                row["ats_slug"] = slug
                return row
    return row


def main() -> None:
    # Incremental: start from companies.csv (the merged master, which can grow
    # between runs if seeds/wordlist change), then carry over any prior ATS
    # discoveries from companies_with_ats.csv when keys match.
    with COMPANIES.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    fieldnames = list(rows[0].keys())
    print(f"Loaded {len(rows)} companies from {COMPANIES.name}")

    if COMPANIES_WITH_ATS.exists():
        with COMPANIES_WITH_ATS.open(encoding="utf-8") as f:
            prior = list(csv.DictReader(f))
        # Carry over ats + ats_slug onto matching companies in `rows`.
        # Match by primary slug candidate (most stable identity).
        prior_map = {(r.get("slug_candidates") or "").split(";")[0]: r for r in prior
                     if r.get("ats_slug")}
        carried = 0
        for r in rows:
            key = (r.get("slug_candidates") or "").split(";")[0]
            p = prior_map.get(key)
            if p:
                r["ats"] = p.get("ats", "")
                r["ats_slug"] = p.get("ats_slug", "")
                carried += 1
        print(f"  carried over {carried} prior ATS hits from {COMPANIES_WITH_ATS.name}")
    pre_hits = sum(1 for r in rows if r.get("ats_slug"))
    print(f"  {pre_hits} companies have an ATS before probing this run")

    print(f"Probing with {MAX_WORKERS} threads — this will take a few minutes...")
    t0 = time.time()
    results: list[dict] = [None] * len(rows)
    progress = {"n": 0, "hits": 0}
    lock = Lock()

    def worker(i_row):
        i, row = i_row
        out = discover_for_row(dict(row))
        with lock:
            progress["n"] += 1
            if out.get("ats_slug"):
                progress["hits"] += 1
            if progress["n"] % 250 == 0:
                elapsed = time.time() - t0
                rate = progress["n"] / elapsed if elapsed else 0
                print(f"  {progress['n']:>5d}/{len(rows)} done, {progress['hits']} hits, "
                      f"{rate:.1f}/s, ETA {(len(rows)-progress['n'])/rate:.0f}s")
        results[i] = out

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = [ex.submit(worker, (i, r)) for i, r in enumerate(rows)]
        for _ in as_completed(futs):
            pass

    elapsed = time.time() - t0
    hits = progress["hits"]
    print(f"\nDone in {elapsed:.0f}s. {hits} companies have an ATS slug ({100*hits/len(rows):.1f}%).")

    # Write output
    with COMPANIES_WITH_ATS.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    print(f"Wrote {COMPANIES_WITH_ATS}")

    # Discovery log
    from collections import Counter
    by_ats = Counter(r["ats"] for r in results if r.get("ats"))
    by_source_hit = Counter()
    for r in results:
        if r.get("ats"):
            for s in r.get("source", "").split(","):
                by_source_hit[s] += 1
    log = [
        f"discovery run completed in {elapsed:.0f}s",
        f"total companies probed: {len(rows)}",
        f"ATS discovered: {hits}",
        "",
        "by ATS:",
        *[f"  {k:11s} {v}" for k, v in by_ats.most_common()],
        "",
        "by source (which seed list the hit came from):",
        *[f"  {k:10s} {v}" for k, v in by_source_hit.most_common()],
    ]
    DISCOVERY_LOG.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
