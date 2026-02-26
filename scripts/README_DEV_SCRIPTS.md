# Dev Scripts

## Prerequisites
- Docker container `newstoday-postgres` is running
- Database name is `newstoday`
- Python venv exists at `.venv\Scripts\python.exe`
- `DATABASE_URL` points to the same DB used by backend

## One-command local refresh
```powershell
.\scripts\update_local.ps1
```
Runs:
1. `backend/fetch_rss.py`
2. `backend/scripts/backfill_embeddings_live.py`
3. `backend/scripts/cluster_events_live.py --write`
4. `backend/scripts/backfill_article_types.py`
5. `scripts/diagnose_funnel.py`

## Phase 5.2 merge pipeline
```powershell
.\run_ai.ps1
```
Runs schema setup + signature build + merge suggestion judge.

## Diagnostics
```powershell
python .\scripts\diagnose_funnel.py
python .\scripts\diagnose_supply.py
```

## Launch frontend + backend
```powershell
.\dev.ps1
```
