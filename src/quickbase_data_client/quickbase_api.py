from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version
from typing import TYPE_CHECKING, Any, Callable, Dict, Literal, Mapping

import requests

from quickbase_data_client.config import (
    BASE_URL,
    DEFAULT_MAX_FILE_SIZE,
    DEFAULT_MAX_REQUEST_SIZE,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_COUNT,
    DEFAULT_RETRY_JITTER,
    DEFAULT_RETRYABLE_STATUS_CODES,
)
from quickbase_data_client.exceptions import (
    QuickbaseAuthError,
    QuickbaseConfigurationError,
    QuickbaseError,
    QuickbaseHTTPError,
    QuickbaseNotFoundError,
    QuickbaseRateLimitError,
    QuickbaseTransportError,
    QuickbaseValidationError,
    format_error_message,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quickbase_data_client.app import App
    from quickbase_data_client.identifier import Identifier
    from quickbase_data_client.schema_cache import SchemaCache
    from quickbase_data_client.table import Table

# SDK VERSION
try:
    __version__ = _version("quickbase-data-client")
except PackageNotFoundError:
    __version__ = "0.0.0"

# DEFAULT UA COMPONENTS
DEFAULT_USER_AGENT: Dict[str, str] = {
    "Base": "QuickBase-Data-Client",
    "Version": __version__,
    "Suffix": "Auth",
    "Separator": "-",
}

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}
MAX_ERROR_BODY_CHARS = 500

RequestTimeout = float | tuple[float, float]
RequestLogHook = Callable[[dict[str, Any]], None]


def _normalize_timeout(timeout: RequestTimeout) -> RequestTimeout:
    if isinstance(timeout, bool):
        raise QuickbaseConfigurationError(
            format_error_message(
                "timeout must be a positive number or a (connect, read) tuple.",
                operation="RequestConfig.__post_init__",
                timeout=timeout,
            )
        )

    if isinstance(timeout, (int, float)):
        timeout_value = float(timeout)
        if timeout_value <= 0:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "timeout must be greater than zero.",
                    operation="RequestConfig.__post_init__",
                    timeout=timeout,
                )
            )
        return timeout_value

    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        try:
            connect_timeout = float(timeout[0])
            read_timeout = float(timeout[1])
        except (TypeError, ValueError) as exc:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "timeout tuple values must be numeric.",
                    operation="RequestConfig.__post_init__",
                    timeout=timeout,
                    cause=exc,
                )
            ) from exc

        if connect_timeout <= 0 or read_timeout <= 0:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "timeout tuple values must be greater than zero.",
                    operation="RequestConfig.__post_init__",
                    timeout=timeout,
                )
            )
        return (connect_timeout, read_timeout)

    raise QuickbaseConfigurationError(
        format_error_message(
            "timeout must be a positive number or a (connect, read) tuple.",
            operation="RequestConfig.__post_init__",
            timeout=timeout,
        )
    )


@dataclass(frozen=True)
class RequestConfig:
    """Configuration for QuickBase request timeout, retry, and logging behavior."""

    timeout: RequestTimeout = DEFAULT_REQUEST_TIMEOUT
    retry_count: int = DEFAULT_RETRY_COUNT
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: DEFAULT_RETRYABLE_STATUS_CODES
    )
    backoff_factor: float = DEFAULT_RETRY_BACKOFF_FACTOR
    jitter: float = DEFAULT_RETRY_JITTER
    respect_retry_after: bool = True
    request_log_hook: RequestLogHook | None = None
    response_log_hook: RequestLogHook | None = None
    max_request_size_kb: float = DEFAULT_MAX_REQUEST_SIZE
    max_file_size_kb: float = DEFAULT_MAX_FILE_SIZE

    def __post_init__(self) -> None:
        object.__setattr__(self, "timeout", _normalize_timeout(self.timeout))
        try:
            retryable_status_codes = frozenset(self.retryable_status_codes)
        except TypeError as exc:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "retryable_status_codes must be an iterable of HTTP status codes.",
                    operation="RequestConfig.__post_init__",
                    retryable_status_codes=self.retryable_status_codes,
                    cause=exc,
                )
            ) from exc
        object.__setattr__(self, "retryable_status_codes", retryable_status_codes)

        if (
            isinstance(self.retry_count, bool)
            or not isinstance(self.retry_count, int)
            or self.retry_count < 0
        ):
            raise QuickbaseConfigurationError(
                format_error_message(
                    "retry_count must be a non-negative integer.",
                    operation="RequestConfig.__post_init__",
                    retry_count=self.retry_count,
                )
            )

        if (
            isinstance(self.backoff_factor, bool)
            or not isinstance(self.backoff_factor, (int, float))
            or self.backoff_factor < 0
        ):
            raise QuickbaseConfigurationError(
                format_error_message(
                    "backoff_factor must be non-negative.",
                    operation="RequestConfig.__post_init__",
                    backoff_factor=self.backoff_factor,
                )
            )
        object.__setattr__(self, "backoff_factor", float(self.backoff_factor))

        if (
            isinstance(self.jitter, bool)
            or not isinstance(self.jitter, (int, float))
            or self.jitter < 0
        ):
            raise QuickbaseConfigurationError(
                format_error_message(
                    "jitter must be non-negative.",
                    operation="RequestConfig.__post_init__",
                    jitter=self.jitter,
                )
            )
        object.__setattr__(self, "jitter", float(self.jitter))

        for field_name, value in (
            ("max_request_size_kb", self.max_request_size_kb),
            ("max_file_size_kb", self.max_file_size_kb),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise QuickbaseConfigurationError(
                    (
                        f"{field_name} must be greater than zero. "
                        f"[operation=RequestConfig.__post_init__, {field_name}={value!r}]"
                    )
                )
            object.__setattr__(self, field_name, float(value))

        invalid_status_codes = [
            status_code
            for status_code in self.retryable_status_codes
            if not isinstance(status_code, int) or status_code < 100 or status_code > 599
        ]
        if invalid_status_codes:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "retryable_status_codes contains invalid HTTP status codes.",
                    operation="RequestConfig.__post_init__",
                    invalid_status_codes=invalid_status_codes,
                )
            )

        for hook_name, hook in (
            ("request_log_hook", self.request_log_hook),
            ("response_log_hook", self.response_log_hook),
        ):
            if hook is not None and not callable(hook):
                raise QuickbaseConfigurationError(
                    format_error_message(
                        f"{hook_name} must be callable when provided.",
                        operation="RequestConfig.__post_init__",
                        hook_name=hook_name,
                        hook_type=type(hook).__name__,
                    )
                )


