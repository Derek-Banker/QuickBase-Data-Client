from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any, cast
from unittest.mock import Mock

import pytest
import requests

import quickbase_data_client.quickbase_api as quickbase_api_module
from quickbase_data_client.exceptions import QuickbaseConfigurationError, QuickbaseTransportError
from quickbase_data_client.parsers.requests import OptionsProperty, build_query_records_request
from quickbase_data_client.quickbase_api import Auth, QuickBaseAPI, RequestConfig


def _response(
    status_code: int,
    *,
    text: str = "",
    headers: dict[str, str] | None = None,
    reason: str | None = None,
) -> Mock:
    response = Mock()
    response.status_code = status_code
    response.text = text
    response.headers = headers or {}
    response.reason = reason
    return response


def test_request_retries_retryable_http_status_and_returns_response(monkeypatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(quickbase_api_module.time, "sleep", delays.append)

    api = QuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=1, backoff_factor=0.5, jitter=0.0),
    )
    request_mock = Mock(
        side_effect=[
            _response(503, text="service unavailable"),
            _response(200, text='{"data": []}'),
        ]
    )
    monkeypatch.setattr(
        api.session,
        "request",
        request_mock,
    )

    response = api.request(method="GET", endpoint="/records")

    assert response.status_code == 200
    assert request_mock.call_count == 2
    assert delays == [0.5]


def test_request_uses_retry_after_for_rate_limit_retries(monkeypatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(quickbase_api_module.time, "sleep", delays.append)

    api = QuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=1, backoff_factor=0.5, jitter=0.0),
    )
    request_mock = Mock(
        side_effect=[
            _response(429, text="rate limited", headers={"Retry-After": "7"}),
            _response(200, text='{"data": []}'),
        ]
    )
    monkeypatch.setattr(
        api.session,
        "request",
        request_mock,
    )

    response = api.request(method="GET", endpoint="/records")

    assert response.status_code == 200
    assert request_mock.call_count == 2
    assert delays == [7.0]


def test_request_retries_connection_errors_and_then_succeeds(monkeypatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(quickbase_api_module.time, "sleep", delays.append)

    api = QuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=1, backoff_factor=0.25, jitter=0.0),
    )
    request_mock = Mock(
        side_effect=[
            requests.ConnectionError("socket closed"),
            _response(200, text='{"data": []}'),
        ]
    )
    monkeypatch.setattr(
        api.session,
        "request",
        request_mock,
    )

    response = api.request(method="GET", endpoint="/records")

    assert response.status_code == 200
    assert request_mock.call_count == 2
    assert delays == [0.25]


def test_request_raises_transport_error_after_timeout_retries(monkeypatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr(quickbase_api_module.time, "sleep", delays.append)

    api = QuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=1, backoff_factor=0.25, jitter=0.0),
    )
    request_mock = Mock(side_effect=requests.Timeout("read timed out"))
    monkeypatch.setattr(
        api.session,
        "request",
        request_mock,
    )

    with pytest.raises(QuickbaseTransportError, match="timed out"):
        api.request(method="GET", endpoint="/records")

    assert request_mock.call_count == 2
    assert delays == [0.25]


def test_request_logging_hooks_redact_authorization_and_payload_values(monkeypatch) -> None:
    request_events: list[dict[str, Any]] = []
    response_events: list[dict[str, Any]] = []

    api = QuickBaseAPI(
        Auth("example.quickbase.com", "super-secret-token"),
        request_config=RequestConfig(
            retry_count=0,
            jitter=0.0,
            request_log_hook=request_events.append,
            response_log_hook=response_events.append,
        ),
    )
    monkeypatch.setattr(
        api.session,
        "request",
        Mock(return_value=_response(200, headers={"X-RateLimit-Remaining": "9"})),
    )

    api.request(
        method="POST",
        endpoint="/records",
        payload={
            "to": "bq12345",
            "user_token": "should-not-appear",
            "data": [{"3": {"value": "should-not-appear"}}],
        },
    )

    assert len(request_events) == 1
    assert request_events[0]["headers"]["Authorization"] == "<redacted>"
    assert request_events[0]["payload_summary"]["record_count"] == 1
    assert "super-secret-token" not in repr(request_events[0])
    assert "should-not-appear" not in repr(request_events[0])

    assert len(response_events) == 1
    assert response_events[0]["headers"]["X-RateLimit-Remaining"] == "9"


def test_parse_retry_after_accepts_http_dates() -> None:
    retry_after = format_datetime(
        datetime.now(timezone.utc) + timedelta(seconds=30),
        usegmt=True,
    )

    delay = QuickBaseAPI._parse_retry_after(retry_after)

    assert delay is not None
    assert 0.0 <= delay <= 30.0


def test_request_config_rejects_non_callable_request_log_hook() -> None:
    with pytest.raises(QuickbaseConfigurationError, match="request_log_hook"):
        RequestConfig(request_log_hook=cast(Any, "not-callable"))


def test_build_query_records_request_omits_none_values() -> None:
    endpoint, payload = build_query_records_request(
        "bq12345",
        where="{3.GT.0}",
        select=[3, 6],
        options=OptionsProperty(skip=0, top=None),
    )

    assert endpoint == "/records/query"
    assert payload == {
        "from": "bq12345",
        "where": "{3.GT.0}",
        "select": [3, 6],
        "options": {
            "skip": 0,
            "compareWithAppLocalTime": False,
        },
    }
