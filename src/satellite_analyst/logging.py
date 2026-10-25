"""Structured JSON logging module for satellite-analyst."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Include contextual fields passed via extra
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if hasattr(record, "job_id"):
            log_entry["job_id"] = record.job_id
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON formatting."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Avoid duplicate handlers
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        root_logger.addHandler(handler)
    else:
        for existing_handler in root_logger.handlers:
            existing_handler.setFormatter(JSONFormatter())


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured with structured output."""
    return logging.getLogger(name)
