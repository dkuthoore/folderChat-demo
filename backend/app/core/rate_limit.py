"""In-memory rate limiter for ingest endpoint."""

from __future__ import annotations

import threading
import time
from collections import defaultdict

from fastapi import HTTPException, status

MINUTE = 60
HOUR = 3600
MAX_INGEST_PER_MINUTE = 3
MAX_INGEST_PER_HOUR = 10

_store: dict[str, list[float]] = defaultdict(list)
_lock = threading.Lock()

INGEST_RATE_LIMIT_MESSAGE = (
    "You're running ingestions too quickly. Please wait a bit before trying again."
)


def check_ingest_rate_limit(user_id: str) -> None:
    """
    Check ingest rate limit for the given user. Raises HTTPException 429 if over limit.
    Counts all requests (valid or invalid) to prevent abuse.
    """
    now = time.monotonic()
    with _lock:
        timestamps = _store[user_id]
        # Prune timestamps older than 1 hour
        timestamps[:] = [t for t in timestamps if now - t < HOUR]

        count_minute = sum(1 for t in timestamps if now - t < MINUTE)
        count_hour = len(timestamps)

        if count_minute >= MAX_INGEST_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=INGEST_RATE_LIMIT_MESSAGE,
                headers={"Retry-After": "60"},
            )
        if count_hour >= MAX_INGEST_PER_HOUR:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=INGEST_RATE_LIMIT_MESSAGE,
                headers={"Retry-After": "3600"},
            )

        timestamps.append(now)
