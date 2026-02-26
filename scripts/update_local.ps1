$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday"
}

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $Py)) {
  $Py = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "[update_local] DATABASE_URL=$env:DATABASE_URL"

& $Py .\backend\fetch_rss.py
& $Py .\backend\scripts\backfill_embeddings_live.py --since_days 7 --limit 500
& $Py .\backend\scripts\cluster_events_live.py --write
& $Py .\backend\scripts\backfill_article_types.py --days 7 --limit 1000
& $Py .\scripts\diagnose_funnel.py
