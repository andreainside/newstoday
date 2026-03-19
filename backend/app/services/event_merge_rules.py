from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Set

from app.services.title_similarity import normalize_title

FUZZ_ACCEPT = 85.0
FUZZ_MAYBE = 60.0
JACCARD_MAYBE = 0.20
TIME_NEAR_HOURS = 6
VEC_MERGE_SIM = 0.62

SUBJECT_STOPWORDS = {
    "iran", "israel", "iranian", "israeli", "gaza", "hamas", "hezbollah",
    "war", "strike", "attack", "airstrike", "missile", "military", "official",
    "chief", "security", "intelligence", "leader", "commander", "minister",
    "president", "prime", "state", "country", "officials", "agency", "forces",
    "death", "dead", "dies", "die", "kill", "killed", "killing", "kills", "funeral",
    "mourning", "assassination", "assassinated", "assassinat", "survives", "survived", "survivor",
}
DEATH_EVENT_MARKERS = {
    "death", "dead", "dies", "die", "kill", "killed", "killing", "kills",
    "funeral", "mourning", "assassination", "assassinated", "assassinat", "surviv", "survived", "survivor",
}


@dataclass
class CandidateScore:
    event_id: int
    rep_title: str
    end_time: Optional[datetime]
    fuzz: float
    jaccard: float
    vec_sim: float


def extract_subject_tokens(title: str) -> Set[str]:
    return {tok for tok in normalize_title(title) if tok not in SUBJECT_STOPWORDS and not tok.isdigit()}


def titles_describe_distinct_death_subject(article_title: str, event_title: str) -> bool:
    article_tokens = set(normalize_title(article_title))
    event_tokens = set(normalize_title(event_title))
    if not (article_tokens & DEATH_EVENT_MARKERS and event_tokens & DEATH_EVENT_MARKERS):
        return False

    article_subjects = extract_subject_tokens(article_title)
    event_subjects = extract_subject_tokens(event_title)
    if not article_subjects or not event_subjects:
        return False

    return article_subjects.isdisjoint(event_subjects)


def decide_action(
    best: Optional[CandidateScore],
    article_time: datetime,
    event_end_time: Optional[datetime],
    *,
    article_title: Optional[str] = None,
) -> str:
    if best is None:
        return "new"

    if article_title and titles_describe_distinct_death_subject(article_title, best.rep_title):
        return "new"

    if best.vec_sim < 0.74 and best.jaccard <= 0.01 and best.fuzz < 45:
        return "new"

    if best.vec_sim >= VEC_MERGE_SIM:
        return "merge"

    if best.vec_sim >= 0.54 and best.fuzz >= 45:
        return "merge"

    if best.fuzz >= FUZZ_ACCEPT:
        return "merge"

    if best.fuzz >= FUZZ_MAYBE:
        if best.jaccard >= JACCARD_MAYBE:
            return "merge"
        if event_end_time is not None and abs(article_time - event_end_time) <= timedelta(hours=TIME_NEAR_HOURS):
            return "merge"

    return "new"
