import logging
import sys

import structlog

from app.core.config import settings


def setup_logging():
    # Clear existing handlers to avoid duplicates
    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if settings.ENV == "production":
        # Output structured JSON logs in production
        processors = shared_processors + [structlog.processors.JSONRenderer()]
    else:
        # Output colorized logs in development
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Standard python log output to stdout
    handler = logging.StreamHandler(sys.stdout)
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
