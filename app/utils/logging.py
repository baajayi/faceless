"""Structured logging with run_id context via structlog."""
import logging
import sys
from contextvars import ContextVar
from typing import Optional

import structlog

from app.settings import settings

# Context variable carries run_id across async / threaded boundaries
_run_id_var: ContextVar[Optional[str]] = ContextVar("run_id", default=None)


def set_run_id(run_id: str) -> None:
    _run_id_var.set(run_id)


def get_run_id() -> Optional[str]:
    return _run_id_var.get()


def _add_run_id(logger, method_name, event_dict):  # noqa: ANN001
    run_id = _run_id_var.get()
    if run_id:
        event_dict["run_id"] = run_id
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_run_id,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
            if settings.LOG_LEVEL == "DEBUG"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def get_logger(name: str = __name__) -> structlog.BoundLogger:
    return structlog.get_logger(name)


# Auto-configure on import
configure_logging()
