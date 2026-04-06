import asyncio
from unittest.mock import Mock

import pandas as pd
import pytest

import quickbase_sdk.async_quickbase_api as async_quickbase_api_module
from quickbase_sdk import (
    AsyncQuickBaseAPI,
    AsyncQuickBaseClient,
    AsyncTable,
    FilePayload,
    SchemaCache,
)
from quickbase_sdk.exceptions import QuickbaseRateLimitError
from quickbase_sdk.quickbase_api import Auth, RequestConfig


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


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


def _upsert_response(rows):
    return {
        "metadata": {"statusCode": 200, "message": "OK"},
        "fields": [{"id": 6, "label": "Status", "type": "text"}],
        "data": rows,
    }


def _tabular_response(*, skip: int, count: int, total: int):
    return {
        "metadata": {
            "statusCode": 200,
            "message": "OK",
            "skip": skip,
            "numRecords": count,
            "totalRecords": total,
        },
        "fields": [
            {"id": 3, "label": "Record ID#", "type": "numeric"},
            {"id": 6, "label": "Status", "type": "text"},
        ],
        "data": [
            {
                "3": {"value": skip + index + 1},
                "6": {"value": f"row-{skip + index + 1}"},
            }
            for index in range(count)
        ],
    }


def test_async_request_retries_retryable_http_status_and_returns_response(monkeypatch) -> None:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(async_quickbase_api_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(async_quickbase_api_module.asyncio, "to_thread", fake_to_thread)

    api = AsyncQuickBaseAPI(
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

    response = asyncio.run(api.request(method="GET", endpoint="/records"))

    assert response.status_code == 200
    assert request_mock.call_count == 2
    assert delays == [0.5]


def test_async_client_exports_id_only_table_and_legacy_async_app_method() -> None:
    client = AsyncQuickBaseClient(Auth("example.quickbase.com", "token"))
    table = client.table(id="bq12345")

    assert isinstance(table, AsyncTable)
    assert table.id == "bq12345"
    assert table.app is None
    assert table.identifier.parent is None

    app = client.app(id="bp12345")
    app_table = app.table(id="bq99999")

    assert app_table.app is app
    assert app_table.identifier.parent is app.identifier

    with pytest.deprecated_call(match=r"AsyncApp\.Table\(\) is deprecated"):
        legacy_table = app.Table(id="bq77777")

    assert legacy_table.app is app
    assert legacy_table.identifier.parent is app.identifier


def test_async_table_core_phase9_operations(monkeypatch) -> None:
    client = AsyncQuickBaseClient(Auth("example.quickbase.com", "token"))
    calls = []

    async def fake_request(*, method, endpoint, payload=None):
        calls.append((method, endpoint, payload))
        if endpoint == "/records":
            return DummyResponse(_upsert_response(payload["data"]))
        if endpoint == "/records/query":
            return DummyResponse(_tabular_response(skip=0, count=1, total=1))
        if endpoint == "/reports/13/run?tableId=bq12345":
            return DummyResponse(_tabular_response(skip=0, count=1, total=1))
        raise AssertionError(endpoint)

    table = client.table(id="bq12345")
    monkeypatch.setattr(client, "request", fake_request)

    async def run():
        upsert = await table.upsert_records(
            [{"6": {"value": "Open"}}],
            fields_to_return=[6],
        )
        query = await table.query_records("{3.GT.0}", select=[3, 6])
        report = await table.run_report(13)
        upload = await table.upload_files(
            file_field_id=10,
            file_payload=FilePayload(name="note.txt", data="YWJj"),
        )
        return upsert, query, report, upload

    upsert, query, report, upload = asyncio.run(run())

    assert upsert.status_code == 200
    assert len(upsert.data) == 1
    assert query.status_code == 200
    assert len(query.data) == 1
    assert report.status_code == 200
    assert len(report.data) == 1
    assert upload.status_code == 200
    assert len(upload.data) == 1
    assert calls == [
        (
            "POST",
            "/records",
            {"to": "bq12345", "data": [{"6": {"value": "Open"}}], "fieldsToReturn": [6]},
        ),
        (
            "POST",
            "/records/query",
            {"from": "bq12345", "where": "{3.GT.0}", "select": [3, 6]},
        ),
        (
            "POST",
            "/reports/13/run?tableId=bq12345",
            {},
        ),
        (
            "POST",
            "/records",
            {
                "to": "bq12345",
                "data": [{"10": {"value": {"fileName": "note.txt", "data": "YWJj"}}}],
            },
        ),
    ]


def test_async_request_maps_rate_limits_to_package_exception(monkeypatch) -> None:
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(async_quickbase_api_module.asyncio, "to_thread", fake_to_thread)

    api = AsyncQuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=0, jitter=0.0),
    )
    monkeypatch.setattr(
        api.session,
        "request",
        Mock(return_value=_response(429, text="rate limited")),
    )

    with pytest.raises(QuickbaseRateLimitError, match="status_code=429"):
        asyncio.run(api.request(method="GET", endpoint="/records"))


def test_async_client_context_manager_closes_session(monkeypatch) -> None:
    async def fake_to_thread(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(async_quickbase_api_module.asyncio, "to_thread", fake_to_thread)

    api = AsyncQuickBaseAPI(Auth("example.quickbase.com", "token"))
    close_mock = Mock()
    monkeypatch.setattr(api.session, "close", close_mock)

    async def run() -> None:
        async with api:
            return None

    asyncio.run(run())

    close_mock.assert_called_once_with()


def test_async_upsert_records_dataframe_name_columns_use_schema_cache(
    tmp_path,
    monkeypatch,
) -> None:
    cache = SchemaCache(path=tmp_path / "schema.sqlite3")
    client = AsyncQuickBaseClient(Auth("example.quickbase.com", "token"), schema_cache=cache)
    calls = []

    async def fake_request(*, method, endpoint, payload=None):
        calls.append((method, endpoint, payload))
        if endpoint == "/fields?tableId=bq12345":
            return DummyResponse(
                {
                    "data": [
                        {"id": 6, "label": "Status", "fieldType": "text"},
                    ]
                }
            )
        if endpoint == "/records":
            return DummyResponse(_upsert_response(payload["data"]))
        raise AssertionError(endpoint)

    monkeypatch.setattr(client, "request", fake_request)
    table = client.table(id="bq12345")

    try:
        async def run():
            return await table.upsert_records(pd.DataFrame([["Open"]], columns=["Status"]))

        response = asyncio.run(run())

        assert response.status_code == 200
        assert response.data == [{"6": {"value": "Open"}}]
        assert calls == [
            ("GET", "/fields?tableId=bq12345", None),
            ("POST", "/records", {"to": "bq12345", "data": [{"6": {"value": "Open"}}]}),
        ]
    finally:
        cache.close()
