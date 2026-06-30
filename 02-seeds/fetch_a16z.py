"""Scrape the a16z portfolio.

Each company card on https://a16z.com/portfolio/ is rendered server-side with
its full metadata embedded as `data-company='<json>'`. Pull all of them, parse,
write to JSON.
"""
from __future__ import annotations

import datetime as _dt
import html
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import A16Z_JSON

PORTFOLIO_URL = "https://a16z.com/portfolio/"


def main() -> None:
    print(f"GET {PORTFOLIO_URL}")
    r = requests.get(PORTFOLIO_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0 job-hunt"})
    r.raise_for_status()

    # The full portfolio (800+ companies) is inlined as a JS array assigned to
    # window.a16z_portfolio_companies. Pull that array verbatim and parse.
    m = re.search(r"window\.a16z_portfolio_companies\s*=\s*(\[.*?\]);", r.text, re.DOTALL)
    if not m:
        raise SystemExit("a16z_portfolio_companies array not found — page structure changed")
    array_text = m.group(1)
    companies = json.loads(array_text)
    print(f"Parsed {len(companies)} companies from window.a16z_portfolio_companies")

    # Dedupe by id (just in case)
    seen = set()
    deduped = []
    for c in companies:
        cid = c.get("id")
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(c)

    payload = {
        "fetched_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "source": PORTFOLIO_URL,
        "count": len(deduped),
        "companies": deduped,
    }
    A16Z_JSON.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(deduped)} a16z companies to {A16Z_JSON}")

    # Stats — keys differ between the two embedded shapes (data-company attr vs
    # the array). The big array uses "title"/"web"/"stages" rather than name/url.
    has_jobs = sum(1 for c in deduped if c.get("jobs") or c.get("number_of_jobs"))
    print(f"\nWith a16z-tracked open jobs: {has_jobs}")
    if deduped:
        print(f"Sample keys: {sorted(deduped[0].keys())[:20]}")


if __name__ == "__main__":
    main()
