from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict


_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class _UtcFormatter(logging.Formatter):
    converter = datetime.utcfromtimestamp


def get_logger(name: str | None = None, level: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name or "observability")
    if logger.handlers:
        return logger

    log_level = (level or os.getenv("LOG_LEVEL") or "INFO").upper()
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)
    handler.setFormatter(_UtcFormatter(_DEFAULT_FORMAT))
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_json(event: str, **fields: Any) -> None:
    payload: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
