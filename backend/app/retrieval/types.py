# backend/app/retrieval/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass(frozen=True)
class CandidateSet:
    """
    Retrieval layer output. Decision layer must ONLY use candidate_event_ids,
    and must NOT expand candidate pool by querying all events.
    """
    query_article_id: int
    candidate_event_ids: List[int]  # must satisfy len(...) <= hard_cap
    strategy_version: str
    params: Dict[str, Any] = field(default_factory=dict)
    debug: Dict[str, Any] = field(default_factory=dict)
