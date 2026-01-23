# backend/scripts/backfill_embeddings_eval.py
from __future__ import annotations

import os
import time
from typing import Dict, List, Tuple
from dotenv import load_dotenv

load_dotenv()  # 自动加载项目根目录的 .env

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sentence_transformers import SentenceTransformer


EVAL_CSV_DEFAULT = "data/eval_missed_merges.csv"
MODEL_NAME_DEFAULT = "sentence-transformers/all-MiniLM-L6-v2"  # 384 dim


def _vec_to_pgvector_literal(v: np.ndarray) -> str:
    # pgvector accepts: '[0.1,0.2,...]'
    return "[" + ",".join(f"{x:.8f}" for x in v.tolist()) + "]"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--eval_csv", default=EVAL_CSV_DEFAULT)
    parser.add_argument("--model", default=MODEL_NAME_DEFAULT)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--only_null", action="store_true", help="only fill rows where embedding IS NULL")
    parser.add_argument("--all_articles", action="store_true", help="backfill all articles with embedding IS NULL")

    args = parser.parse_args()

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Please set it (same as your backend uses), then re-run."
        )

    t0 = time.time()
    df = pd.read_csv(args.eval_csv)
    if "query_article_id" not in df.columns:
        raise RuntimeError(f"eval_csv missing column 'query_article_id'. got columns={list(df.columns)}")

    query_ids = sorted({int(x) for x in df["query_article_id"].dropna().tolist()})
    print(f"[eval] unique query_article_id: {len(query_ids)}")

    engine = create_engine(db_url)


    with engine.begin() as conn:
        if args.all_articles:
            rows = conn.execute(
                text(
                    """
                    SELECT id, title
                    FROM articles
                    WHERE embedding IS NULL
                    ORDER BY id
                    """
                )
            ).fetchall()
        elif args.only_null:
            rows = conn.execute(
                text(
                    """
                    SELECT id, title
                    FROM articles
                    WHERE id = ANY(:ids) AND embedding IS NULL
                    """
                ),
            {"ids": query_ids},
            ).fetchall()
        else:
            rows = conn.execute(
                text(
                    """
                    SELECT id, title
                    FROM articles
                    WHERE id = ANY(:ids)
                    """
                ),
                {"ids": query_ids},
            ).fetchall()


    id_to_title: Dict[int, str] = {int(r[0]): str(r[1]) for r in rows}
    missing = [i for i in query_ids if i not in id_to_title]
    if missing:
        print(f"[warn] missing articles in DB for {len(missing)} ids. examples: {missing[:10]}")

    target_ids = sorted(id_to_title.keys())
    if not target_ids:
        print("[done] nothing to backfill (all present ids already have embedding, or no ids found).")
        return

    titles = [id_to_title[i] for i in target_ids]
    print(f"[db] rows to embed: {len(target_ids)} (only_null={args.only_null})")

    # Load model
    model = SentenceTransformer(args.model)
    # Ensure we really have 384 dims (must match vector(384))
    test_vec = model.encode(["dim_check"], normalize_embeddings=True)
    dim = int(test_vec.shape[1])
    if dim != 384:
        raise RuntimeError(f"Model dim={dim}, but DB column is vector(384). Choose a 384-dim model.")

    # Encode in batches
    embeddings = model.encode(
        titles,
        batch_size=args.batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    embeddings = np.asarray(embeddings, dtype=np.float32)

    # Prepare updates
    payload: List[Tuple[int, str]] = []
    for aid, vec in zip(target_ids, embeddings):
        payload.append((aid, _vec_to_pgvector_literal(vec)))

    # Write back
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE articles
                SET embedding = (:emb)::vector
                WHERE id = :id
                """
            ),
            [{"id": aid, "emb": emb} for (aid, emb) in payload],
        )

    dt = time.time() - t0
    print(f"[done] updated {len(payload)} rows in {dt:.2f}s")
    print(f"[meta] model={args.model} dim=384 normalize=true batch_size={args.batch_size}")


if __name__ == "__main__":
    main()
