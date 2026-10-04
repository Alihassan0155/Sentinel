"""Timed and rate-limited Gemini calls with SDK retries."""

import logging
import time
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings
from app.services.network import wait_for_rate_slot

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def client():
    return genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=settings.gemini_timeout_ms,
            retry_options=types.HttpRetryOptions(
                attempts=3, initial_delay=1.0, max_delay=8.0,
                exp_base=2.0, http_status_codes=[429, 500, 502, 503, 504],
            ),
        ),
    )


def generate(*, model: str, contents: str, config: dict, operation: str):
    wait_for_rate_slot("api:gemini", settings.gemini_min_interval_seconds)
    started = time.monotonic()
    try:
        result = client().models.generate_content(
            model=model, contents=contents, config=config,
        )
        logger.info("Gemini call completed", extra={
            "event": f"llm_{operation}", "model": model,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "status": "ok",
        })
        return result
    except Exception:
        logger.exception("Gemini call failed", extra={
            "event": f"llm_{operation}", "model": model,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "status": "failed",
        })
        raise


def embed(*, model: str, content: str, dimensions: int):
    wait_for_rate_slot("api:gemini", settings.gemini_min_interval_seconds)
    started = time.monotonic()
    try:
        result = client().models.embed_content(
            model=model, contents=content,
            config=types.EmbedContentConfig(output_dimensionality=dimensions),
        )
        logger.info("Gemini embedding completed", extra={
            "event": "llm_embedding", "model": model,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "status": "ok",
        })
        return result
    except Exception:
        logger.exception("Gemini embedding failed", extra={
            "event": "llm_embedding", "model": model,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "status": "failed",
        })
        raise
