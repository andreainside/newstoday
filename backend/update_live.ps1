# E:\NewsToday\newstoday\backend\update_live.ps1
param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [switch]$UseDockerCounts,
  [string]$DockerPgContainer = "newstoday-postgres",
  [string]$DockerDbName = "newstoday"
)

$ErrorActionPreference = "Stop"

$BackendDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $BackendDir

$Py = Join-Path $BackendDir "..\.venv\Scripts\python.exe"
if (!(Test-Path $Py)) { $Py = (Get-Command python -ErrorAction Stop).Source }

if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
  throw "DATABASE_URL is empty. Pass -DatabaseUrl or set env:DATABASE_URL before running."
}

$env:DATABASE_URL = $DatabaseUrl

New-Item -ItemType Directory -Force .\data\logs | Out-Null
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$log = ".\data\logs\update_live_$ts.log"

"=== update_live start $ts ===" | Tee-Object -FilePath $log
"DATABASE_URL source: parameter/env" | Tee-Object -FilePath $log -Append

if ($UseDockerCounts) {
  "--- BEFORE counts (docker) ---" | Tee-Object -FilePath $log -Append
  docker exec -i $DockerPgContainer psql -U postgres -d $DockerDbName -c "SELECT COUNT(*) AS articles FROM public.articles; SELECT COUNT(*) AS events FROM public.events; SELECT COUNT(*) AS event_articles FROM public.event_articles;" | Tee-Object -FilePath $log -Append
}

"--- scripts.update_live --write ---" | Tee-Object -FilePath $log -Append
& $Py -m scripts.update_live --write *>&1 | Tee-Object -FilePath $log -Append

if ($UseDockerCounts) {
  "--- AFTER counts (docker) ---" | Tee-Object -FilePath $log -Append
  docker exec -i $DockerPgContainer psql -U postgres -d $DockerDbName -c "SELECT COUNT(*) AS articles FROM public.articles; SELECT COUNT(*) AS events FROM public.events; SELECT COUNT(*) AS event_articles FROM public.event_articles;" | Tee-Object -FilePath $log -Append
}

"=== update_live done ===" | Tee-Object -FilePath $log -Append
Write-Host "Log: $log"
