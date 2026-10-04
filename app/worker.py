"""Run Sentinel's scheduled jobs outside the API process."""

import logging
import signal
from threading import Event

from app.logging_config import configure_logging
from app.services.scheduler import scheduler, start_scheduler


def main() -> None:
    configure_logging()
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    start_scheduler()
    logging.getLogger(__name__).info("Sentinel worker started", extra={
        "event": "worker_started",
    })
    try:
        stop.wait()
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
