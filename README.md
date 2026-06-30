# job-hunt

A 6-stage pipeline that turns **company seeds** (Y Combinator, a16z, a curated wordlist, and optionally your own saved career-page tabs) into a **ranked job-application workbook** — scored to your role / geo / seniority preferences. It hits **public ATS JSON APIs only** (Ashby, Greenhouse, Lever, SmartRecruiters, Recruitee) — no headless browser, no login, no HTML scraping.

Clone it, run it, and you get an Excel workbook whose **Shortlist** sheet is the postings most worth your time.

## Quickstart

Requires **Python 3.10+**. Ships with a sample tab set (`01-ingest/tabs.sample.json`) so it runs end to end out of the box.

```bash
git clone https://github.com/adityachaudhary99/job-hunt && cd job-hunt
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt      # Windows: .venv\Scripts\python -m pip install -r requirements.txt

./run_all.sh        # Windows: .\run_all.ps1
```

Stage 04 (ATS discovery) is the slow one — ~15–20 min on a first full run, faster on re-runs (it's incremental). The result lands at **`06-assemble/job-hunt.xlsx`**.

**Make it yours** (all optional):
- Change the company universe: edit `02-seeds/wordlist_known_cos.txt`, or add a fetcher in `02-seeds/`.
- Fold in career pages you've collected: drop a browser-tab export at `01-ingest/tabs.json` (same shape as `tabs.sample.json`). It overrides the sample and is gitignored.
- Tune what ranks highly: `ROLE_TAGS` / `GEO_TAGS` in `05-scrape/scrape_postings.py`, and `PREFERRED_ROLES` / `PRIMARY_ROLES` / `PREFERRED_GEOS` / `SENIORITY_SCORE` / `score_posting()` in `06-assemble/build_workbook.py`.

## How it works

Each stage reads the previous stage's output; all paths resolve through `paths.py`. Run the whole thing with `run_all.{sh,ps1}`, or run stages individually.

| Stage | Script | Does |
|---|---|---|
| 01 ingest *(optional)* | `01-ingest/build_catalog.py` | Classify a browser-tab export (`tabs.json`, else the bundled `tabs.sample.json`) into career-pages / aggregators / postings. Skips cleanly if neither exists. |
| 02 seeds | `02-seeds/fetch_*.py` | Pull company lists: YC (yc-oss mirror), a16z portfolio, a hand-curated wordlist |
| 03 merge | `03-merge/merge_companies.py` | Dedupe all seeds (+ optional tabs) into one master list with ~10 slug candidates each |
| 04 discover | `04-discover/discover_ats.py` | Probe 5 ATSes × top slug variants to find who's hiring (parallel, incremental) |
| 05 scrape | `05-scrape/scrape_postings.py` | Pull every posting from each discovered ATS; multi-tag by role + geo |
| 06 assemble | `06-assemble/build_workbook.py` | Dedupe + score + write the 7-sheet `job-hunt.xlsx` and a `tracker.md` |
| 07 bridge *(optional)* | `07-bridge/bridge_to_evaluator.py` | Export the shortlist as an idempotent task list for a downstream evaluator/agent (see below) |

Files like `*_companies.json`, `*.csv`, `*.xlsx`, `tracker.md`, and your `tabs.json` are **generated at runtime** (gitignored) — running the stages creates them.

## Hand-off to a downstream evaluator (optional)

The spreadsheet isn't the only output. **Stage 07** exports the Shortlist as an *idempotent* Markdown task list — `- [ ] <url> | <company> | <role> | score=X.X` under a `## Pending` heading. It's built to drop straight into **[career-ops](https://github.com/santifer/career-ops)** (an AI-powered job-search system on Claude Code) as a discovery front-end: **job-hunt finds and ranks the openings; career-ops evaluates them and tailors applications.** Re-runs skip URLs already seen (in `## Pending` or `## Processed`), so it's safe to run on a schedule against any downstream evaluator or agent.

```bash
# append up to 30 new high-score rows to the hand-off file
python 07-bridge/bridge_to_evaluator.py --limit 30 --min-score 6.0

# choose where it lands:
HANDOFF_DIR=/path/to/your/evaluator python 07-bridge/bridge_to_evaluator.py
python 07-bridge/bridge_to_evaluator.py --out ./bridge-out
```

Target dir resolution: `$HANDOFF_DIR` → `--out` → a local `./bridge-out/`. To feed [career-ops](https://github.com/santifer/career-ops), point `HANDOFF_DIR` at your career-ops checkout and it picks up `data/pipeline.md`. The hand-off is plain Markdown, so any other downstream tool works too.

## Workbook sheets

| # | Sheet | Contents |
|---|---|---|
| 1 | Catalog | All ingested browser tabs (your `tabs.json` or the sample), classified. Empty if you ran without stage 01. |
| 2 | Sources | Subset of Catalog that are real harvest targets (career pages, aggregators, referral forms) |
| 3 | Companies | Full deduped master with discovered ATS column; ATS-hit rows first |
| 4 | **Shortlist** | Top-N matched postings ranked by `score_posting()` — role + geo match + recency + YC-hiring boost + seniority fit |
| 5 | Postings (raw) | Every scraped posting, deduped by (company, title, location), newest first |
| 6 | Postings (matched) | As raw, filtered to those with at least one role-tag hit, score-ranked |
| 7 | Tracker | Empty application log (you fill rows as you apply) |

## Supported ATSes

| ATS | Endpoint | Notes |
|---|---|---|
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` | Cleanest payload |
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | Largest volume |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` | Solid |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{slug}/postings` | Paginates; non-existent slugs still return 200 — discover checks `totalFound > 0` |
| Recruitee | `{slug}.recruitee.com/api/offers` | Variable apply-URL shape |

### Dropped: Workable

Workable was probed and built end-to-end, then removed. Two reasons: its apply flow forces candidates to create a new account per company (high friction), and Cloudflare protection kicks in after moderate probing (so scraping is unreliable). The `scrape_workable()` function is kept in `05-scrape/scrape_postings.py` but unwired — revive via a real browser if ever needed.

## Role tagging

`05-scrape/scrape_postings.py` multi-tags each posting against title + department:

| Tag | Captures |
|---|---|
| `data` | data engineer, data platform, etl/elt, pipeline, airflow, spark, dbt, analytics engineer, warehouse, lakehouse |
| `ai-ml` | ml engineer, ml platform, ml ops, ai engineer, applied (ai\|ml\|scientist\|research), llm, nlp, deep learning, foundation model |
| `backend` | backend, server, api engineer, distributed systems |
| `fullstack` | full-stack |
| `software` | software engineer, swe, sde |
| `fde` | forward deployed, solutions/deployment/field/implementation/customer/sales/applications/professional-services engineer |
| `early-career` | intern, junior, new grad, entry-level, graduate, associate engineer, trainee, fresher, university grad |
| `infra` | infrastructure engineer, platform engineer, sre, devops, cloud engineer/architect, kubernetes, terraform |
| `frontend` | frontend, ui/ux engineer, web engineer, react engineer, design engineer |
| `security` | security engineer, appsec, infosec, penetration test, red/blue team |

Edit `ROLE_TAGS` in `scrape_postings.py` to tune.

## Geo tagging

Same shape, applied to the posting location:

| Tag | Captures |
|---|---|
| `India` | bengaluru/bangalore, mumbai, delhi, hyderabad, pune, noida, chennai, gurugram |
| `Remote` | remote, work from anywhere, distributed |
| `US` | usa, NYC, SF, seattle, austin, boston, chicago, denver, los angeles, palo alto |
| `Europe` | berlin, london, amsterdam, dublin, switzerland, zurich, paris, munich, stockholm, copenhagen, barcelona, madrid, bratislava, prague |
| `Japan` | japan, tokyo, osaka, kyoto |

## Shortlist scoring

`06-assemble/build_workbook.py::score_posting()` ranks each matched posting roughly −6..+11:

| Component | Range | What |
|---|---|---|
| role_match | 0..+3 | Count of preferred role tags hit |
| primary_bonus | 0..+2 | Bonus for hitting `PRIMARY_ROLES` |
| geo_match | 0..+2 | Count of preferred geo tags hit |
| recency | 0..+3 | Linear: 3.0 at today, 0 at >180 days old |
| yc_hiring | 0..+1 | +1 if company is YC + flagged `is_hiring=true` |
| seniority | −6..+1.5 | Inferred from title; defaults are tuned for an early-career candidate, so senior+ titles get penalised (see below — retune to your level) |

Top-N by score lands in the Shortlist sheet. Edit `PREFERRED_ROLES` / `PRIMARY_ROLES` / `PREFERRED_GEOS` / `SENIORITY_SCORE` / `score_posting()` to retune for your search.

### Shortlist ATS filter

`SHORTLIST_ATSES` in `06-assemble/build_workbook.py` is an allowlist deciding which ATSes are eligible for the Shortlist sheet. Postings on other ATSes still appear in **Postings (raw)** and **Postings (matched)**, just not in the Shortlist.

```python
# Default — all 5 we scrape:
SHORTLIST_ATSES = {"Ashby", "Greenhouse", "Lever", "SmartRecruiters", "Recruitee"}

# Common edits:
SHORTLIST_ATSES = {"Ashby", "Greenhouse", "Lever"}  # only the 3 with cleanest apply flows
SHORTLIST_ATSES = None                               # disable filter entirely
```

Pairs with the apply-UX rule that dropped Workable: if you want to A/B which ATSes feel best to apply through, set this tight, re-run `build_workbook.py`, and compare.

### Seniority inference (title-only)

`infer_seniority()` tags each posting with one of: `intern`, `new-grad`, `junior`, `mid`, `senior`, `staff`, `principal`, `distinguished`, `manager`, `director`, `vp`, or `""` (unmatched, assumed mid-IC). Order matters — most specific patterns first, so "Senior Staff Engineer" tags as `staff`, not `senior`.

Default scoring contributions (positive = boost, negative = penalty) — **retune `SENIORITY_SCORE` to your own experience level**:

| Seniority | Score | Rationale (default = early-career) |
|---|---|---|
| `new-grad`, `junior` | +1.5 | Best match for an early-career / new-grad candidate |
| `mid` | +0.5 | Often reachable at 1–2 YoE |
| `""` (untagged) | 0 | Most plain titles ("Software Engineer", "Data Engineer") |
| `intern` | 0 | Mostly student-only; let other signals decide |
| `senior` | −2 | 3–5+ YoE typical; sometimes flexible |
| `manager` | −3 | People management out of scope |
| `staff` | −4 | 7+ YoE typical |
| `principal`, `distinguished`, `director` | −5 | Effectively unreachable for early-career |
| `vp` | −6 | Hard exclusion |

**PhD penalty:** titles containing `PhD`, `Ph.D`, `doctorate`, or `doctoral` get an extra **−3** (`title_phd_required()`) — many ML-lab "Research Scientist/Engineer" roles gate on a PhD stated in the title.

Senior+ and PhD-tagged postings still appear in **Postings (raw)** / **(matched)** — only the Shortlist filters them out via the score.

## Adding a new source

1. Drop a fetcher in `02-seeds/` that writes `<source>_companies.json` (v2 shape `{fetched_at, source, count, companies:[…]}`).
2. Add `from_<source>()` and wire it into `main()` in `03-merge/merge_companies.py`.
3. Re-run from `merge_companies.py` onwards.

## Adding a new ATS adapter

1. **Before any code:** manually click "Apply" on a sample posting. If it forces account creation per company, stop — drop the ATS (see Workable).
2. Add a `probe_<name>()` to `04-discover/discover_ats.py` and include it in `PROBES`. It must distinguish "slug exists with jobs" from "slug missing" (some APIs return 200 for missing — check the count field).
3. Add a `scrape_<name>()` generator to `05-scrape/scrape_postings.py`; add it to the `supported` set and `scrapers` dict in `main()`.
4. Re-run discover (incremental) then scrape.

## Example run

Numbers from the author's own run — yours will differ with your seeds, filters, and the day you run it:

| Metric | Value |
|---|---|
| Companies in master list | ~6,800 (YC + a16z + wordlist) |
| Companies with a discovered ATS | ~1,400 (≈21%) |
| Postings scraped (deduped) | ~25,000 |
| Postings matching role keywords | ~6,200 (≈25%) |
| ATSes integrated | 5 (Ashby, Greenhouse, Lever, SmartRecruiters, Recruitee) |

## Roadmap

- More seed sources (Sequoia / Accel / Lightspeed portfolios — SPA-rendered, need a real browser).
- Career pages behind Workday / Phenom / Oracle HCM / custom sites (need a real browser to render).
- Aggregators (RemoteOK, YC WaaS, Japan Dev) — keyword-driven scraping.
- `https://{domain}/careers` HTML parsing for `ashby_jid` / `gh_jid` / Lever markers, to catch companies whose slug differs from their name.

## License

MIT — see [LICENSE](LICENSE).
