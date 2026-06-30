"""Merge all seed sources + the tab catalog into one deduped companies.csv.

Output columns:
  company_name       canonical display name
  slug_candidates    semicolon-separated; first one used for ATS probes, fallbacks tried in order
  website            canonical website (when known)
  source             yc | a16z | tabs | wordlist | sequoia | accel | ...
  is_hiring          true/false (best signal we have — YC has this, others don't)
  industry           free-text (industries + tags joined)
  location           "all_locations" when known
  batch              YC batch / a16z year
  ats                blank now; populated by discover_ats.py
  ats_slug           blank now; populated by discover_ats.py
  source_url         where we found this company (tab URL, VC permalink, etc.)
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import (YC_JSON, A16Z_JSON, VC_PORTFOLIOS_DIR, WORDLIST,
                   TABS_CATALOG, COMPANIES)


def slugify(name: str) -> str:
    """Lowercase, alphanumeric + hyphens. Used for ATS slug guessing."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def variants(name: str) -> list[str]:
    """All slug variants worth trying on an ATS for this name."""
    if not name:
        return []
    name = name.strip()
    base = slugify(name)
    nospace = re.sub(r"[^a-z0-9]+", "", name.lower())
    candidates = [
        base,
        nospace,
        base.replace("-", ""),
        base.replace("-ai", "ai"),
        base.replace("-labs", ""),
        base.replace("-inc", ""),
        base.replace("-com", ""),
        base.replace("-io", ""),
        # Common suffix variants seen on ATS boards
        f"{base}-hq",
        f"{base}-co",
        f"{base}-labs",
        f"{base}-team",
        f"{nospace}hq",
        f"{nospace}co",
        f"{nospace}labs",
    ]
    out: list[str] = []
    for s in candidates:
        if s and s not in out:
            out.append(s)
    return out


def website_from(raw: str | None) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw


def root_domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0] if host else ""


def _unwrap(blob):
    """Seed JSON shape v2: {fetched_at, count, companies: [...]} — fall through if v1 (raw list)."""
    if isinstance(blob, dict) and "companies" in blob:
        return blob["companies"]
    return blob


def from_yc() -> list[dict]:
    if not YC_JSON.exists():
        return []
    data = _unwrap(json.loads(YC_JSON.read_text(encoding="utf-8")))
    rows = []
    for c in data:
        name = c.get("name") or ""
        website = website_from(c.get("website"))
        rd = root_domain(website)
        slug_cands = variants(name)
        if rd and rd not in slug_cands:
            slug_cands.insert(0, rd)
        rows.append({
            "company_name": name,
            "slug_candidates": ";".join(slug_cands[:5]),
            "website": website,
            "source": "yc",
            "is_hiring": "true" if (c.get("isHiring") or c.get("is_hiring")) else "false",
            "industry": "; ".join(c.get("industries") or []) or c.get("industry") or "",
            "location": c.get("all_locations") or "",
            "batch": c.get("batch") or "",
            "ats": "",
            "ats_slug": "",
            "source_url": f"https://www.ycombinator.com/companies/{c.get('slug', '')}",
        })
    return rows


def from_a16z() -> list[dict]:
    if not A16Z_JSON.exists():
        return []
    data = _unwrap(json.loads(A16Z_JSON.read_text(encoding="utf-8")))
    rows = []
    for c in data:
        name = c.get("title") or c.get("name") or ""
        website = website_from(c.get("web") or c.get("url"))
        rd = root_domain(website)
        slug_cands = variants(name)
        if rd and rd not in slug_cands:
            slug_cands.insert(0, rd)
        rows.append({
            "company_name": name,
            "slug_candidates": ";".join(slug_cands[:5]),
            "website": website,
            "source": "a16z",
            "is_hiring": "",
            "industry": "; ".join(c.get("stages") or []),
            "location": "",
            "batch": str(c.get("year_founded") or ""),
            "ats": "",
            "ats_slug": "",
            "source_url": f"https://a16z.com/companies/{slugify(name)}/",
        })
    return rows


