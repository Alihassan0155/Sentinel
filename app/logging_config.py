"""Compact JSON logs with consistent context fields."""

import json
import logging
import sys
from datetime import datetime, timezone


CONTEXT_FIELDS = (
    "event", "request_id", "watch_id", "change_id", "job_id", "url",
    "duration_ms", "status", "model", "attempt", "notification_id",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CONTEXT_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, ensure_ascii=False)


def configure_logging() -> None:
    root = logging.getLogger()
    if any(getattr(handler, "sentinel_json", False) for handler in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.sentinel_json = True
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
