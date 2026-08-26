"""Exceptions for the Confluence client.

Mirrors the structure of src/utils_v2/jira/exceptions.py so both clients
fail the same way and the subagents can handle them identically.
"""

from src.utils_v2.logger import shared_logger

logger = shared_logger(__name__)


class ConfluenceException(Exception):
    """Base for every failure raised by the Confluence client."""

    def __init__(self, message, status_code=None, page_id=None, url=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.page_id = page_id
        self.url = url

    def __str__(self):
        parts = [self.message]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.page_id is not None:
            parts.append(f"page_id={self.page_id}")
        return " | ".join(parts)


class ConfluenceAuthError(ConfluenceException):
    """401 or 403. Token missing, expired, or lacking space permission."""


class ConfluenceNotFoundError(ConfluenceException):
    """404. Page deleted, archived, or the id/title never existed."""


class ConfluenceRateLimitError(ConfluenceException):
    """429. Includes retry_after seconds when the server sends it."""

    def __init__(self, message, retry_after=None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ConfluenceConfigError(ConfluenceException):
    """Required environment configuration is missing or malformed."""


def handle_confluence_exception(exc, context=""):
    """Log a Confluence failure and return a serialisable dict.

    Used by the subagent so one bad page reference does not abort the
    whole evidence check. The returned dict is safe to drop straight
    into state.
    """
    prefix = f"[{context}] " if context else ""

    if isinstance(exc, ConfluenceException):
        logger.error(f"{prefix}{exc}")
        return {
            "error_type": type(exc).__name__,
            "message": exc.message,
            "status_code": exc.status_code,
            "page_id": exc.page_id,
            "url": exc.url,
        }

    logger.exception(f"{prefix}Unexpected Confluence failure: {exc}")
    return {
        "error_type": type(exc).__name__,
        "message": str(exc),
        "status_code": None,
        "page_id": None,
        "url": None,
    }
