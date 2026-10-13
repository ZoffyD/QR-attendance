"""Tiny in-memory limiter for the public student endpoints (resets when the server restarts)."""
import time
from collections import defaultdict

from fastapi import HTTPException

_hits: dict[str, list[float]] = defaultdict(list)


def check(key: str, limit: int, window: int) -> None:
    now = time.time()
    _hits[key] = [t for t in _hits[key] if now - t < window]
    if len(_hits[key]) >= limit:
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again.")


def record(key: str) -> None:
    _hits[key].append(time.time())


def clear() -> None:
    _hits.clear()
