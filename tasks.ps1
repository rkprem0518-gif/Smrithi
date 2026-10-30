# Smriti task runner for Windows PowerShell.
#   .\tasks.ps1 setup | demo | test | lint | create-agent | dry-run | check | call +91XXXXXXXXXX | seed
param(
    [Parameter(Position = 0)][string]$Task = "help",
    [Parameter(Position = 1)][string]$Arg = ""
)
$ErrorActionPreference = "Stop"
$py = ".\.venv\Scripts\python.exe"

switch ($Task) {
    "setup" {
        python -m venv .venv
        & $py -m pip install -r requirements-dev.txt
        if (-not (Test-Path .env)) { Copy-Item .env.example .env }
        Write-Host "Done. Run: .\tasks.ps1 demo"
    }
    "demo"         { & $py -m uvicorn app.main:app --reload }
    "test"         { & $py -m pytest }
    "lint"         { & $py -m ruff check . }
    "create-agent" { & $py scripts\create_agent.py }
    "dry-run"      { & $py scripts\create_agent.py --dry-run }
    "check"        { & $py scripts\check_live.py }
    "call" {
        if (-not $Arg) { throw "Usage: .\tasks.ps1 call +91XXXXXXXXXX" }
        & $py scripts\test_call.py $Arg
    }
    "seed"         { & $py scripts\seed_demo.py }
    default {
        Write-Host "Usage: .\tasks.ps1 setup | demo | test | lint | create-agent | dry-run | check | call +91XXXXXXXXXX | seed"
    }
}
