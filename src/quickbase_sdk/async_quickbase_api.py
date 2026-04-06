from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, Literal

import requests

from quickbase_sdk.config import BASE_URL
from quickbase_sdk.exceptions import (
    QuickbaseTransportError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_sdk.quickbase_api import Auth, QuickBaseAPI, RequestConfig

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from quickbase_sdk.async_app import AsyncApp
    from quickbase_sdk.async_table import AsyncTable
    from quickbase_sdk.identifier import Identifier
    from quickbase_sdk.schema_cache import SchemaCache


class AsyncQuickBaseAPI(QuickBaseAPI):
    """Separate async client implementation for the stable Phase 9 surface."""

    def __init__(
        self,
        auth: Auth,
        base_url: str = BASE_URL,
        *,
        request_config: RequestConfig | None = None,
        session: requests.Session | None = None,
        schema_cache: SchemaCache | None = None,
    ) -> None:
        super().__init__(
            auth,
            base_url=base_url,
            request_config=request_config,
            session=session,
            schema_cache=schema_cache,
        )
        self._session_lock = threading.Lock()

    def app(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
    ) -> AsyncApp:
        from quickbase_sdk.async_app import AsyncApp

        if identifier is not None:
            return AsyncApp(self, identifier)
        if id is not None and name is not None:
            return AsyncApp(self, id=id, name=name)
        if id is not None:
            return AsyncApp(self, id=id)
        if name is not None:
            return AsyncApp(self, name=name)
        raise QuickbaseValidationError(
            format_error_message(
                "AsyncQuickBaseAPI.app requires an identifier, id, or name.",
                operation="AsyncQuickBaseAPI.app",
            )
        )

    def table(
        self,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        app: AsyncApp | None = None,
    ) -> AsyncTable:
        from quickbase_sdk.async_table import AsyncTable

        if identifier is not None:
            return AsyncTable(self, identifier, app=app)
        if id is not None and name is not None:
            return AsyncTable(self, id=id, name=name, app=app)
        if id is not None:
            return AsyncTable(self, id=id, app=app)
        if name is not None:
            return AsyncTable(self, name=name, app=app)
        raise QuickbaseValidationError(
            format_error_message(
                "AsyncQuickBaseAPI.table requires an identifier, id, or name.",
                operation="AsyncQuickBaseAPI.table",
            )
        )

    def _request_once(
        self,
        method: Literal["GET", "POST", "DELETE", "PUT"],
        url: str,
        payload: Dict[str, Any] | None,
    ) -> requests.Response:
        with self._session_lock:
            return self.session.request(
                method,
                url,
                json=payload if payload is not None else None,
                timeout=self.request_config.timeout,
            )

    async def request(
        self,
        *,
        method: Literal["GET", "POST", "DELETE", "PUT"],
        endpoint: str,
        payload: Dict[str, Any] | None = None,
    ) -> requests.Response:
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
                response = await asyncio.to_thread(self._request_once, method, url, payload)
            except requests.Timeout as exc:
                if attempt <= self.request_config.retry_count:
                    retry_delay = self._compute_retry_delay(attempt=attempt)
                    logger.debug(
                        (
                            "AsyncQuickBaseAPI.request timeout retry: "
                            "method=%s endpoint=%s attempt=%s delay=%s"
                        ),
                        method,
                        endpoint,
                        attempt,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    continue

                raise QuickbaseTransportError(
                    format_error_message(
                        "Quickbase request timed out.",
                        operation="AsyncQuickBaseAPI.request",
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
                            "AsyncQuickBaseAPI.request connection retry: "
                            "method=%s endpoint=%s attempt=%s delay=%s"
                        ),
                        method,
                        endpoint,
                        attempt,
                        retry_delay,
                    )
                    await asyncio.sleep(retry_delay)
                    continue

                raise QuickbaseTransportError(
                    format_error_message(
                        "Quickbase connection error.",
                        operation="AsyncQuickBaseAPI.request",
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
                        operation="AsyncQuickBaseAPI.request",
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
                await asyncio.sleep(response_retry_delay or 0.0)
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
                operation="AsyncQuickBaseAPI.request",
                endpoint=endpoint,
                method=method,
                retry_count=self.request_config.retry_count,
            )
        )

    def close(self) -> None:
        with self._session_lock:
            self.session.close()

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    async def __aenter__(self) -> AsyncQuickBaseAPI:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()


class AsyncQuickBaseClient(AsyncQuickBaseAPI):
    """Preferred async client name for the Phase 9 async data operations surface."""
