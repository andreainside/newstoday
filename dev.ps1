$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

if (-not $env:DATABASE_URL) {
  $env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/newstoday"
}
if (-not $env:NEXT_PUBLIC_API_BASE_URL) {
  $env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:8000"
}

$Py = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (!(Test-Path $Py)) {
  $Py = (Get-Command python -ErrorAction Stop).Source
}

Write-Host "[dev] Starting backend at http://127.0.0.1:8000"
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$RepoRoot\backend'; `$env:DATABASE_URL='$env:DATABASE_URL'; & '$Py' -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload"

Write-Host "[dev] Starting frontend at http://127.0.0.1:3000"
Start-Process powershell -ArgumentList "-NoExit","-Command","Set-Location '$RepoRoot\frontend'; `$env:NEXT_PUBLIC_API_BASE_URL='$env:NEXT_PUBLIC_API_BASE_URL'; npm run dev"

Write-Host "[dev] Done. Backend: 127.0.0.1:8000, Frontend: 127.0.0.1:3000"
