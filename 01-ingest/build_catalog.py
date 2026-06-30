"""Parse the exported tab-groups JSON into a classified CSV catalog."""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import TABS_JSON, TABS_SAMPLE, TABS_CATALOG

# Use your own export if present (01-ingest/tabs.json), else the shipped sample.
JSON_PATH = TABS_JSON if TABS_JSON.exists() else TABS_SAMPLE
CSV_PATH = TABS_CATALOG

# Known ATS / job-board host fragments -> platform label
ATS_HOSTS = {
    "greenhouse.io": "Greenhouse",
    "job-boards.greenhouse.io": "Greenhouse",
    "boards.greenhouse.io": "Greenhouse",
    "lever.co": "Lever",
    "jobs.lever.co": "Lever",
    "ashbyhq.com": "Ashby",
    "jobs.ashbyhq.com": "Ashby",
    "breezy.hr": "Breezy",
    "workday": "Workday",
    "myworkdayjobs.com": "Workday",
    "successfactors.com": "SuccessFactors",
    "successfactors": "SuccessFactors",
    "oraclecloud.com": "Oracle HCM",
    "keka.com": "Keka",
    "recruiteecdn.com": "Recruitee",
    "recruiterflow.com": "RecruiterFlow",
    "phenompeople.com": "Phenom",
    "jibecdn.com": "Jibe",
    "homerun.co": "Homerun",
    "rebolt.ai": "Rebolt",
    "airtable.com": "Airtable form",
    "tally.so": "Tally form",
    "notion.site": "Notion page",
    "coda.io": "Coda doc",
}

# Aggregator / job-board domains (real job aggregators only)
AGGREGATORS = {
    "workatastartup.com": "Y Combinator WaaS",
    "remoteok.com": "RemoteOK",
    "dailyremote.com": "DailyRemote",
    "flexiple.com": "Flexiple",
    "topstartups.io": "TopStartups",
    "cutshort.io": "Cutshort",
    "shine.com": "Shine",
    "ventureloop.com": "VentureLoop",
    "geekwire.com": "GeekWire Jobs",
    "motorsportjobs.com": "MotorsportJobs",
    "dataengjobs.com": "DataEng Jobs",
    "eurotoptech.com": "EuroTopTech",
    "japan-dev.com": "Japan Dev",
    "gaijinpot.com": "GaijinPot",
    "roberthalf.com": "Robert Half",
    "thehub.io": "The Hub",
    "theantijobboard.com": "AntiJobBoard",
    "overemployed.com": "Overemployed",
    "feedinkoo.com": "Feedinkoo",
    "a16zspeedrun.com": "a16z speedrun",
}

# Reference / research tools (not job listings, not careers — kept for user reference)
REFERENCE_HOSTS = {
    "crunchbase.com": "Crunchbase",
    "startups.rip": "Startups.rip",
    "news.ycombinator.com": "Hacker News",
}

# Company homepages you're scouting that aren't a careers URL yet.
# Add your own host -> label entries here (keeps them out of the "unrelated" bucket).
SCOUTING_HOSTS: dict[str, str] = {}

TYPE_REFERENCE = "reference-research"
TYPE_SCOUTING = "company-landing-page"

# Geo hints from URL or title fragments
GEO_PATTERNS = [
    (re.compile(r"japan|gaijin|tokyo|osaka|kyoto|/jp/", re.I), "Japan"),
    (re.compile(r"/eu/|europe|berlin|london|amsterdam|dublin|paris|munich|zurich", re.I), "Europe"),
    (re.compile(r"/us/|/usa|new.?york|nyc|san.?francisco|seattle|austin|boston", re.I), "US"),
    (re.compile(r"india|\.in[/?]|bengaluru|bangalore|mumbai|delhi|hyderabad|pune", re.I), "India"),
    (re.compile(r"remote|workfromhome|wfh", re.I), "Remote"),
]

# Tab types
TYPE_UNRELATED = "unrelated"
TYPE_SEARCH = "search-result"
TYPE_AGGREGATOR = "job-board-aggregator"
TYPE_SPECIFIC_JOB = "specific-job-posting"
TYPE_CAREER_PAGE = "company-career-page"
TYPE_REFERRAL_FORM = "referral-or-form"

UNRELATED_HOSTS = {
    "codecrafters.io",
    "whimsical.com",
    "indiaai.gov.in",
    "junegunn.github.io",  # fzf
    "greenhouse.com",      # the ATS vendor homepage, not a career page
}

# Project-specific "unrelated" URL patterns — tabs that look job-related but
# aren't (docs, launches, personal repos). Add your own noise patterns here.
UNRELATED_URL_RE = re.compile(
    r"ycombinator\.com/launches/|example\.com/ignore-me",
    re.I,
)


