# backend/scripts/smoke_candidateset.py
from app.retrieval.types import CandidateSet

def main() -> None:
    cs = CandidateSet(
        query_article_id=123,
        candidate_event_ids=[1, 2, 3],
        strategy_version="p2.1_contract_smoke",
        params={"hard_cap": 20},
        debug={"note": "contract only"},
    )
    print("OK", cs)

if __name__ == "__main__":
    main()
