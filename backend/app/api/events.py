from fastapi import APIRouter, HTTPException, Query
from app.services.event_reader import get_top_events, get_event_detail
from app.services.coverage_matrix import get_coverage_matrix
from app.services.gap_hints import get_gap_hints

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/{event_id}/coverage")
def event_coverage(event_id: int):
    return get_coverage_matrix(event_id)


@router.get("/{event_id}/gaps")
def event_gaps(event_id: int):
    return get_gap_hints(event_id)
@router.get("/top")
def top_events(limit: int = Query(5, ge=1, le=20)):
    return get_top_events(limit)

@router.get("/{event_id}")
def event_detail(
    event_id: int,
    diversity: int = Query(0, ge=0, le=60),
    debug: int = Query(0, ge=0, le=1),
):
    if diversity not in (0, 30, 60):
        raise HTTPException(status_code=400, detail="diversity must be one of 0,30,60")

    data = get_event_detail(event_id, diversity=diversity, debug=bool(debug))

    if data.get("event") is None:
        raise HTTPException(status_code=404, detail="event not found")
    return data

