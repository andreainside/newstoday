# article_typing_rules.py
# Phase 2.2B v0: Rule-based Article Typing (FACT / INTERPRETATION / COMMENTARY)
# Constraints: conservative, low false-positive, default FACT. No LLM. No ML.

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple, Optional


TYPE_FACT = "FACT"
TYPE_INTERPRETATION = "INTERPRETATION"
TYPE_COMMENTARY = "COMMENTARY"


# --- Reason codes (for debugging/auditing) ---
R_URL_OPINION = "URL_OPINION"
R_URL_ANALYSIS = "URL_ANALYSIS"
R_TITLE_PREFIX_OPINION = "TITLE_PREFIX_OPINION"
R_TITLE_PREFIX_ANALYSIS = "TITLE_PREFIX_ANALYSIS"
R_TEXT_COMMENTARY_STRONG = "TEXT_COMMENTARY_STRONG"
R_TEXT_INTERPRET_STRONG = "TEXT_INTERPRET_STRONG"
R_DEFAULT_FACT = "DEFAULT_FACT"


# --- URL / path patterns (publisher self-label is the safest signal) ---
# Keep these conservative. Only match obvious section paths.
URL_OPINION_PATTERNS = [
    r"/opinion/",
    r"/editorial/",
    r"/comment/",
    r"/column/",
]

URL_ANALYSIS_PATTERNS = [
    r"/analysis/",
    r"/explainer/",
    r"/explain/",
    r"/background/",
]

# Compile once (case-insensitive)
URL_OPINION_RE = [re.compile(p, re.IGNORECASE) for p in URL_OPINION_PATTERNS]
URL_ANALYSIS_RE = [re.compile(p, re.IGNORECASE) for p in URL_ANALYSIS_PATTERNS]


# --- Title prefix patterns (safe when it's clearly formatted as a prefix) ---
# Only accept prefix-like formats, to reduce false positives.
TITLE_PREFIX_OPINION = [
    r"^\s*opinion\s*:\s*",
    r"^\s*editorial\s*:\s*",
    r"^\s*commentary\s*:\s*",
    r"^\s*column\s*:\s*",
    r"^\s*our\s+view\s*:\s*",
]

TITLE_PREFIX_ANALYSIS = [
    r"^\s*analysis\s*:\s*",
    r"^\s*explainer\s*:\s*",
    r"^\s*explained\s*:\s*",
    r"^\s*what\s+we\s+know\s*:\s*",
    r"^\s*why\s+it\s+matters\s*:\s*",
]

TITLE_PREFIX_OPINION_RE = [re.compile(p, re.IGNORECASE) for p in TITLE_PREFIX_OPINION]
TITLE_PREFIX_ANALYSIS_RE = [re.compile(p, re.IGNORECASE) for p in TITLE_PREFIX_ANALYSIS]


# --- Text signals (be very conservative) ---
# Commentary strong signals:
# We require >=2 categories to trigger COMMENTARY by text.
FIRST_PERSON_STANCE = [
    r"\bi\s+think\b",
    r"\bin\s+my\s+view\b",
    r"\bwe\s+think\b",
    r"\bwe\s+believe\b",
    r"\bour\s+view\b",
    r"\bi\s+argue\b",
    r"\bwe\s+argue\b",
]

NORMATIVE_CALL = [
    r"\bshould\b",
    r"\bmust\b",
    r"\bneed\s+to\b",
    r"\bhave\s+to\b",
]

VALUE_JUDGMENT = [
    r"\boutrageous\b",
    r"\bdisgraceful\b",
    r"\bshameful\b",
    r"\babsurd\b",
    r"\bridiculous\b",
]

STANCE_RE = [re.compile(p, re.IGNORECASE) for p in FIRST_PERSON_STANCE]
NORM_RE = [re.compile(p, re.IGNORECASE) for p in NORMATIVE_CALL]
VALUE_RE = [re.compile(p, re.IGNORECASE) for p in VALUE_JUDGMENT]


# Interpretation strong signals:
# Require >=2 signals AND not overridden by commentary strong signals.
INTERPRET_SIGNALS = [
    r"\bwhat\s+it\s+means\b",
    r"\bwhy\s+it\s+matters\b",
    r"\bthis\s+means\b",
    r"\bsignals?\b",
    r"\bindicates?\b",
    r"\bsuggests?\b",
    r"\blikely\b",
    r"\bunlikely\b",
    r"\bcould\s+lead\s+to\b",
    r"\bmay\s+lead\s+to\b",
    r"\brisk\b",
    r"\bimpact\b",
    r"\bbecause\b",
    r"\btherefore\b",
]

INTERPRET_RE = [re.compile(p, re.IGNORECASE) for p in INTERPRET_SIGNALS]


def _safe_text(s: Optional[str]) -> str:
    if not s:
        return ""
    # normalize whitespace; keep it simple
    return " ".join(s.strip().split())


def _match_any(res: List[re.Pattern], text: str) -> bool:
    return any(r.search(text) for r in res)


def _count_matches(res: List[re.Pattern], text: str) -> int:
    return sum(1 for r in res if r.search(text))


@dataclass(frozen=True)
class ArticleTypingResult:
    article_type: str
    reasons: List[str]


def classify_article_type(
    title: Optional[str],
    summary: Optional[str],
    url: Optional[str] = None,
) -> ArticleTypingResult:
    """
    Conservative v0 classifier.
    Priority: COMMENTARY > INTERPRETATION > FACT.
    Default: FACT.
    """
    t = _safe_text(title)
    s = _safe_text(summary)
    u = _safe_text(url)
    text = (t + " " + s).strip()

    reasons: List[str] = []

    # --- Step A: URL section signals (strongest, publisher self-label) ---
    if u and _match_any(URL_OPINION_RE, u):
        return ArticleTypingResult(TYPE_COMMENTARY, [R_URL_OPINION])

    if u and _match_any(URL_ANALYSIS_RE, u):
        return ArticleTypingResult(TYPE_INTERPRETATION, [R_URL_ANALYSIS])

    # --- Step B: Title prefix signals (strong) ---
    if t and _match_any(TITLE_PREFIX_OPINION_RE, t):
        return ArticleTypingResult(TYPE_COMMENTARY, [R_TITLE_PREFIX_OPINION])

    if t and _match_any(TITLE_PREFIX_ANALYSIS_RE, t):
        return ArticleTypingResult(TYPE_INTERPRETATION, [R_TITLE_PREFIX_ANALYSIS])

    # --- Step C: Text strong signals (strict thresholds) ---
    # Commentary by text requires >=2 categories hit.
    stance_hit = _count_matches(STANCE_RE, text) > 0
    norm_hit = _count_matches(NORM_RE, text) > 0
    value_hit = _count_matches(VALUE_RE, text) > 0
    commentary_cats = sum([stance_hit, norm_hit, value_hit])

    if commentary_cats >= 2:
        reasons.append(R_TEXT_COMMENTARY_STRONG)
        return ArticleTypingResult(TYPE_COMMENTARY, reasons)

    # Interpretation by text requires >=2 interpret signals and no strong commentary.
    interpret_hits = _count_matches(INTERPRET_RE, text)
    if interpret_hits >= 2:
        reasons.append(R_TEXT_INTERPRET_STRONG)
        return ArticleTypingResult(TYPE_INTERPRETATION, reasons)

    # --- Default ---
    return ArticleTypingResult(TYPE_FACT, [R_DEFAULT_FACT])
