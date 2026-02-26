from __future__ import annotations


CANONICAL = {"FACT", "INTERPRETATION", "COMMENTARY"}


def effective_type(raw_type: str | None) -> str:
    if raw_type is None:
        return "UNKNOWN"

    t = str(raw_type).strip().upper()
    if not t:
        return "UNKNOWN"
    if t in CANONICAL:
        return t

    if t in {"ANALYSIS", "EXPLAINER"}:
        return "INTERPRETATION"
    if t in {"OPINION", "EDITORIAL", "COMMENT"}:
        return "COMMENTARY"

    return "UNKNOWN"
