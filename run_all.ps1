# Runs the full job-hunt pipeline end to end.
# Usage:
#   .\run_all.ps1            # run every stage
#   .\run_all.ps1 -SkipSeeds # skip 02-seeds (when the YC/a16z JSON is fresh enough)
#   .\run_all.ps1 -From 04   # start from stage 04 (re-discover + downstream)
#
# Stage 04 (discover) is the slow one (~15-20 min on first run, faster incrementally).
# Stage 05 (scrape) is ~3-5 min. Everything else is seconds.

param(
    [switch]$SkipSeeds,
    [string]$From = "01"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Py)) {
    Write-Error "venv missing at $Py. Run: python -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

function Run-Stage {
    param([string]$Stage, [string]$Script, [string]$Label)
    if ([int]($Stage -replace '\D','') -lt [int]($From -replace '\D','')) {
        Write-Host "[skip] $Stage  $Label" -ForegroundColor DarkGray
        return
    }
    if ($SkipSeeds -and $Stage -eq "02") {
        Write-Host "[skip] $Stage  $Label  (-SkipSeeds)" -ForegroundColor DarkGray
        return
    }
    Write-Host ""
    Write-Host "=== $Stage  $Label ===" -ForegroundColor Cyan
    $t0 = Get-Date
    & $Py (Join-Path $Root $Script)
    if ($LASTEXITCODE -ne 0) { throw "Stage $Stage failed (exit $LASTEXITCODE)" }
    $elapsed = ((Get-Date) - $t0).TotalSeconds
    Write-Host ("[done] $Stage  {0:N0}s" -f $elapsed) -ForegroundColor Green
}

$wallStart = Get-Date

Run-Stage "01" "01-ingest\build_catalog.py"          "ingest tabs -> tabs_catalog.csv"
Run-Stage "02" "02-seeds\fetch_yc.py"                 "fetch YC companies"
Run-Stage "02" "02-seeds\fetch_a16z.py"               "fetch a16z portfolio"
Run-Stage "02" "02-seeds\fetch_vc_portfolios.py"      "Sequoia/Accel/Lightspeed (placeholder)"
Run-Stage "03" "03-merge\merge_companies.py"          "merge seeds + tabs -> companies.csv"
Run-Stage "04" "04-discover\discover_ats.py"          "probe Ashby/Greenhouse/Lever/SmartRecruiters/Recruitee"
Run-Stage "05" "05-scrape\scrape_postings.py"         "scrape every discovered ATS in parallel"
Run-Stage "06" "06-assemble\build_workbook.py"        "build job-hunt.xlsx + tracker.md"

# Stage 07 only runs if the bridge script is present
$bridge = Join-Path $Root "07-bridge\bridge_to_evaluator.py"
if (Test-Path $bridge) {
    Run-Stage "07" "07-bridge\bridge_to_evaluator.py" "export shortlist hand-off (-> bridge-out or HANDOFF_DIR)"
}

$total = ((Get-Date) - $wallStart).TotalSeconds
Write-Host ""
Write-Host ("=== pipeline complete in {0:N0}s ===" -f $total) -ForegroundColor Cyan
Write-Host "Outputs:"
Write-Host "  06-assemble\job-hunt.xlsx"
Write-Host "  06-assemble\tracker.md"
