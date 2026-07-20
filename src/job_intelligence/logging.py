"""Structured logging via structlog.

Provides a `get_logger()` and a `configure_logging()` entry point. Fields such as
workflow_id / run_id / company / activity are bound onto the logger by callers
(workflows and activities) so every line carries run context.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from .config import load_yaml_config

_CONFIGURED = False

# Fields that must never be emitted in full (privacy + log volume).
_DEFAULT_REDACT = {"description_text", "raw_payload_json", "raw_payload"}


def _redact_processor(redact: set[str]) -> structlog.types.Processor:
    def processor(
        _logger: structlog.types.WrappedLogger, _name: str, event_dict: structlog.types.EventDict
    ) -> structlog.types.EventDict:
        for key in list(event_dict):
            if key in redact and event_dict[key] is not None:
                event_dict[key] = "<redacted>"
        return event_dict

    return processor


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    try:
        cfg = load_yaml_config("logging.yml")
    except Exception:
        cfg = {}

    level_name = str(cfg.get("level", "INFO")).upper()
    renderer_name = str(cfg.get("renderer", "console"))
    redact = _DEFAULT_REDACT | set(cfg.get("redact_fields", []))

    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level_name, logging.INFO)
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if renderer_name == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact_processor(redact),
            structlog.processors.StackInfoRenderer(),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level_name, logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None, **initial: Any) -> structlog.stdlib.BoundLogger:
    configure_logging()
    logger = structlog.get_logger(name)
    return logger.bind(**initial) if initial else logger
