# backend/scripts/eval_retrieval.py
import argparse
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple
from sqlalchemy import text
from app.retrieval.vector_retriever import RetrieverParams, retrieve_candidates


import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

# 这里用你 Phase 1 已经跑通的 DB 入口：backend/database.py
# 你之前修复过它，并且 python -m scripts.cluster_events 能跑通
from database import SessionLocal  # noqa: E402


@dataclass
class ArticleRow:
    id: int
    title: str
    published_at: str  # ISO string
    event_id: int | None


def fetch_articles(conn, window_days: int) -> List[ArticleRow]:
    """
    取文章 + 当前归属 event（如果有）
    注意：我们不改 Phase 1 表，只读 articles + event_articles
    """
    sql = f"""
    SELECT
      a.id,
      a.title,
      a.published_at::text AS published_at,
      ea.event_id
    FROM articles a
    LEFT JOIN event_articles ea ON ea.article_id = a.id
    WHERE a.published_at >= NOW() - INTERVAL '{int(window_days)} days'
    ORDER BY a.published_at DESC
    """
    rows = conn.execute(text(sql)).fetchall()
    out: List[ArticleRow] = []
    for r in rows:
        out.append(ArticleRow(id=r[0], title=r[1] or "", published_at=r[2], event_id=r[3]))
    return out


