"""Other VC portfolios — Sequoia, Accel, Lightspeed, Lightspeed India.

Tonight's probe results (2026-05-15):
  - sequoia.com/our-companies        200 but SPA-rendered; <30 companies in static HTML
  - accel.com/companies              200 but 0 /companies/ hits in static HTML — fully client-side
  - lsvp.com/companies               403 (CDN blocks plain requests)
  - lsvpindia.com                    DNS failure (domain doesn't resolve)

None are accessible via plain requests. All need Playwright with realistic
browser fingerprint. This is deferred to tomorrow's Playwright pass alongside
the non-API career-page scrapes.

This script exists so the pipeline doesn't break on its absence; it writes an
empty marker file each VC.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import VC_PORTFOLIOS_DIR


def main() -> None:
    VC_PORTFOLIOS_DIR.mkdir(parents=True, exist_ok=True)
    for vc in ("sequoia", "accel", "lightspeed", "lightspeed-india"):
        path = VC_PORTFOLIOS_DIR / f"{vc}.json"
        path.write_text(json.dumps({"vc": vc, "companies": [], "note": "deferred to Playwright pass"}), encoding="utf-8")
    print(f"Wrote 4 empty VC marker files to {VC_PORTFOLIOS_DIR}")
    print("Run via Playwright tomorrow to populate.")


if __name__ == "__main__":
    main()
