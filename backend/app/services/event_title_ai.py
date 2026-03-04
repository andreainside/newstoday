from __future__ import annotations

import os
import random
from typing import Any, Dict, List, Sequence

import httpx

DEEPSEEK_PROVIDER = "deepseek"

MAX_INPUT_TITLES = 6


def current_deepseek_settings() -> Dict[str, Any]:
    return {
        "provider": DEEPSEEK_PROVIDER,
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        "api_key": os.getenv("DEEPSEEK_API_KEY", ""),
        "timeout_seconds": float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "20")),
    }


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


def summarize_event_title(article_titles: Sequence[str]) -> Dict[str, Any]:
    settings = current_deepseek_settings()
    sampled_titles = _pick_titles_for_prompt(article_titles)
    if not sampled_titles:
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": "empty_article_titles",
        }

    if not settings["api_key"]:
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

    try:
        with httpx.Client(timeout=settings["timeout_seconds"]) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
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
        return {
            "ok": False,
            "title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "sampled_titles": sampled_titles,
            "error": "deepseek_empty_content",
        }

    return {
        "ok": True,
        "title": normalized,
        "provider": settings["provider"],
        "model": settings["model"],
        "sampled_titles": sampled_titles,
        "error": None,
    }


def translate_title_to_zh(title: str) -> Dict[str, Any]:
    settings = current_deepseek_settings()
    source = " ".join((title or "").split()).strip()
    if not source:
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": "empty_source_title",
        }
    if not settings["api_key"]:
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
    try:
        with httpx.Client(timeout=settings["timeout_seconds"]) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
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
        return {
            "ok": False,
            "translated_title": None,
            "provider": settings["provider"],
            "model": settings["model"],
            "error": "deepseek_empty_content",
        }
    return {
        "ok": True,
        "translated_title": translated,
        "provider": settings["provider"],
        "model": settings["model"],
        "error": None,
    }
