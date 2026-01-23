# backend/app/retrieval/vector_retriever.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from app.retrieval.types import CandidateSet

load_dotenv()


@dataclass(frozen=True)
class RetrieverParams:
    hard_cap_n: int = 20          # final hard cap on events
    neighbor_m: int = 200         # top-M neighbor articles
    time_gate_days: Optional[int] = None  # optional, keep None for v0


STRATEGY_VERSION = "p2.1_v0_vec_topM_articles_to_topN_events"


def retrieve_candidates(query_article_id: int, params: RetrieverParams) -> CandidateSet:
    """
    Retrieval v0:
    1) get query article embedding (+ published_at)
    2) vector-search top-M neighbor articles (optionally time-gated)
    3) map neighbor articles -> events, score event by max similarity
    4) take top-N events (hard cap)
    """
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")

    engine = create_engine(db_url)
    t0 = time.time()

    # 1) fetch query embedding and time
    with engine.begin() as conn:
        qrow = conn.execute(
            text(
                """
                SELECT id, embedding, published_at
                FROM articles
                WHERE id = :id
                """
            ),
            {"id": query_article_id},
        ).fetchone()

    if not qrow:
        return CandidateSet(
            query_article_id=query_article_id,
            candidate_event_ids=[],
            strategy_version=STRATEGY_VERSION,
            params={"hard_cap_n": params.hard_cap_n, "neighbor_m": params.neighbor_m, "time_gate_days": params.time_gate_days},
            debug={"error": "query_article_not_found"},
        )

    _, qemb, qtime = qrow
    if qemb is None:
        return CandidateSet(
            query_article_id=query_article_id,
            candidate_event_ids=[],
            strategy_version=STRATEGY_VERSION,
            params={"hard_cap_n": params.hard_cap_n, "neighbor_m": params.neighbor_m, "time_gate_days": params.time_gate_days},
            debug={"error": "query_embedding_is_null"},
        )

    # 2) vector search neighbor articles
    # pgvector: smaller distance is closer. We'll use <=> (cosine distance) since embeddings are normalized.
    neighbor_sql = """
        SELECT a.id AS neighbor_article_id,
               (1 - (a.embedding <=> :qemb)) AS sim
        FROM articles a
        WHERE a.embedding IS NOT NULL
          AND a.id <> :qid
    """

    params_sql: Dict[str, Any] = {"qemb": qemb, "qid": query_article_id, "m": params.neighbor_m}

    if params.time_gate_days is not None:
        # only apply if query has published_at
        neighbor_sql += """
          AND a.published_at IS NOT NULL
          AND :qtime IS NOT NULL
          AND a.published_at BETWEEN (:qtime - (:days || ' days')::interval) AND (:qtime + (:days || ' days')::interval)
        """
        params_sql["qtime"] = qtime
        params_sql["days"] = params.time_gate_days

    neighbor_sql += """
        ORDER BY a.embedding <=> :qemb
        LIMIT :m
    """

    with engine.begin() as conn:
        nrows = conn.execute(text(neighbor_sql), params_sql).fetchall()

    neighbor_count = len(nrows)

    # 3) map neighbor articles -> events, score by max sim
    # We only need events that contain these neighbor articles.
    neighbor_ids = [int(r[0]) for r in nrows]
    sims = {int(r[0]): float(r[1]) for r in nrows}

    if not neighbor_ids:
        return CandidateSet(
            query_article_id=query_article_id,
            candidate_event_ids=[],
            strategy_version=STRATEGY_VERSION,
            params={"hard_cap_n": params.hard_cap_n, "neighbor_m": params.neighbor_m, "time_gate_days": params.time_gate_days},
            debug={"neighbor_articles": 0, "unique_events": 0},
        )

    map_sql = """
        SELECT ea.event_id, ea.article_id
        FROM event_articles ea
        WHERE ea.article_id = ANY(:aids)
    """

    with engine.begin() as conn:
        map_rows = conn.execute(text(map_sql), {"aids": neighbor_ids}).fetchall()

    event_best: Dict[int, Tuple[float, int]] = {}  # event_id -> (best_sim, article_id)
    for event_id, article_id in map_rows:
        eid = int(event_id)
        aid = int(article_id)
        sim = sims.get(aid, 0.0)
        prev = event_best.get(eid)
        if (prev is None) or (sim > prev[0]):
            event_best[eid] = (sim, aid)

    # sort events by best_sim desc
    ranked = sorted(event_best.items(), key=lambda kv: kv[1][0], reverse=True)
    top_events = [eid for eid, _ in ranked[: params.hard_cap_n]]

    dt_ms = int((time.time() - t0) * 1000)
    debug = {
        "neighbor_articles": neighbor_count,
        "unique_events": len(event_best),
        "timing_ms": dt_ms,
        "top_event_samples": [
            {"event_id": eid, "best_sim": float(best[0]), "via_article_id": int(best[1])}
            for eid, best in ranked[: min(5, len(ranked))]
        ],
    }

    return CandidateSet(
        query_article_id=query_article_id,
        candidate_event_ids=top_events,
        strategy_version=STRATEGY_VERSION,
        params={"hard_cap_n": params.hard_cap_n, "neighbor_m": params.neighbor_m, "time_gate_days": params.time_gate_days},
        debug=debug,
    )