def from_tabs() -> list[dict]:
    if not TABS_CATALOG.exists():
        return []
    rows = []
    with TABS_CATALOG.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tab_type = r.get("tab_type", "")
            if tab_type in ("unrelated", "search-result", "reference-research"):
                continue
            name = r.get("company") or ""
            website = website_from(r.get("url"))
            rd = root_domain(website)
            slug_cands = variants(name)
            if rd and rd not in slug_cands:
                slug_cands.insert(0, rd)
            # If the tab already pointed at an ATS, we know the slug — set it
            ats = r.get("ats_platform", "")
            ats_slug = ""
            url = r.get("url", "")
            p = urlparse(url)
            host = p.netloc.lower()
            path_parts = [s for s in p.path.strip("/").split("/") if s]
            if ats == "Ashby" and "ashbyhq.com" in host and path_parts:
                ats_slug = path_parts[0]
            elif ats == "Greenhouse" and "greenhouse.io" in host and path_parts:
                ats_slug = path_parts[0]
            elif ats == "Lever" and "lever.co" in host and path_parts:
                ats_slug = path_parts[0]
            rows.append({
                "company_name": name,
                "slug_candidates": ";".join(slug_cands[:5]),
                "website": website,
                "source": "tabs",
                "is_hiring": "",
                "industry": "",
                "location": r.get("geo_hint", ""),
                "batch": "",
                "ats": ats if ats in ("Ashby", "Greenhouse", "Lever") else "",
                "ats_slug": ats_slug,
                "source_url": url,
            })
    return rows


def from_wordlist() -> list[dict]:
    if not WORDLIST.exists():
        return []
    rows = []
    for line in WORDLIST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append({
            "company_name": line,
            "slug_candidates": ";".join(variants(line)[:5]),
            "website": "",
            "source": "wordlist",
            "is_hiring": "",
            "industry": "",
            "location": "",
            "batch": "",
            "ats": "",
            "ats_slug": "",
            "source_url": "",
        })
    return rows


def main() -> None:
    yc = from_yc()
    a16z = from_a16z()
    tabs = from_tabs()
    wl = from_wordlist()
    print(f"YC: {len(yc)}  a16z: {len(a16z)}  tabs: {len(tabs)}  wordlist: {len(wl)}")

    # Merge with dedup by primary slug candidate (or company_name lowercased)
    merged: dict[str, dict] = {}
    # Priority: tabs (we may already know ATS) > yc (has hiring flag) > a16z > wordlist
    for source_rows in (tabs, yc, a16z, wl):
        for r in source_rows:
            key = (r["slug_candidates"].split(";")[0] if r["slug_candidates"]
                   else r["company_name"].lower())
            if not key:
                continue
            existing = merged.get(key)
            if existing is None:
                merged[key] = r
            else:
                # Merge: prefer non-empty fields, append source
                for col in r:
                    if not existing.get(col) and r.get(col):
                        existing[col] = r[col]
                # Track multi-source provenance
                if r["source"] not in existing["source"].split(","):
                    existing["source"] += f",{r['source']}"

    rows = list(merged.values())
    print(f"Deduped to {len(rows)} unique companies")

    fieldnames = ["company_name", "slug_candidates", "website", "source",
                  "is_hiring", "industry", "location", "batch",
                  "ats", "ats_slug", "source_url"]
    with COMPANIES.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {COMPANIES}")

    # Stats
    from collections import Counter
    sources = Counter()
    for r in rows:
        for s in r["source"].split(","):
            sources[s] += 1
    print("\nBy source (multi-counted when company appears in multiple lists):")
    for k, v in sources.most_common():
        print(f"  {k:10s} {v}")
    hiring = sum(1 for r in rows if r["is_hiring"] == "true")
    has_ats = sum(1 for r in rows if r["ats_slug"])
    print(f"\nMarked hiring (YC signal only): {hiring}")
    print(f"Already have known ATS slug: {has_ats}")


if __name__ == "__main__":
    main()
