# E:\NewsToday\newstoday\backend\update_live.ps1
$ErrorActionPreference = "Stop"

# 1) Paths
$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $BackendDir

$Py = Join-Path $BackendDir "..\.venv\Scripts\python.exe"
if (!(Test-Path $Py)) {
  throw "Python venv not found at: $Py . Please check .venv path."
}

New-Item -ItemType Directory -Force .\data\logs | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = ".\data\logs\update_live_$ts.log"

# 2) Force LIVE DB
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/newstoday"

"=== update_live start $ts ===" | Tee-Object -FilePath $log

"--- BEFORE counts ---" | Tee-Object -FilePath $log -Append
docker exec -i newstoday-postgres psql -U postgres -d newstoday -c "SELECT COUNT(*) AS articles FROM public.articles; SELECT COUNT(*) AS events FROM public.events; SELECT COUNT(*) AS event_articles FROM public.event_articles;" |
  Tee-Object -FilePath $log -Append

"--- fetch_rss ---" | Tee-Object -FilePath $log -Append
& $Py .\fetch_rss.py *>&1 | Tee-Object -FilePath $log -Append

"--- cluster_events --write ---" | Tee-Object -FilePath $log -Append
& $Py -m scripts.cluster_events --write *>&1 | Tee-Object -FilePath $log -Append

"--- recompute event windows ---" | Tee-Object -FilePath $log -Append
docker exec -i newstoday-postgres psql -U postgres -d newstoday -c "
WITH stats AS (
  SELECT ea.event_id, MIN(a.published_at) AS min_t, MAX(a.published_at) AS max_t
  FROM public.event_articles ea
  JOIN public.articles a ON a.id = ea.article_id
  GROUP BY ea.event_id
)
UPDATE public.events e
SET start_time = s.min_t,
    end_time   = s.max_t
FROM stats s
WHERE e.id = s.event_id
  AND (e.start_time IS DISTINCT FROM s.min_t OR e.end_time IS DISTINCT FROM s.max_t);
" | Tee-Object -FilePath $log -Append


"--- AFTER counts ---" | Tee-Object -FilePath $log -Append
docker exec -i newstoday-postgres psql -U postgres -d newstoday -c "SELECT COUNT(*) AS articles FROM public.articles; SELECT COUNT(*) AS events FROM public.events; SELECT COUNT(*) AS event_articles FROM public.event_articles;" |
  Tee-Object -FilePath $log -Append

"=== update_live done ===" | Tee-Object -FilePath $log -Append
Write-Host "Log: $log"
