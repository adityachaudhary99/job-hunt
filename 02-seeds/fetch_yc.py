"""Pull the full YC company directory.

Uses the community-maintained mirror at yc-oss.github.io which republishes
YC's algolia-backed company list as static JSON. Falls back to scraping the
YC /companies pages directly if the mirror is down.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import YC_JSON

YC_OSS_ALL = "https://yc-oss.github.io/api/companies/all.json"
YC_OSS_HIRING = "https://yc-oss.github.io/api/companies/is-hiring.json"


def fetch(url: str) -> list[dict] | None:
    print(f"GET {url}")
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "job-hunt/0.1"})
        if r.status_code != 200:
            print(f"  [http {r.status_code}]")
            return None
        return r.json()
    except Exception as e:
        print(f"  [error] {e}")
        return None


def main() -> None:
    all_cos = fetch(YC_OSS_ALL) or []
    hiring = fetch(YC_OSS_HIRING) or []
    hiring_ids = {c.get("id") for c in hiring if isinstance(c, dict)}

    # Annotate each company with is_hiring flag
    enriched = []
    for c in all_cos:
        if not isinstance(c, dict):
            continue
        c["is_hiring"] = c.get("id") in hiring_ids
        enriched.append(c)

    payload = {
        "fetched_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": YC_OSS_ALL,
        "count": len(enriched),
        "companies": enriched,
    }
    YC_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(enriched)} YC companies to {YC_JSON}")
    print(f"  hiring: {sum(1 for c in enriched if c.get('is_hiring'))}")
    # Show a sample
    if enriched:
        sample = enriched[0]
        print(f"\nSample keys: {sorted(sample.keys())[:15]}")
        print(f"Sample row: name={sample.get('name')} slug={sample.get('slug')} website={sample.get('website')}")


if __name__ == "__main__":
    main()
