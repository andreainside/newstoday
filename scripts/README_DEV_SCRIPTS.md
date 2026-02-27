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

## Top5 eval quality
```powershell
# Evaluate top5 quality vs human baseline + article attachment audit
python .\backend\scripts\eval_top5_events_quality.py --write-log

# Optional: export JSON
python .\backend\scripts\eval_top5_events_quality.py --output-json .\scripts\eval_top5_quality.json
```

## Daily eval dashboard
```powershell
# Log top-events params for today, then print daily aggregates
python .\backend\scripts\dashboard_eval_daily.py --write-params
```

## Launch frontend + backend
```powershell
.\dev.ps1
```
