[CmdletBinding()]
param(
    [switch]$SkipTests
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $RepoRoot

$ExpectedBranch = "research/rd09b-market-level-native-chain-feasibility-v2"
$CurrentBranch = (& git rev-parse --abbrev-ref HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to resolve the current Git branch."
}
if ($CurrentBranch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch' but found '$CurrentBranch'."
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python -PathType Leaf)) {
    throw "Python interpreter not found at $Python"
}

if ([string]::IsNullOrWhiteSpace($env:DUNE_API_KEY)) {
    throw "DUNE_API_KEY is not visible in this PowerShell process."
}
if ($env:DUNE_ZERO_SPEND_CONFIRMED -ne "true") {
    throw "DUNE_ZERO_SPEND_CONFIRMED must equal 'true'."
}

$SourcePath = Join-Path $RepoRoot "src"
if ([string]::IsNullOrWhiteSpace($env:PYTHONPATH)) {
    $env:PYTHONPATH = $SourcePath
}
else {
    $env:PYTHONPATH = $SourcePath + [IO.Path]::PathSeparator + $env:PYTHONPATH
}

$LogDirectory = Join-Path $RepoRoot "data\research\rd09b\v2\manifests"
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$LogPath = Join-Path $LogDirectory "rd09b-v2-local-$Timestamp.log"

function Invoke-LoggedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Label,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "=== $Label ==="
    "=== $Label ===" | Out-File -FilePath $LogPath -Append -Encoding utf8

    & $Python @Arguments 2>&1 |
        Tee-Object -FilePath $LogPath -Append |
        ForEach-Object { Write-Host $_ }

    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE. See $LogPath"
    }
}

Write-Host "RD09B v2 local runner preflight passed."
Write-Host "Branch: $CurrentBranch"
Write-Host "DUNE_API_KEY: present"
Write-Host "DUNE_ZERO_SPEND_CONFIRMED: true"
Write-Host "Cash spend ceiling: `$0"
Write-Host "Pilot credit ceiling: 500"
Write-Host "Log: $LogPath"

if (-not $SkipTests) {
    Invoke-LoggedCommand -Label "Ruff check" -Arguments @(
        "-m",
        "ruff",
        "check",
        "src/spotbot/research/rd09b_market_level_acquisition.py",
        "src/spotbot/research/rd09b_market_level_quality.py",
        "scripts/research/run_rd09b_v2_dune_pilot.py",
        "scripts/research/run_rd09b_v2_quality_and_decision.py",
        "tests/research/test_rd09b_market_level_acquisition.py",
        "tests/research/test_rd09b_market_level_quality.py"
    )

    Invoke-LoggedCommand -Label "Ruff format check" -Arguments @(
        "-m",
        "ruff",
        "format",
        "--check",
        "src/spotbot/research/rd09b_market_level_acquisition.py",
        "src/spotbot/research/rd09b_market_level_quality.py",
        "scripts/research/run_rd09b_v2_dune_pilot.py",
        "scripts/research/run_rd09b_v2_quality_and_decision.py",
        "tests/research/test_rd09b_market_level_acquisition.py",
        "tests/research/test_rd09b_market_level_quality.py"
    )

    Invoke-LoggedCommand -Label "Strict mypy" -Arguments @(
        "-m",
        "mypy",
        "src/spotbot/research/rd09b_market_level_acquisition.py",
        "src/spotbot/research/rd09b_market_level_quality.py"
    )

    Invoke-LoggedCommand -Label "Focused safety tests" -Arguments @(
        "-m",
        "pytest",
        "tests/research/test_rd09b_market_level_protocol.py",
        "tests/research/test_rd09b_market_level_acquisition.py",
        "tests/research/test_rd09b_market_level_quality.py",
        "-W",
        "error",
        "-q"
    )
}

Invoke-LoggedCommand -Label "Dune pilot acquisition" -Arguments @(
    "scripts/research/run_rd09b_v2_dune_pilot.py"
)

Invoke-LoggedCommand -Label "Pilot quality and final decision" -Arguments @(
    "scripts/research/run_rd09b_v2_quality_and_decision.py"
)

$DecisionPath = Join-Path $RepoRoot "reports\research\ams-rd09b-v2-final-decision-v1.json"
if (-not (Test-Path $DecisionPath -PathType Leaf)) {
    throw "Final decision report was not created."
}

$Decision = Get-Content $DecisionPath -Raw | ConvertFrom-Json
Write-Host ""
Write-Host "=== RD09B v2 result ==="
Write-Host "Status: $($Decision.status)"
Write-Host "Decision: $($Decision.decision)"
Write-Host "Executed queries: $($Decision.executed_query_count)"
Write-Host "Passing namespaces: $($Decision.passing_namespace_count)"
Write-Host "Pilot credits consumed: $($Decision.pilot_credits_consumed)"
Write-Host "Paid spending: `$$($Decision.paid_spending_usd)"
Write-Host "Next stage: $($Decision.next_stage)"
Write-Host "Full report: $DecisionPath"
Write-Host "Run log: $LogPath"
