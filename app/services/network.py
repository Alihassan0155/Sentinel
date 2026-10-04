"""Shared website request budget and bounded HTTP retries."""

import logging
import random
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import text

from app.config import settings
from app.database import engine

logger = logging.getLogger(__name__)
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class RateLimitDeferred(Exception):
    """The shared request budget cannot grant a slot soon enough."""


def wait_for_rate_slot(key: str, interval_seconds: float) -> None:
    if interval_seconds <= 0:
        return
    now = datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(text("""
            INSERT INTO rate_limits (key, next_allowed_at)
            VALUES (:key, :now) ON CONFLICT (key) DO NOTHING
        """), {"key": key, "now": now})
        scheduled = connection.execute(text("""
            SELECT next_allowed_at FROM rate_limits WHERE key = :key FOR UPDATE
        """), {"key": key}).scalar_one()
        delay = max(0.0, (scheduled - now).total_seconds())
        if delay > settings.max_rate_wait_seconds:
            raise RateLimitDeferred(f"Rate limit for {key} deferred by {delay:.1f}s")
        next_allowed = max(now, scheduled) + timedelta(seconds=interval_seconds)
        connection.execute(text("""
            UPDATE rate_limits SET next_allowed_at = :next_allowed WHERE key = :key
        """), {"key": key, "next_allowed": next_allowed})
    if delay:
        time.sleep(delay)


def _rate_key(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only HTTP and HTTPS website URLs are supported")
    return f"host:{parsed.hostname.lower()}"


def get_page(client: httpx.Client, url: str) -> httpx.Response:
    last_error = None
    for attempt in range(1, settings.http_retry_attempts + 1):
        wait_for_rate_slot(_rate_key(url), settings.website_min_interval_seconds)
        started = time.monotonic()
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > settings.http_max_bytes:
                        raise ValueError(f"Page exceeds {settings.http_max_bytes} bytes")
                    chunks.append(chunk)
                result = httpx.Response(
                    response.status_code, headers=response.headers,
                    request=response.request, content=b"".join(chunks),
                )
            logger.info("Website request completed", extra={
                "event": "website_fetch", "url": str(result.url),
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "status": result.status_code, "attempt": attempt,
            })
            return result
        except (httpx.TransportError, httpx.HTTPStatusError) as error:
            last_error = error
            retryable = (
                isinstance(error, httpx.TransportError)
                or error.response.status_code in RETRYABLE_STATUSES
            )
            if not retryable or attempt >= settings.http_retry_attempts:
                raise
            delay = min(4.0, 0.5 * 2 ** (attempt - 1)) + random.uniform(0, 0.2)
            logger.warning("Website request retry", extra={
                "event": "website_retry", "url": url, "attempt": attempt,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            })
            time.sleep(delay)
    raise last_error


def website_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_seconds, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"
        )},
    )
