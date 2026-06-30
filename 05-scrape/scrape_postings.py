"""Scrape postings from the public JSON APIs of Ashby / Greenhouse / Lever.

These three ATSes expose every company's open postings via simple GET endpoints
that need no auth. We pull JSON, normalise to a common row shape, and write
postings.csv.

Tomorrow's pass can add Playwright for the messier sources.
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import COMPANIES_WITH_ATS, POSTINGS

COMPANIES_CSV = COMPANIES_WITH_ATS
POSTINGS_CSV = POSTINGS

# --- Role keyword tags (broad, multi-tag per posting) ---
ROLE_TAGS = {
    "data": re.compile(
        r"\b(data engineer|data engineering|data platform|data infrastructure|data infra|"
        r"etl|elt|pipeline|airflow|spark|dbt|analytics engineer|bi engineer|data architect|"
        r"data ops|dataops|warehouse|lakehouse)\b", re.I),
    "ai-ml": re.compile(
        r"\b(machine learning|ml engineer|ml platform|ml ops|mlops|ai engineer|ai platform|"
        r"applied (?:ai|ml|scientist|research)|llm|nlp|computer vision|deep learning|"
        r"ai/ml|ai researcher|research engineer|research scientist|foundation model)\b", re.I),
    "backend": re.compile(
        r"\b(backend|back[- ]end|server[- ]?side|api engineer|api developer|"
        r"distributed systems|systems engineer)\b", re.I),
    "fullstack": re.compile(r"\b(full[- ]?stack|fullstack)\b", re.I),
    "software": re.compile(r"\b(software engineer|software developer|swe|sde)\b", re.I),
    "fde": re.compile(
        r"\b(forward[- ]deployed|fde|solutions engineer|deployment engineer|"
        r"field engineer|implementation engineer|customer engineer|sales engineer|"
        r"applications engineer|professional services engineer)\b", re.I),
    "early-career": re.compile(
        r"\b(intern|internship|junior|new grad|entry[- ]level|graduate|"
        r"associate engineer|trainee|fresher|early career|early[- ]career|"
        r"university|university grad|grad program)\b", re.I),
    "infra": re.compile(
        r"\b(infrastructure engineer|platform engineer|site reliability|sre|"
        r"devops|cloud engineer|cloud architect|production engineer|"
        r"kubernetes|terraform)\b", re.I),
    "frontend": re.compile(
        r"\b(front[- ]?end|frontend|ui engineer|ux engineer|web engineer|"
        r"react engineer|design engineer)\b", re.I),
    "security": re.compile(
        r"\b(security engineer|security analyst|appsec|application security|"
        r"infosec|penetration test|red team|blue team|product security)\b", re.I),
}

# --- Geo tags ---
GEO_TAGS = {
    "India": re.compile(r"\b(india|bengaluru|bangalore|mumbai|delhi|hyderabad|gurgaon|gurugram|pune|noida|chennai)\b", re.I),
    "Remote": re.compile(r"\b(remote|work from anywhere|distributed|anywhere)\b", re.I),
    "US": re.compile(r"\b(united states|usa|new york|nyc|san francisco|^sf$|seattle|austin|boston|chicago|denver|los angeles|palo alto)\b", re.I),
    "Europe": re.compile(r"\b(berlin|london|amsterdam|dublin|switzerland|zurich|paris|munich|stockholm|copenhagen|barcelona|madrid|bratislava|prague)\b", re.I),
    "Japan": re.compile(r"\b(japan|tokyo|osaka|kyoto)\b", re.I),
}


@dataclass
class Posting:
    source_company: str       # Company the source belongs to
    source_url: str           # The career-page tab URL we started from
    posting_id: str
    posting_title: str
    department: str
    location: str
    employment_type: str
    published_at: str
    apply_url: str
    role_tags: str            # semicolon-separated, e.g. "data;backend"
    geo_tags: str             # semicolon-separated
    ats: str                  # Ashby / Greenhouse / Lever
    raw: str                  # truncated raw JSON for debugging


def tag_role(title: str, dept: str = "") -> str:
    haystack = f"{title} {dept}"
    hits = [tag for tag, pat in ROLE_TAGS.items() if pat.search(haystack)]
    return ";".join(hits)


def tag_geo(location: str) -> str:
    hits = [tag for tag, pat in GEO_TAGS.items() if pat.search(location)]
    return ";".join(hits)


def fetch_json(url: str, *, timeout: int = 15) -> dict | list | None:
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "job-hunt/0.1"})
        if r.status_code != 200:
            print(f"  [http {r.status_code}] {url}")
            return None
        return r.json()
    except Exception as e:
        print(f"  [error] {url}: {e}")
        return None


def scrape_ashby(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    api = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    data = fetch_json(api)
    if not data or "jobs" not in data:
        return
    for j in data["jobs"]:
        title = j.get("title", "")
        dept = j.get("departmentName", "") or ""
        location = j.get("locationName", "") or ""
        yield Posting(
            source_company=source_company,
            source_url=source_url,
            posting_id=str(j.get("id", "")),
            posting_title=title,
            department=dept,
            location=location,
            employment_type=j.get("employmentType", "") or "",
            published_at=j.get("publishedAt", "") or "",
            apply_url=j.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{slug}/{j.get('id', '')}",
            role_tags=tag_role(title, dept),
            geo_tags=tag_geo(location),
            ats="Ashby",
            raw=json.dumps(j)[:400],
        )


def scrape_greenhouse(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    api = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false"
    data = fetch_json(api)
    if not data or "jobs" not in data:
        return
    for j in data["jobs"]:
        title = j.get("title", "")
        depts = j.get("departments") or []
        dept = ", ".join(d.get("name", "") for d in depts if isinstance(d, dict))
        location = (j.get("location") or {}).get("name", "") if isinstance(j.get("location"), dict) else ""
        yield Posting(
            source_company=source_company,
            source_url=source_url,
            posting_id=str(j.get("id", "")),
            posting_title=title,
            department=dept,
            location=location,
            employment_type="",
            published_at=j.get("updated_at", "") or "",
            apply_url=j.get("absolute_url", "") or "",
            role_tags=tag_role(title, dept),
            geo_tags=tag_geo(location),
            ats="Greenhouse",
            raw=json.dumps(j)[:400],
        )


def scrape_lever(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    api = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = fetch_json(api)
    if not isinstance(data, list):
        return
    for j in data:
        title = j.get("text", "")
        cats = j.get("categories") or {}
        dept = cats.get("team", "") or ""
        location = cats.get("location", "") or ""
        yield Posting(
            source_company=source_company,
            source_url=source_url,
            posting_id=str(j.get("id", "")),
            posting_title=title,
            department=dept,
            location=location,
            employment_type=cats.get("commitment", "") or "",
            published_at=str(j.get("createdAt", "")),
            apply_url=j.get("hostedUrl", "") or "",
            role_tags=tag_role(title, dept),
            geo_tags=tag_geo(location),
            ats="Lever",
            raw=json.dumps(j)[:400],
        )


def scrape_workable(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    api = f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    data = fetch_json(api)
    if not isinstance(data, dict) or not data.get("jobs"):
        return
    for j in data["jobs"]:
        title = j.get("title", "") or ""
        dept = j.get("department", "") or ""
        location = j.get("location", "") or ""
        shortcode = j.get("shortcode", "") or ""
        apply_url = j.get("url") or (f"https://apply.workable.com/{slug}/j/{shortcode}/" if shortcode else "")
        yield Posting(
            source_company=source_company,
            source_url=source_url,
            posting_id=str(j.get("id", shortcode)),
            posting_title=title,
            department=dept,
            location=location,
            employment_type=j.get("type", "") or "",
            published_at=j.get("published_at", "") or j.get("created_at", "") or "",
            apply_url=apply_url,
            role_tags=tag_role(title, dept),
            geo_tags=tag_geo(location),
            ats="Workable",
            raw=json.dumps(j)[:400],
        )


def scrape_smartrecruiters(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    # SmartRecruiters paginates by offset; pull up to 500 postings per company
    seen = 0
    offset = 0
    limit = 100
    while seen < 500:
        api = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit={limit}&offset={offset}"
        data = fetch_json(api)
        if not isinstance(data, dict):
            return
        content = data.get("content") or []
        if not content:
            return
        for j in content:
            title = j.get("name", "") or ""
            dept = (j.get("department") or {}).get("label", "") or ""
            loc = j.get("location") or {}
            location_parts = [loc.get(k, "") for k in ("city", "region", "country") if loc.get(k)]
            location = ", ".join(location_parts)
            yield Posting(
                source_company=source_company,
                source_url=source_url,
                posting_id=str(j.get("id", "")),
                posting_title=title,
                department=dept,
                location=location,
                employment_type=(j.get("typeOfEmployment") or {}).get("label", "") or "",
                published_at=j.get("releasedDate", "") or j.get("createdOn", "") or "",
                apply_url=j.get("applyUrl", "") or f"https://careers.smartrecruiters.com/{slug}/{j.get('id', '')}",
                role_tags=tag_role(title, dept),
                geo_tags=tag_geo(location),
                ats="SmartRecruiters",
                raw=json.dumps(j)[:400],
            )
        seen += len(content)
        if len(content) < limit:
            return
        offset += limit


def scrape_recruitee(slug: str, source_company: str, source_url: str) -> Iterable[Posting]:
    api = f"https://{slug}.recruitee.com/api/offers"
    data = fetch_json(api)
    if not isinstance(data, dict) or not data.get("offers"):
        return
    for j in data["offers"]:
        title = j.get("title", "") or j.get("sharing_title", "") or ""
        dept = j.get("department", "") or ""
        location = j.get("location", "") or j.get("city", "") or ""
        if not location and j.get("country_code"):
            location = j["country_code"]
        yield Posting(
            source_company=source_company,
            source_url=source_url,
            posting_id=str(j.get("id", "")),
            posting_title=title,
            department=dept,
            location=location,
            employment_type=j.get("employment_type_code", "") or j.get("position_type", "") or "",
            published_at=j.get("published_at", "") or j.get("created_at", "") or "",
            apply_url=j.get("careers_apply_url") or j.get("careers_url") or "",
            role_tags=tag_role(title, dept),
            geo_tags=tag_geo(location),
            ats="Recruitee",
            raw=json.dumps(j)[:400],
        )


def load_companies() -> list[dict]:
    """Load discovered companies (with ats + ats_slug columns) from 04-discover output."""
    with COMPANIES_CSV.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main() -> None:
    rows = load_companies()
    targets: list[tuple[str, str, str, str]] = []  # (ats, slug, company, source_url)

    # Workable dropped: requires account creation per company (terrible apply UX)
    # + their Cloudflare protection blocks our probe rate anyway.
    supported = {"Ashby", "Greenhouse", "Lever", "SmartRecruiters", "Recruitee"}
    for r in rows:
        ats = (r.get("ats") or "").strip()
        slug = (r.get("ats_slug") or "").strip()
        if ats in supported and slug:
            targets.append((ats, slug, r.get("company_name") or r.get("company", ""),
                             r.get("source_url", "")))

    # De-dup by (ats, slug)
    seen = set()
    uniq_targets = []
    for t in targets:
        key = (t[0], t[1].lower())
        if key in seen:
            continue
        seen.add(key)
        uniq_targets.append(t)

    print(f"Will scrape {len(uniq_targets)} ATS targets in parallel (16 threads)")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from threading import Lock

    scrapers = {
        "Ashby": scrape_ashby,
        "Greenhouse": scrape_greenhouse,
        "Lever": scrape_lever,
        "SmartRecruiters": scrape_smartrecruiters,
        "Recruitee": scrape_recruitee,
    }
    postings: list[Posting] = []
    fail_count = 0
    progress = {"n": 0}
    lock = Lock()
    t0 = time.time()

    def run_one(target):
        ats, slug, company, url = target
        out: list[Posting] = []
        try:
            for p in scrapers[ats](slug, company, url):
                out.append(p)
        except Exception as e:
            return target, [], str(e)
        return target, out, None

    with ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(run_one, t) for t in uniq_targets]
        for fut in as_completed(futs):
            target, out, err = fut.result()
            with lock:
                progress["n"] += 1
                postings.extend(out)
                if not out and err is None:
                    fail_count += 1
                if err:
                    fail_count += 1
                if progress["n"] % 100 == 0:
                    elapsed = time.time() - t0
                    rate = progress["n"] / elapsed if elapsed else 0
                    print(f"  {progress['n']:>4d}/{len(uniq_targets)} done, "
                          f"{len(postings)} postings so far, {rate:.1f} co/s, "
                          f"ETA {(len(uniq_targets)-progress['n'])/rate:.0f}s")

    print(f"\nScraped {len(postings)} postings; {fail_count} targets returned 0 postings.")
    if not postings:
        return

    if not postings:
        print("\nNo postings fetched.")
        return

    fieldnames = list(asdict(postings[0]).keys())
    with POSTINGS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in postings:
            writer.writerow(asdict(p))

    print(f"\nWrote {len(postings)} postings to {POSTINGS_CSV}")

    # Summary — encode-safe printing so cp1252 stdout doesn't choke on emoji
    # in scraped company names (e.g. some startups have heart/money emojis).
    def safe(s: str) -> str:
        try:
            return s.encode("ascii", "replace").decode("ascii")
        except Exception:
            return repr(s)

    from collections import Counter
    by_company = Counter(p.source_company for p in postings)
    by_ats = Counter(p.ats for p in postings)
    role_count = Counter()
    for p in postings:
        for tag in p.role_tags.split(";"):
            if tag:
                role_count[tag] += 1
    print("\nTop 25 companies by posting count:")
    for k, v in by_company.most_common(25):
        print(f"  {safe(k):25s} {v}")
    print("\nBy ATS:")
    for k, v in by_ats.most_common():
        print(f"  {k:11s} {v}")
    print("\nRole tag hits (across all postings, multi-tagged):")
    for k, v in role_count.most_common():
        print(f"  {k:13s} {v}")
    matched = sum(1 for p in postings if p.role_tags)
    print(f"\n{matched}/{len(postings)} postings have at least one role-tag match.")


if __name__ == "__main__":
    main()
