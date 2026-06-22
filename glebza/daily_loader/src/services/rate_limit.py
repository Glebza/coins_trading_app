"""T-Invest RESOURCE_EXHAUSTED retry helpers."""

from __future__ import annotations

import logging
import re
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

_RATE_LIMIT_RESET_RE = re.compile(r"ratelimit_reset=['\"]?(\d+(?:\.\d+)?)")

T = TypeVar("T")


def is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "RESOURCE_EXHAUSTED" in text
        or "resource exhausted" in text.lower()
        or "ratelimit_reset" in text
    )


def rate_limit_sleep_seconds(exc: Exception, *, fallback: float) -> float:
    match = _RATE_LIMIT_RESET_RE.search(str(exc))
    if not match:
        return fallback
    return max(0.0, float(match.group(1)) + 1.0)


def call_with_rate_limit_retries(
    fn: Callable[[], T],
    *,
    label: str,
    retries: int = 3,
    fallback_sleep_seconds: float = 60.0,
) -> T:
    if retries < 0:
        raise ValueError("retries must be non-negative")
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception as exc:
            if not is_rate_limit_error(exc) or attempt >= retries:
                raise
            sleep_seconds = rate_limit_sleep_seconds(exc, fallback=fallback_sleep_seconds)
            logger.warning(
                "rate limited label=%s attempt=%s/%s sleep_seconds=%.1f",
                label,
                attempt + 1,
                retries,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
    raise RuntimeError(f"rate limit retries exhausted label={label}")