def assemble_user_agent(cfg: Dict[str, str]) -> str:
    final = DEFAULT_USER_AGENT.copy()
    final.update(cfg or {})
    sep = final["Separator"]
    parts = [final["Base"], final["Version"]]
    if final.get("Suffix"):
        parts.append(final["Suffix"])
    return sep.join(parts)


class Auth:
    """
    Encapsulates realm + user token, and assembles a flexible User-Agent.
    """

    def __init__(
        self,
        realm: str,
        user_token: str,
        *,
        user_agent: Dict[str, str] | None = None,
    ):
        self.realm = realm
        self.user_token = user_token
        self._user_agent = assemble_user_agent(user_agent or {})

    @property
    def user_agent(self) -> str:
        return self._user_agent

    @user_agent.setter
    def user_agent(self, cfg: Dict[str, str]):
        self._user_agent = assemble_user_agent(cfg)

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "QB-Realm-Hostname": self.realm,
            "Authorization": f"QB-USER-TOKEN {self.user_token}",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }

    def session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(self.headers)
        return session


class QuickBaseAPI:
    """
    Holds auth/session and issues raw HTTP requests.
    Does not parse responses; returns the raw Response.
    """

    def __init__(
        self,
        auth: Auth,
        base_url: str = BASE_URL,
        *,
        request_config: RequestConfig | None = None,
        session: requests.Session | None = None,
        schema_cache: SchemaCache | None = None,
    ):
        self.auth = auth
        self.base_url = base_url.rstrip("/")
        self.request_config = request_config or RequestConfig()
        self.session = session or requests.Session()
        self.session.headers.update(auth.headers)
        self._schema_cache: SchemaCache | None = None
        if schema_cache is not None:
            self.schema_cache = schema_cache

    @property
    def schema_cache(self) -> SchemaCache | None:
        return self._schema_cache

    @schema_cache.setter
    def schema_cache(self, schema_cache: SchemaCache) -> None:
        from quickbase_data_client.schema_cache import SchemaCache

        if not isinstance(schema_cache, SchemaCache):
            raise QuickbaseConfigurationError(
                format_error_message(
                    "schema_cache must be a SchemaCache instance.",
                    operation="QuickBaseAPI.schema_cache",
                    schema_cache_type=type(schema_cache).__name__,
                )
            )
        schema_cache.api_client = self
        self._schema_cache = schema_cache

    def app(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> App:
        from quickbase_data_client.app import App

        if identifier is not None:
            return App(self, identifier)
        if id is not None and name is not None:
            return App(self, id=id, name=name)
        if id is not None:
            return App(self, id=id)
        if name is not None:
            return App(self, name=name)
        raise QuickbaseValidationError(
            format_error_message(
                "QuickBaseAPI.app requires an identifier, id, or name.",
                operation="QuickBaseAPI.app",
            )
        )

    def table(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        app: App | None = None,
    ) -> Table:
        from quickbase_data_client.table import Table

        if identifier is not None:
            return Table(self, identifier, app=app)
        if id is not None and name is not None:
            return Table(self, id=id, name=name, app=app)
        if id is not None:
            return Table(self, id=id, app=app)
        if name is not None:
            return Table(self, name=name, app=app)
        raise QuickbaseValidationError(
            format_error_message(
                "QuickBaseAPI.table requires an identifier, id, or name.",
                operation="QuickBaseAPI.table",
            )
        )

    @staticmethod
    def _sanitize_headers(headers: Mapping[str, Any]) -> Dict[str, str]:
        sanitized: Dict[str, str] = {}
        for key, value in headers.items():
            normalized_key = str(key)
            if normalized_key.lower() in SENSITIVE_HEADER_NAMES:
                sanitized[normalized_key] = "<redacted>"
            else:
                sanitized[normalized_key] = str(value)
        return sanitized

    @staticmethod
    def _summarize_payload(payload: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if payload is None:
            return None

        summary: Dict[str, Any] = {
            "type": type(payload).__name__,
            "keys": sorted(str(key) for key in payload.keys()),
        }

        data = payload.get("data")
        if isinstance(data, list):
            summary["record_count"] = len(data)

        select = payload.get("select")
        if isinstance(select, list):
            summary["select_count"] = len(select)

        summary["has_where"] = "where" in payload
        summary["has_fields_to_return"] = "fieldsToReturn" in payload
        return summary

    @staticmethod
    def _response_body_preview(response: requests.Response) -> str | None:
        body = getattr(response, "text", None)
        if body is None:
            return None

        body_text = str(body)
        if len(body_text) <= MAX_ERROR_BODY_CHARS:
            return body_text
        return f"{body_text[:MAX_ERROR_BODY_CHARS]}..."

    @staticmethod
    def _parse_retry_after(value: str | None) -> float | None:
        if not value:
            return None

        try:
            return max(float(value), 0.0)
        except ValueError:
            pass

        try:
            retry_after_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None

        if retry_after_at.tzinfo is None:
            retry_after_at = retry_after_at.replace(tzinfo=timezone.utc)

        return max((retry_after_at - datetime.now(timezone.utc)).total_seconds(), 0.0)

    def _emit_log_hook(
        self,
        hook: RequestLogHook | None,
        event: dict[str, Any],
        hook_name: str,
    ) -> None:
        if hook is None:
            return

        try:
            hook(event)
        except Exception:
            logger.warning(
                "%s raised while logging QuickBaseAPI activity.",
                hook_name,
                exc_info=True,
            )

    def _log_request(
        self,
        *,
        method: str,
        endpoint: str,
        url: str,
        payload: Dict[str, Any] | None,
        attempt: int,
    ) -> None:
        event = {
            "event": "request",
            "method": method,
            "endpoint": endpoint,
            "url": url,
            "attempt": attempt,
            "timeout": self.request_config.timeout,
            "headers": self._sanitize_headers(self.session.headers),
            "payload_summary": self._summarize_payload(payload),
        }
        logger.debug("QuickBaseAPI.request: %s", event)
        self._emit_log_hook(
            self.request_config.request_log_hook,
            event,
            "request_log_hook",
        )

    def _log_response(
        self,
        *,
        response: requests.Response,
        method: str,
        endpoint: str,
        url: str,
        attempt: int,
        will_retry: bool,
        retry_delay: float | None = None,
    ) -> None:
        retry_after_header = None
        headers = getattr(response, "headers", {}) or {}
        if isinstance(headers, Mapping):
            retry_after_header = headers.get("Retry-After")

        event = {
            "event": "response",
            "method": method,
            "endpoint": endpoint,
            "url": url,
            "attempt": attempt,
            "status_code": response.status_code,
            "reason": getattr(response, "reason", None),
            "headers": (
                self._sanitize_headers(headers) if isinstance(headers, Mapping) else {}
            ),
            "will_retry": will_retry,
        }

        if retry_after_header is not None:
            event["retry_after"] = retry_after_header
        if retry_delay is not None:
            event["retry_delay"] = retry_delay

        logger.debug("QuickBaseAPI.response: %s", event)
        self._emit_log_hook(
            self.request_config.response_log_hook,
            event,
            "response_log_hook",
        )

    def _compute_retry_delay(
        self,
        *,
        attempt: int,
        response: requests.Response | None = None,
    ) -> float:
        if response is not None and self.request_config.respect_retry_after:
            headers = getattr(response, "headers", {}) or {}
            if isinstance(headers, Mapping):
                retry_after = self._parse_retry_after(headers.get("Retry-After"))
                if retry_after is not None:
                    return retry_after

        delay = self.request_config.backoff_factor * (2 ** (attempt - 1))
        if self.request_config.jitter:
            delay += random.random() * self.request_config.jitter
        return delay

    def _should_retry_response(self, response: requests.Response) -> bool:
        return response.status_code in self.request_config.retryable_status_codes

    def _raise_http_error(
        self,
        *,
        response: requests.Response,
        endpoint: str,
        method: str,
        attempts: int,
    ) -> None:
        status_code = response.status_code
        response_body = self._response_body_preview(response)
        headers = getattr(response, "headers", {}) or {}
        retry_after = headers.get("Retry-After") if isinstance(headers, Mapping) else None

        error_cls: type[QuickbaseError] = QuickbaseHTTPError
        if status_code in {401, 403}:
            error_cls = QuickbaseAuthError
        elif status_code == 404:
            error_cls = QuickbaseNotFoundError
        elif status_code == 429:
            error_cls = QuickbaseRateLimitError

        http_error = requests.HTTPError(
            f"Quickbase returned HTTP {status_code} for {method} {endpoint}",
            response=response,
        )
        raise error_cls(
            format_error_message(
                "Quickbase request failed.",
                operation="QuickBaseAPI.request",
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                attempts=attempts,
                retry_count=self.request_config.retry_count,
                retry_after=retry_after,
                response_body=response_body,
                cause=http_error,
            )
        ) from http_error

    def request(
        self,
        *,
        method: Literal["GET", "POST", "DELETE", "PUT"],
        endpoint: str,
        payload: Dict[str, Any] | None = None,
    ) -> requests.Response:
        """
        Sends a raw HTTP request and returns the requests.Response.
        Parsing into QuickBaseResponse is done at the Table layer.
        """
        url = f"{self.base_url}{endpoint}"
        for attempt in range(1, self.request_config.retry_count + 2):
            self._log_request(
                method=method,
                endpoint=endpoint,
                url=url,
                payload=payload,
                attempt=attempt,
            )

            try:
                response = self.session.request(
                    method,
                    url,
                    json=payload if payload is not None else None,
                    timeout=self.request_config.timeout,
                )
            except requests.Timeout as exc:
                if attempt <= self.request_config.retry_count:
                    retry_delay = self._compute_retry_delay(attempt=attempt)
                    logger.debug(
                        (
                            "QuickBaseAPI.request timeout retry: "
                            "method=%s endpoint=%s attempt=%s delay=%s"
                        ),
                        method,
                        endpoint,
                        attempt,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                    continue

                raise QuickbaseTransportError(
                    format_error_message(
                        "Quickbase request timed out.",
                        operation="QuickBaseAPI.request",
                        endpoint=endpoint,
                        method=method,
                        timeout=self.request_config.timeout,
                        attempts=attempt,
                        retry_count=self.request_config.retry_count,
                        cause=exc,
                    )
                ) from exc
            except requests.ConnectionError as exc:
                if attempt <= self.request_config.retry_count:
                    retry_delay = self._compute_retry_delay(attempt=attempt)
                    logger.debug(
                        (
                            "QuickBaseAPI.request connection retry: "
                            "method=%s endpoint=%s attempt=%s delay=%s"
                        ),
                        method,
                        endpoint,
                        attempt,
                        retry_delay,
                    )
                    time.sleep(retry_delay)
                    continue

                raise QuickbaseTransportError(
                    format_error_message(
                        "Quickbase connection error.",
                        operation="QuickBaseAPI.request",
                        endpoint=endpoint,
                        method=method,
                        attempts=attempt,
                        retry_count=self.request_config.retry_count,
                        cause=exc,
                    )
                ) from exc
            except requests.RequestException as exc:
                raise QuickbaseTransportError(
                    format_error_message(
                        "Quickbase transport error.",
                        operation="QuickBaseAPI.request",
                        endpoint=endpoint,
                        method=method,
                        attempts=attempt,
                        retry_count=self.request_config.retry_count,
                        cause=exc,
                    )
                ) from exc

            will_retry = (
                attempt <= self.request_config.retry_count
                and self._should_retry_response(response)
            )
            response_retry_delay: float | None = (
                self._compute_retry_delay(attempt=attempt, response=response)
                if will_retry
                else None
            )
            self._log_response(
                response=response,
                method=method,
                endpoint=endpoint,
                url=url,
                attempt=attempt,
                will_retry=will_retry,
                retry_delay=response_retry_delay,
            )

            if response.status_code < 400:
                return response

            if will_retry:
                time.sleep(response_retry_delay or 0.0)
                continue

            self._raise_http_error(
                response=response,
                endpoint=endpoint,
                method=method,
                attempts=attempt,
            )

        raise QuickbaseTransportError(
            format_error_message(
                "Quickbase request exhausted retries without a terminal response.",
                operation="QuickBaseAPI.request",
                endpoint=endpoint,
                method=method,
                retry_count=self.request_config.retry_count,
            )
        )


class QuickBaseClient(QuickBaseAPI):
    """Preferred public client name for Quickbase data operations."""
