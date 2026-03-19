from datetime import datetime

from app.services.event_merge_rules import CandidateScore, decide_action, titles_describe_distinct_death_subject


def test_distinct_death_subjects_do_not_merge_even_with_strong_vector_signal():
    best = CandidateScore(
        event_id=1,
        rep_title="Iran security chief Ali Larijani killed in Israeli strike",
        end_time=datetime(2026, 3, 17, 22, 5),
        fuzz=68.0,
        jaccard=0.22,
        vec_sim=0.83,
    )

    action = decide_action(
        best,
        article_time=datetime(2026, 3, 18, 4, 57),
        event_end_time=best.end_time,
        article_title="Israel says it killed Iran intelligence chief Mohammad Kazemi in a third strike",
    )

    assert action == "new"


def test_same_death_subject_can_still_merge():
    best = CandidateScore(
        event_id=1,
        rep_title="Iran security chief Ali Larijani killed in Israeli strike",
        end_time=datetime(2026, 3, 17, 22, 5),
        fuzz=72.0,
        jaccard=0.30,
        vec_sim=0.83,
    )

    action = decide_action(
        best,
        article_time=datetime(2026, 3, 18, 0, 30),
        event_end_time=best.end_time,
        article_title="Funeral held after Israeli strike killed Ali Larijani, Iran security chief",
    )

    assert action == "merge"


def test_distinct_death_subject_detector_requires_disjoint_subject_tokens():
    assert titles_describe_distinct_death_subject(
        "Israel says it killed Iran intelligence chief Mohammad Kazemi in a third strike",
        "Iran security chief Ali Larijani killed in Israeli strike",
    )
    assert not titles_describe_distinct_death_subject(
        "Funeral held after Israeli strike killed Ali Larijani, Iran security chief",
        "Iran security chief Ali Larijani killed in Israeli strike",
    )