def classify(tab: dict) -> dict:
    url = tab.get("url", "")
    title = tab.get("title", "")
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    host_no_www = host[4:] if host.startswith("www.") else host

    # ATS / platform detection
    ats_platform = ""
    for frag, label in ATS_HOSTS.items():
        if frag in host:
            ats_platform = label
            break

    # Subdomain hints — `careers.` or `jobs.` strongly signals a careers page
    careers_subdomain = bool(re.match(r"^(careers|jobs|hiring|apply|recruit)\.", host_no_www))

    # Tab type
    if UNRELATED_URL_RE.search(url) or host_no_www in UNRELATED_HOSTS:
        tab_type = TYPE_UNRELATED
    elif "google.com/search" in url:
        tab_type = TYPE_SEARCH
    elif host_no_www in REFERENCE_HOSTS:
        tab_type = TYPE_REFERENCE
    elif host_no_www in AGGREGATORS or any(a == host_no_www for a in AGGREGATORS):
        tab_type = TYPE_AGGREGATOR
    elif ats_platform and ats_platform in {"Tally form", "Airtable form", "Notion page", "Coda doc"}:
        tab_type = TYPE_REFERRAL_FORM
    elif ats_platform:
        if re.search(r"/job/|gh_jid=|jid=|/jobs/\d+|/posting/", url, re.I):
            tab_type = TYPE_SPECIFIC_JOB
        else:
            tab_type = TYPE_CAREER_PAGE
    elif careers_subdomain:
        tab_type = TYPE_CAREER_PAGE
    else:
        path = parsed.path.lower()
        if any(k in path for k in ("/career", "/careers", "/explore-jobs", "/job-search", "/jobs", "/hiring", "/open-roles", "/it-opportunities")):
            tab_type = TYPE_CAREER_PAGE
        elif host_no_www in SCOUTING_HOSTS:
            tab_type = TYPE_SCOUTING
        elif "career" in title.lower() or "hiring" in title.lower() or ("jobs" in title.lower() and "github" not in host_no_www):
            tab_type = TYPE_CAREER_PAGE
        else:
            tab_type = TYPE_UNRELATED

    # Company guess
    company = guess_company(host_no_www, title, url, tab_type)

    # Geo hint
    geo = ""
    haystack = f"{url} {title}"
    for pat, label in GEO_PATTERNS:
        if pat.search(haystack):
            geo = label
            break

    return {
        "title": title,
        "url": url,
        "domain": host_no_www,
        "company": company,
        "tab_type": tab_type,
        "ats_platform": ats_platform,
        "geo_hint": geo,
        "notes": "",
    }


def guess_company(host_no_www: str, title: str, url: str, tab_type: str) -> str:
    """Best-effort company name from host / title."""
    if tab_type == TYPE_AGGREGATOR:
        # Use aggregator label
        if host_no_www in AGGREGATORS:
            return AGGREGATORS[host_no_www]
        for h, lbl in AGGREGATORS.items():
            if h in host_no_www:
                return lbl

    # ATS-hosted pages: company is in the path (jobs.ashbyhq.com/parallel) or subdomain
    parsed = urlparse(url)
    if "ashbyhq.com" in host_no_www or "lever.co" in host_no_www or "greenhouse.io" in host_no_www:
        seg = parsed.path.strip("/").split("/")
        if seg and seg[0]:
            return seg[0].replace("-", " ").title()
    if "breezy.hr" in host_no_www:
        sub = host_no_www.split(".")[0]
        return sub.title()
    if "keka.com" in host_no_www:
        sub = host_no_www.split(".")[0]
        return sub.title()
    if "successfactors" in host_no_www or "successfactors.com" in host_no_www:
        # some SuccessFactors tenants put the company in the subdomain, else title
        sub = host_no_www.split(".")[0]
        if sub in ("careers", "rmkcdn"):
            # Fall back to title
            m = re.search(r"\|\s*([A-Z][A-Za-z .&]+)$", title)
            if m:
                return m.group(1).strip()
        return sub.title()
    if "oraclecloud.com" in host_no_www:
        m = re.search(r"^([A-Za-z .&]+) Careers", title)
        if m:
            return m.group(1).strip()
    if "recruiteecdn.com" in host_no_www or "recruiterflow.com" in host_no_www:
        m = re.search(r"at\s+([A-Z][A-Za-z0-9 .&]+)", title)
        if m:
            return m.group(1).strip()
    if "phenompeople.com" in host_no_www:
        m = re.search(r"Careers at\s+([A-Z][A-Za-z0-9 .&]+)", title)
        if m:
            return m.group(1).strip()

    # Default: company = root domain second-level
    parts = host_no_www.split(".")
    if len(parts) >= 2:
        return parts[-2].replace("-", " ").title()
    return host_no_www


def main() -> None:
    if not JSON_PATH.exists():
        print(
            f"[01-ingest] no tab export at {JSON_PATH.name} — skipping this optional stage. "
            "Drop a browser tab-groups JSON here to fold collected career pages into the seeds."
        )
        return
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    rows = []
    for group in data.get("groups", []):
        for i, tab in enumerate(group.get("tabs", []), start=1):
            row = {"index": i, "group": group.get("name", "")}
            row.update(classify(tab))
            rows.append(row)

    fieldnames = [
        "index",
        "group",
        "company",
        "tab_type",
        "ats_platform",
        "geo_hint",
        "title",
        "url",
        "domain",
        "notes",
    ]
    with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Summary to stdout
    print(f"Wrote {len(rows)} rows to {CSV_PATH}")
    from collections import Counter
    by_type = Counter(r["tab_type"] for r in rows)
    by_ats = Counter(r["ats_platform"] for r in rows if r["ats_platform"])
    by_geo = Counter(r["geo_hint"] for r in rows if r["geo_hint"])
    print("\nBy tab_type:")
    for k, v in by_type.most_common():
        print(f"  {k:28s} {v}")
    print("\nBy ATS platform (non-empty):")
    for k, v in by_ats.most_common():
        print(f"  {k:20s} {v}")
    print("\nBy geo_hint (non-empty):")
    for k, v in by_geo.most_common():
        print(f"  {k:10s} {v}")


if __name__ == "__main__":
    main()
