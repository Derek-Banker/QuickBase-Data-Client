from __future__ import annotations

from typing import Any


def _format_detail(value: Any) -> str:
    if isinstance(value, BaseException):
        return f"{type(value).__name__}: {value}"
    return repr(value)


def format_error_message(
    summary: str,
    *,
    operation: str | None = None,
    endpoint: str | None = None,
    object_ref: str | None = None,
    **context: Any,
) -> str:
    details: list[str] = []

    if operation:
        details.append(f"operation={operation}")
    if endpoint:
        details.append(f"endpoint={endpoint}")
    if object_ref:
        details.append(f"object={object_ref}")

    for key, value in context.items():
        if value is None:
            continue
        details.append(f"{key}={_format_detail(value)}")

    if not details:
        return summary
    return f"{summary} [{', '.join(details)}]"


class QuickbaseError(Exception):
    """Base exception for package-level Quickbase failures."""


class QuickbaseValidationError(QuickbaseError, ValueError):
    """Raised when caller input is invalid for the requested operation."""


class QuickbaseConfigurationError(QuickbaseValidationError):
    """Raised when local package configuration or paths are invalid."""


class QuickbaseTransportError(QuickbaseError):
    """Raised for network or transport failures before a valid HTTP response exists."""


class QuickbaseHTTPError(QuickbaseError):
    """Raised when Quickbase returns an unsuccessful HTTP response."""


class QuickbaseAuthError(QuickbaseHTTPError, PermissionError):
    """Raised for authentication or authorization failures."""


class QuickbaseRateLimitError(QuickbaseHTTPError):
    """Raised when Quickbase responds with a rate-limit failure."""


class QuickbaseSchemaError(QuickbaseError):
    """Raised for schema cache loading or lookup failures."""


class QuickbaseNotFoundError(QuickbaseError, LookupError):
    """Raised when a requested Quickbase object or local schema entity is missing."""


class QuickbasePayloadError(QuickbaseValidationError):
    """Raised when request or response payload content is invalid."""


__all__ = [
    "QuickbaseAuthError",
    "QuickbaseConfigurationError",
    "QuickbaseError",
    "QuickbaseHTTPError",
    "QuickbaseNotFoundError",
    "QuickbasePayloadError",
    "QuickbaseRateLimitError",
    "QuickbaseSchemaError",
    "QuickbaseTransportError",
    "QuickbaseValidationError",
    "format_error_message",
]
