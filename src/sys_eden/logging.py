"""Structured application logging, separate from durable reports."""

import json
import logging
from datetime import UTC, datetime
from typing import TextIO


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Arbitrary extras and exception text can contain private adapter/config data.
        return json.dumps({
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "component": record.name,
            "level": record.levelname,
            "event_type": getattr(record, "event_type", "application"),
            "task_id": getattr(record, "task_id", None),
            "report_id": getattr(record, "report_id", None),
            "message": record.getMessage(),
        })


def configure_logging(stream: TextIO | None = None) -> logging.Logger:
    """Configure only Eden's logger; callers must use non-sensitive messages/IDs."""
    logger = logging.getLogger("sys_eden")
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
