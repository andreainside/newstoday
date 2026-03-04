from __future__ import annotations

import os
import random
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Sequence

import httpx

from app.observability import log_json

DEEPSEEK_PROVIDER = "deepseek"

MAX_INPUT_TITLES = 6

_LAST_CALL_LOCK = Lock()
_LAST_CALL_STATUS: Dict[str, Any] = {
    "ts": None,
    "provider": DEEPSEEK_PROVIDER,
    "model": None,
    "status": "NEVER_CALLED",
    "error_type": None,
    "http_status": None,
    "latency_ms": None,
}


def current_deepseek_settings() -> Dict[str, Any]:
    return {
        "provider": DEEPSEEK_PROVIDER,
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "timeout_seconds": float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20")),
    }


def _set_last_call_status(**fields: Any) -> None:
    with _LAST_CALL_LOCK:
        _LAST_CALL_STATUS.update(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                **fields,
            }
        )


def get_last_deepseek_call_status() -> Dict[str, Any]:
    with _LAST_CALL_LOCK:
        return dict(_LAST_CALL_STATUS)


def _compact_titles(article_titles: Sequence[str]) -> List[str]:
    cleaned: List[str] = []
    seen = set()
    for raw in article_titles:
        title = (raw or "").strip()
        if not title:
            continue
        title = " ".join(title.split())
        title = title[:160]
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(title)
    return cleaned


def _pick_titles_for_prompt(article_titles: Sequence[str]) -> List[str]:
    cleaned = _compact_titles(article_titles)
    if len(cleaned) <= MAX_INPUT_TITLES:
        return cleaned

    picked_indices = sorted(random.sample(range(len(cleaned)), MAX_INPUT_TITLES))
    return [cleaned[i] for i in picked_indices]


def _normalize_title(text: str) -> str:
    title = (text or "").strip().strip("\"'`")
    title = " ".join(title.split())
    return title[:140]


def _log_deepseek_call(
    *,
    event_id: int | None,
    model: str,
    status: str,
    error_type: str | None,
    http_status: int | None,
    latency_ms: int,
    cache_hit: bool,
) -> None:
    log_json(
        "deepseek_call",
        event_id=event_id,
        provider=DEEPSEEK_PROVIDER,
        model=model,
        status=status,
        error_type=error_type,
        http_status=http_status,
        latency_ms=latency_ms,
        cache_hit=cache_hit,
    )
    _set_last_call_status(
        provider=DEEPSEEK_PROVIDER,
        model=model,
        status=status,
        error_type=error_type,
        http_status=http_status,
        latency_ms=latency_ms,
    )


def summarize_event_title(article_titles: Sequence[str], event_id: int | None = None) -> Dict[str, Any]:
    settings = current_deepseek_settings()
    sampled_titles = _pick_titles_for_prompt(article_titles)
    if not sampled_titles:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="SKIPPED",
            error_type="empty_article_titles",
            http_status=None,
            latency_ms=0,
            cache_hit=False,
        )
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": "empty_article_titles",
        }

    if not settings["api_key"]:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="SKIPPED",
            error_type="missing_deepseek_api_key",
            http_status=None,
            latency_ms=0,
            cache_hit=False,
        )
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": "missing_deepseek_api_key",
        }

    system_prompt = (
        "You are a senior news editor. Generate one concise event title from input article headlines. "
        "Return only the title text. Keep it specific, factual, and under 16 words."
    )
    user_lines = [f"{idx + 1}. {t}" for idx, t in enumerate(sampled_titles)]
    user_prompt = "Article headlines:\n" + "\n".join(user_lines)

    url = f"{settings['base_url']}/chat/completions"
    payload = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 48,
    }
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }

    started = time.monotonic()
    try:
        with httpx.Client(timeout=settings["timeout_seconds"]) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        latency_ms = int((time.monotonic() - started) * 1000)
    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type="http_status_error",
            http_status=exc.response.status_code,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": f"deepseek_request_failed: {exc}",
            "http_status": exc.response.status_code,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type=type(exc).__name__,
            http_status=None,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": f"deepseek_request_failed: {exc}",
        }

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(data, dict)
        else None
    )
    normalized = _normalize_title(content or "")
    if not normalized:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type="deepseek_empty_content",
            http_status=resp.status_code,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": "deepseek_empty_content",
        }

    _log_deepseek_call(
        event_id=event_id,
        model=settings["model"],
        status="SUCCESS",
        error_type=None,
        http_status=resp.status_code,
        latency_ms=latency_ms,
        cache_hit=False,
    )
    return {
        "ok": True,
        "title": normalized,
        "provider": settings["provider"],
        "model": settings["model"],
        "sampled_titles": sampled_titles,
        "error": None,
    }


def translate_title_to_zh(title: str, event_id: int | None = None) -> Dict[str, Any]:
    settings = current_deepseek_settings()
    source = " ".join((title or "").split()).strip()
    if not source:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="SKIPPED",
            error_type="empty_source_title",
            http_status=None,
            latency_ms=0,
            cache_hit=False,
        )
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": "empty_source_title",
        }
    if not settings["api_key"]:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="SKIPPED",
            error_type="missing_deepseek_api_key",
            http_status=None,
            latency_ms=0,
            cache_hit=False,
        )
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": "missing_deepseek_api_key",
        }

    system_prompt = (
        "You are a bilingual news editor. Translate the headline to concise Simplified Chinese. "
        "Keep headline style. Return only translated title text."
    )
    user_prompt = f"Headline: {source}"
    url = f"{settings['base_url']}/chat/completions"
    payload = {
        "model": settings["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 96,
    }
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    started = time.monotonic()
    try:
        with httpx.Client(timeout=settings["timeout_seconds"]) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        latency_ms = int((time.monotonic() - started) * 1000)
    except httpx.HTTPStatusError as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type="http_status_error",
            http_status=exc.response.status_code,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": f"deepseek_request_failed: {exc}",
            "http_status": exc.response.status_code,
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - started) * 1000)
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type=type(exc).__name__,
            http_status=None,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": f"deepseek_request_failed: {exc}",
        }

    content = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
        if isinstance(data, dict)
        else None
    )
    translated = _normalize_title(content or "")
    if not translated:
        _log_deepseek_call(
            event_id=event_id,
            model=settings["model"],
            status="ERROR",
            error_type="deepseek_empty_content",
            http_status=resp.status_code,
            latency_ms=latency_ms,
            cache_hit=False,
        )
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": "deepseek_empty_content",
        }

    _log_deepseek_call(
        event_id=event_id,
        model=settings["model"],
        status="SUCCESS",
        error_type=None,
        http_status=resp.status_code,
        latency_ms=latency_ms,
        cache_hit=False,
    )
    return {
        "ok": True,
        "translated_title": translated,
        "provider": settings["provider"],
        "model": settings["model"],
        "error": None,
    }


def probe_deepseek_connectivity(timeout_seconds: float = 2.0) -> Dict[str, Any]:
    settings = current_deepseek_settings()
    if not settings["api_key"]:
        return {
            "ok": False,
            "reason": "missing_deepseek_api_key",
            "http_status": None,
        }

    url = f"{settings['base_url']}/chat/completions"
    payload = {
        "model": settings["model"],
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {settings['api_key']}",
        "Content-Type": "application/json",
    }
    started = time.monotonic()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            resp = client.post(url, json=payload, headers=headers)
        return {
            "ok": resp.status_code < 500,
            "reason": "ok" if resp.status_code < 500 else "upstream_5xx",
            "http_status": resp.status_code,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": type(exc).__name__,
            "http_status": None,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
