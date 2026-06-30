"""Shared paths for all pipeline-stage scripts.

Every script does:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from paths import *
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

INGEST = ROOT / "01-ingest"
SEEDS = ROOT / "02-seeds"
MERGE = ROOT / "03-merge"
DISCOVER = ROOT / "04-discover"
SCRAPE = ROOT / "05-scrape"
ASSEMBLE = ROOT / "06-assemble"

# 01-ingest
TABS_JSON = INGEST / "tabs.json"            # your own browser-tab export (gitignored)
TABS_SAMPLE = INGEST / "tabs.sample.json"   # shipped demo seed (public career pages)
TABS_CATALOG = INGEST / "tabs_catalog.csv"

# 02-seeds
YC_JSON = SEEDS / "yc_companies.json"
A16Z_JSON = SEEDS / "a16z_portfolio.json"
VC_PORTFOLIOS_DIR = SEEDS / "vc"
WORDLIST = SEEDS / "wordlist_known_cos.txt"

# 03-merge
COMPANIES = MERGE / "companies.csv"

# 04-discover
COMPANIES_WITH_ATS = DISCOVER / "companies_with_ats.csv"
DISCOVERY_LOG = DISCOVER / "discovery_log.txt"

# 05-scrape
POSTINGS = SCRAPE / "postings.csv"

# 06-assemble
XLSX = ASSEMBLE / "job-hunt.xlsx"
TRACKER_MD = ASSEMBLE / "tracker.md"
