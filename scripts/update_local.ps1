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
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

function Get-ScalarInt([string]$sql) {
  $code = @'
import os
from sqlalchemy import create_engine, text

db = os.getenv("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday")
eng = create_engine(db)
sql = os.getenv("NT_SQL")
with eng.connect() as c:
    v = c.execute(text(sql)).scalar()
print(int(v or 0))
'@
  $env:NT_SQL = $sql
  try {
    $out = $code | & $Py -
    if ($LASTEXITCODE -ne 0) {
      throw "Get-ScalarInt failed: Python exited with code $LASTEXITCODE"
    }
    $lastLine = ($out | Select-Object -Last 1).ToString().Trim()
    $parsed = 0
    if (-not [int]::TryParse($lastLine, [ref]$parsed)) {
      throw "Get-ScalarInt failed: unexpected output '$lastLine'"
    }
    return $parsed
  }
  finally {
    Remove-Item Env:\NT_SQL -ErrorAction SilentlyContinue
  }
}

function Get-UnassignedCount240h {
  return Get-ScalarInt @"
SELECT COUNT(*)
FROM articles a
LEFT JOIN event_articles ea ON ea.article_id = a.id
WHERE a.published_at >= (NOW() - INTERVAL '240 hours')
  AND a.embedding IS NOT NULL
  AND ea.article_id IS NULL
"@
}

function Get-MissingEmbeddingsRecent7d {
  return Get-ScalarInt @"
SELECT COUNT(*)
FROM articles
WHERE published_at >= (NOW() - INTERVAL '7 days')
  AND embedding IS NULL
"@
}

function Get-MissingArticleTypesRecent7d {
  return Get-ScalarInt @"
SELECT COUNT(*)
FROM articles
WHERE published_at >= (NOW() - INTERVAL '7 days')
  AND article_type IS NULL
"@
}

Push-Location (Join-Path $RepoRoot "backend")
try {
  & $Py -m fetch_rss

  $missingEmbeddings = Get-MissingEmbeddingsRecent7d
  if ($missingEmbeddings -gt 0) {
    Write-Host "[embed] missing_recent_7d=$missingEmbeddings -> run backfill_embeddings_live"
    & $Py -m scripts.backfill_embeddings_live --since_days 7 --limit 500
  }
  else {
    Write-Host "[embed] missing_recent_7d=0 -> skip backfill_embeddings_live"
  }

  $maxRounds = if ($env:CLUSTER_MAX_ROUNDS) { [int]$env:CLUSTER_MAX_ROUNDS } else { 30 }
  $clusterBatchSize = if ($env:CLUSTER_BATCH_SIZE) { [int]$env:CLUSTER_BATCH_SIZE } else { 100 }

  $remainingBefore = Get-UnassignedCount240h
  if ($remainingBefore -le 0) {
    Write-Host "[cluster] remaining_unassigned_240h=0 -> skip cluster_events_live"
  }

  if ($remainingBefore -gt 0) {
    $suggestedRounds = [math]::Ceiling($remainingBefore / [double]$clusterBatchSize) + 2
    if ($suggestedRounds -lt $maxRounds) {
      $maxRounds = [int]$suggestedRounds
    }
  }

  $prevRemaining = -1
  $stagnantRounds = 0
  for ($round = 1; $round -le $maxRounds -and $remainingBefore -gt 0; $round++) {
    Write-Host "[cluster] round=$round/$maxRounds (start_remaining=$remainingBefore)"
    & $Py -m scripts.cluster_events_live --write

    $remaining = Get-UnassignedCount240h
    Write-Host "[cluster] remaining_unassigned_240h=$remaining"

    if ($remaining -le 0) {
      Write-Host "[cluster] complete: no unassigned recent articles."
      break
    }

    if ($prevRemaining -ge 0 -and $remaining -ge $prevRemaining) {
      $stagnantRounds += 1
      Write-Warning "[cluster] no progress detected (prev=$prevRemaining, now=$remaining, stagnant_rounds=$stagnantRounds)."
      if ($stagnantRounds -ge 3) {
        Write-Warning "[cluster] stop after 3 stagnant rounds."
        break
      }
    }
    else {
      $stagnantRounds = 0
    }

    $prevRemaining = $remaining
  }

  $missingTypes = Get-MissingArticleTypesRecent7d
  if ($missingTypes -gt 0) {
    Write-Host "[types] missing_recent_7d=$missingTypes -> run backfill_article_types"
    & $Py -m scripts.backfill_article_types --days 7 --limit 1000
  }
  else {
    Write-Host "[types] missing_recent_7d=0 -> skip backfill_article_types"
  }
}
finally {
  Pop-Location
}

& $Py .\scripts\diagnose_funnel.py
