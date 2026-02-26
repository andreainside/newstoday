$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday"
}

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $Py)) {
  $Py = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "[run_ai] apply phase5.2 schema"
Get-Content .\backend\sql\phase52_schema.sql -Raw | docker exec -i newstoday-postgres psql -U postgres -d newstoday -f -

Write-Host "[run_ai] build signatures"
& $Py .\backend\scripts\build_event_signatures_v0.py --db-url "$env:DATABASE_URL" --since-days 7 --write-db

Write-Host "[run_ai] generate and judge merge suggestions"
& $Py .\backend\scripts\judge_event_merge_suggestions_v1.py --db-url "$env:DATABASE_URL" --since-days 7 --topk 60 --write-db --mock-llm

Write-Host "[run_ai] diagnose funnel"
& $Py .\scripts\diagnose_funnel.py
