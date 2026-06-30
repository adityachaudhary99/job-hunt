#!/usr/bin/env bash
# Runs the full job-hunt pipeline end to end (Git Bash / WSL friendly).
# Usage:
#   ./run_all.sh            # run every stage
#   ./run_all.sh --skip-seeds  # skip 02-seeds (when the YC/a16z JSON is fresh enough)
#   ./run_all.sh --from 04  # start from stage 04 (re-discover + downstream)
#
# Stage 04 (discover) is the slow one (~15-20 min on first run, faster incrementally).
# Stage 05 (scrape) is ~3-5 min. Everything else is seconds.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$ROOT/.venv/Scripts/python.exe"
[[ -x "$PY" ]] || PY="$ROOT/.venv/bin/python"   # fall back for non-Windows venvs

if [[ ! -x "$PY" ]]; then
    echo "venv missing. Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

FROM="01"
SKIP_SEEDS=0
while (( $# )); do
    case "$1" in
        --skip-seeds) SKIP_SEEDS=1 ;;
        --from)       FROM="$2"; shift ;;
        -h|--help)
            sed -n '2,9p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
    shift
done

# Strip leading zero so 04 -> 4 for numeric compare
strip_zero() { echo "${1#0}"; }
FROM_N=$(strip_zero "$FROM")

run_stage() {
    local stage="$1" script="$2" label="$3"
    local stage_n; stage_n=$(strip_zero "$stage")
    if (( stage_n < FROM_N )); then
        printf '\e[90m[skip] %s  %s\e[0m\n' "$stage" "$label"
        return 0
    fi
    if (( SKIP_SEEDS == 1 )) && [[ "$stage" == "02" ]]; then
        printf '\e[90m[skip] %s  %s  (--skip-seeds)\e[0m\n' "$stage" "$label"
        return 0
    fi
    echo
    printf '\e[36m=== %s  %s ===\e[0m\n' "$stage" "$label"
    local t0=$SECONDS
    "$PY" "$ROOT/$script"
    printf '\e[32m[done] %s  %ss\e[0m\n' "$stage" "$((SECONDS - t0))"
}

wall_start=$SECONDS

run_stage "01" "01-ingest/build_catalog.py"        "ingest tabs -> tabs_catalog.csv"
run_stage "02" "02-seeds/fetch_yc.py"               "fetch YC companies"
run_stage "02" "02-seeds/fetch_a16z.py"             "fetch a16z portfolio"
run_stage "02" "02-seeds/fetch_vc_portfolios.py"    "Sequoia/Accel/Lightspeed (placeholder)"
run_stage "03" "03-merge/merge_companies.py"        "merge seeds + tabs -> companies.csv"
run_stage "04" "04-discover/discover_ats.py"        "probe Ashby/Greenhouse/Lever/SmartRecruiters/Recruitee"
run_stage "05" "05-scrape/scrape_postings.py"       "scrape every discovered ATS in parallel"
run_stage "06" "06-assemble/build_workbook.py"      "build job-hunt.xlsx + tracker.md"

# Stage 07 only runs if the bridge script is present
if [[ -f "$ROOT/07-bridge/bridge_to_evaluator.py" ]]; then
    run_stage "07" "07-bridge/bridge_to_evaluator.py" "export shortlist hand-off (-> bridge-out or HANDOFF_DIR)"
fi

echo
printf '\e[36m=== pipeline complete in %ss ===\e[0m\n' "$((SECONDS - wall_start))"
echo "Outputs:"
echo "  06-assemble/job-hunt.xlsx"
echo "  06-assemble/tracker.md"