def cosine_topk(emb: np.ndarray, k: int) -> np.ndarray:
    """
    emb: [N, D] float32, assumed L2-normalized
    return indices of top-k most similar for each row (excluding self later)
    """
    # similarity = emb @ emb.T (cosine because normalized)
    sim = emb @ emb.T  # [N, N]
    # take top-(k+1) because self is highest
    top = np.argpartition(-sim, kth=min(k + 1, sim.shape[1] - 1), axis=1)[:, : k + 1]
    # sort those candidates by exact score
    top_sorted = np.take_along_axis(top, np.argsort(-np.take_along_axis(sim, top, axis=1), axis=1), axis=1)
    return top_sorted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval_csv", required=True, help="data/eval_missed_merges.csv")
    parser.add_argument("--window_days", type=int, default=7)
    parser.add_argument("--max_articles_per_event", type=int, default=3)
    parser.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--k_list", default="10,20,50")
    parser.add_argument(
        "--out_csv",
        default="",
        help="Optional: write per-query candidate sizes to CSV"
    )
    parser.add_argument("--strategy", type=str, default="baseline", choices=["baseline", "vec_v0"])
    parser.add_argument("--hard_cap_n", type=int, default=20)
    parser.add_argument("--neighbor_m", type=int, default=200)
    parser.add_argument("--time_gate_days", type=int, default=None)


    args = parser.parse_args()

    k_list = [int(x.strip()) for x in args.k_list.split(",") if x.strip()]
    k_max = max(k_list)

   

    # 1) 读人工标注 CSV：query_article_id,true_event_id
    df = pd.read_csv(args.eval_csv)
    required_cols = {"query_article_id", "true_event_id"}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"CSV must contain columns: {required_cols}, got: {list(df.columns)}")

    eval_pairs = [(int(r["query_article_id"]), int(r["true_event_id"])) for _, r in df.iterrows()]
    eval_query_ids = set(q for q, _ in eval_pairs)

    # 2) 从 DB 拉取近 window_days 的文章（只评测检索层，避免全库太慢）
    session = SessionLocal()
    conn = session.connection()
    try:
        articles = fetch_articles(conn, args.window_days)
    finally:
        session.close()

    # 3) 建索引：只保留标题非空的文章
    id_to_idx: Dict[int, int] = {}
    titles: List[str] = []
    article_ids: List[int] = []
    article_event: List[int | None] = []
    for a in articles:
        if not a.title.strip():
            continue
        id_to_idx[a.id] = len(article_ids)
        article_ids.append(a.id)
        titles.append(a.title.strip())
        article_event.append(a.event_id)

    # 4) 检查 eval 里的 query 是否都在候选库里
    missing = [qid for qid in eval_query_ids if qid not in id_to_idx]
    if missing:
        raise RuntimeError(
            "Some query_article_id not found in recent articles (window_days too small?). "
            f"Missing: {missing[:10]} (showing up to 10). "
            "Try increasing --window_days."
        )

    top_idx = None  # baseline 才会赋值

    if args.strategy == "baseline":
        # 5) 计算 embedding（标题级）
        model = SentenceTransformer(args.model)
        emb = model.encode(titles, batch_size=64, normalize_embeddings=True, show_progress_bar=True)
        emb = np.asarray(emb, dtype=np.float32)

        # 6) 取 topK 文章索引
        top_idx = cosine_topk(emb, k_max)


    # 7) Recall@K（以“映射成 event 集合后包含 true_event”为命中）
    hits = {k: 0 for k in k_list}
    cand_event_sizes: List[int] = []
    per_query_rows: List[Dict] = []


    # 用于“每事件最多取 M 篇候选文章”的配额
    # 做法：遍历 top 文章时，对每个 event 计数，超过配额就跳过
    for qid, true_eid in eval_pairs:
        # === Phase 2.1: vec_v0 path ===
        if args.strategy == "vec_v0":
            cs = retrieve_candidates(
                query_article_id=qid,
                params=RetrieverParams(
                    hard_cap_n=args.hard_cap_n,
                    neighbor_m=args.neighbor_m,
                    time_gate_days=args.time_gate_days,
                ),
            )
            cand_events_ordered = cs.candidate_event_ids  # 已经是硬上限后的 event 列表（有序）
            cand_event_sizes.append(len(cand_events_ordered))

            row = {
                "query_article_id": qid,
                "true_event_id": true_eid,
                "cand_event_size": len(cand_events_ordered),
                "strategy": args.strategy,
                "strategy_version": cs.strategy_version,
                "top_event_ids": ",".join(map(str, cand_events_ordered)),
            }
            for k in k_list:
                row[f"hit@{k}"] = int(true_eid in cand_events_ordered[: min(k, len(cand_events_ordered))])
                if true_eid in cand_events_ordered[: min(k, len(cand_events_ordered))]:
                    hits[k] += 1

            per_query_rows.append(row)
            continue  # vec_v0 走完这一条就结束本轮循环

        # === Phase 2.0: baseline path (keep existing logic) ===
        qi = id_to_idx[qid]

        per_event_cnt: Dict[int, int] = {}
        cand_events_ordered: List[int] = []

        for j in top_idx[qi]:
            aid = article_ids[int(j)]
            if aid == qid:
                continue  # exclude self
            eid = article_event[int(j)]
            if eid is None:
                continue

            eid_int = int(eid)
            cur = per_event_cnt.get(eid_int, 0)
            if cur >= args.max_articles_per_event:
                continue
            per_event_cnt[eid_int] = cur + 1

            if eid_int not in cand_events_ordered:
                cand_events_ordered.append(eid_int)

        cand_event_sizes.append(len(cand_events_ordered))

        row = {
            "query_article_id": qid,
            "true_event_id": true_eid,
            "cand_event_size": len(cand_events_ordered),
            "strategy": args.strategy,
            "strategy_version": "p2.0_baseline",
            "top_event_ids": ",".join(map(str, cand_events_ordered)),
        }
        for k in k_list:
            row[f"hit@{k}"] = int(true_eid in cand_events_ordered[: min(k, len(cand_events_ordered))])
            if true_eid in cand_events_ordered[: min(k, len(cand_events_ordered))]:
                hits[k] += 1

        per_query_rows.append(row)


    n = len(eval_pairs)
    print("\n=== Retrieval-only Metrics (Recall Layer) ===")
    for k in k_list:
        print(f"Recall@{k}: {hits[k]}/{n} = {hits[k]/n:.3f}")

    cand = np.asarray(cand_event_sizes, dtype=np.float32)
    mean = float(cand.mean()) if len(cand) else 0.0
    p95 = float(np.percentile(cand, 95)) if len(cand) else 0.0
    print(f"Candidate event set size: mean={mean:.2f}, p95={p95:.0f}")
    print(f"(window_days={args.window_days}, max_articles_per_event={args.max_articles_per_event})\n")

    if args.out_csv:
        out_df = pd.DataFrame(per_query_rows)

        # HARD GUARD: each query_article_id must appear exactly once
        dup = out_df["query_article_id"].duplicated().sum()
        assert dup == 0, f"duplicate query rows detected: {dup}"

        assert len(out_df) == len(eval_pairs), (
            f"row mismatch: rows={len(out_df)} eval_pairs={len(eval_pairs)}"
        )

        out_df.to_csv(args.out_csv, index=False)
        print(f"Wrote per-query candidate stats to: {args.out_csv}")




if __name__ == "__main__":
    main()
