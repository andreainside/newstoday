# backend/scripts/smoke_retrieval_v0.py
import pandas as pd

from app.retrieval.vector_retriever import RetrieverParams, retrieve_candidates

def main() -> None:
    df = pd.read_csv("data/eval_missed_merges.csv")
    qid = int(df.iloc[0]["query_article_id"])
    true_eid = int(df.iloc[0]["true_event_id"])

    params = RetrieverParams(hard_cap_n=20, neighbor_m=200, time_gate_days=None)
    cs = retrieve_candidates(qid, params)

    print("strategy:", cs.strategy_version)
    print("query_article_id:", cs.query_article_id, "true_event_id:", true_eid)
    print("cand_size:", len(cs.candidate_event_ids))
    print("candidates:", cs.candidate_event_ids)
    print("debug:", cs.debug)

if __name__ == "__main__":
    main()
