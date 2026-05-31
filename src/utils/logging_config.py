"""Structured logging utility with request_id tracking using contextvars (Phase P5)."""

import contextvars
import logging
import uuid

# Context variable to hold the request ID for the current thread/task context
request_id_ctx_var = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    """Retrieve the current request ID from context."""
    return request_id_ctx_var.get()


def set_request_id(request_id: str | None = None) -> str:
    """Set the request ID for the current context. Generates a new UUID if none is provided."""
    req_id = request_id or str(uuid.uuid4())
    request_id_ctx_var.set(req_id)
    return req_id


def clear_request_id() -> None:
    """Clear the request ID from the current context."""
    request_id_ctx_var.set("")


class RequestIdFilter(logging.Filter):
    """Logging filter to inject request_id from contextvars into all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        req_id = get_request_id()
        # format placeholder will fall back to '-' if request ID is empty
        record.request_id = req_id if req_id else "-"
        return True


def setup_logging(level: int = logging.INFO) -> None:
    """Set up log formatting with request ID mapping for all stream handlers."""
    # Ensure root logger config is initialized
    root_logger = logging.getLogger()
    
    # Create request filter
    req_filter = RequestIdFilter()

    # If root logger has no handlers, configure one
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        root_logger.addHandler(handler)

    # Use a custom format that displays the request ID
    log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s"
    formatter = logging.Formatter(log_format)

    # Set formatter and add filter to all root handlers
    for handler in root_logger.handlers:
        handler.addFilter(req_filter)
        handler.setFormatter(formatter)

    root_logger.setLevel(level)

    # Make sure we also configure other loggers (like uvicorn and app loggers)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "src"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(req_filter)
        for handler in logger.handlers:
            handler.addFilter(req_filter)
            handler.setFormatter(formatter)
