import pytest

import quickbase_sdk.schema_cache as schema_cache_module
from quickbase_sdk import QuickBaseClient, SchemaCache
from quickbase_sdk.exceptions import QuickbaseNotFoundError
from quickbase_sdk.quickbase_api import Auth


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _make_client_with_cache(
    tmp_path,
    monkeypatch,
    responses,
    *,
    default_refresh_policy="missing",
    stale_after_seconds=3600.0,
):
    client = QuickBaseClient(Auth("example.quickbase.com", "token"))
    calls = []

    def fake_request(*, method, endpoint, payload=None):
        calls.append((method, endpoint, payload))
        return DummyResponse(responses[endpoint])

    monkeypatch.setattr(client, "request", fake_request)
    cache = SchemaCache(
        path=tmp_path / "schema.sqlite3",
        default_refresh_policy=default_refresh_policy,
        stale_after_seconds=stale_after_seconds,
    )
    client.schema_cache = cache
    return client, cache, calls


def test_schema_cache_missing_policy_fetches_tables_once_for_name_resolution(
    tmp_path,
    monkeypatch,
) -> None:
    client, cache, calls = _make_client_with_cache(
        tmp_path,
        monkeypatch,
        {
            "/tables?appId=bp123": {
                "data": [
                    {"id": "bq123", "name": "Orders"},
                ]
            }
        },
    )

    try:
        app = client.app(id="bp123")

        assert app.table(name="Orders").id == "bq123"
        assert app.table(name="Orders").id == "bq123"
        assert calls == [("GET", "/tables?appId=bp123", None)]
    finally:
        cache.close()


def test_schema_cache_never_policy_uses_local_rows_only(tmp_path, monkeypatch) -> None:
    client, cache, calls = _make_client_with_cache(
        tmp_path,
        monkeypatch,
        {
            "/tables?appId=bp123": {
                "data": [
                    {"id": "bq123", "name": "Orders"},
                ]
            }
        },
        default_refresh_policy="never",
    )

    try:
        app = client.app(id="bp123")

        with pytest.raises(QuickbaseNotFoundError, match="requested object by name"):
            _ = app.table(name="Orders").id

        assert calls == []

        cache.refresh_tables("bp123")
        assert app.table(name="Orders").id == "bq123"
        assert calls == [("GET", "/tables?appId=bp123", None)]
    finally:
        cache.close()


def test_schema_cache_always_policy_refetches_segments(tmp_path, monkeypatch) -> None:
    client, cache, calls = _make_client_with_cache(
        tmp_path,
        monkeypatch,
        {
            "/tables?appId=bp123": {
                "data": [
                    {"id": "bq123", "name": "Orders"},
                ]
            }
        },
        default_refresh_policy="always",
    )

    try:
        app = client.app(id="bp123")

        assert app.table(name="Orders").id == "bq123"
        assert app.table(name="Orders").id == "bq123"
        assert calls == [
            ("GET", "/tables?appId=bp123", None),
            ("GET", "/tables?appId=bp123", None),
        ]
    finally:
        cache.close()


def test_schema_cache_stale_policy_refetches_expired_segments(tmp_path, monkeypatch) -> None:
    client, cache, calls = _make_client_with_cache(
        tmp_path,
        monkeypatch,
        {
            "/tables?appId=bp123": {
                "data": [
                    {"id": "bq123", "name": "Orders"},
                ]
            }
        },
        default_refresh_policy="stale",
        stale_after_seconds=10.0,
    )

    time_points = iter([100.0, 120.0, 120.0])
    monkeypatch.setattr(schema_cache_module.time, "time", lambda: next(time_points))

    try:
        app = client.app(id="bp123")

        assert app.table(name="Orders").id == "bq123"
        assert app.table(name="Orders").id == "bq123"
        assert calls == [
            ("GET", "/tables?appId=bp123", None),
            ("GET", "/tables?appId=bp123", None),
        ]
    finally:
        cache.close()


def test_schema_cache_fetches_app_and_field_segments(tmp_path, monkeypatch) -> None:
    client, cache, calls = _make_client_with_cache(
        tmp_path,
        monkeypatch,
        {
            "/apps/bp123": {"id": "bp123", "name": "Operations"},
            "/fields?tableId=bq123": {
                "data": [
                    {"id": 6, "label": "Status", "fieldType": "text"},
                    {"id": 7, "label": "Amount", "fieldType": "numeric"},
                ]
            },
        },
    )

    try:
        app = client.app(id="bp123")
        table = client.table(id="bq123")
        field = table.identifier.create_child(level="FIELD", name="Status")

        assert app.name == "Operations"
        assert client.app(name="Operations").id == "bp123"
        assert field.id == "6"

        field_identities = table.identifier.field_identities()
        assert field_identities is not None
        assert [(item.id, item.name, item.type) for item in field_identities] == [
            ("6", "Status", "text"),
            ("7", "Amount", "numeric"),
        ]
        assert calls == [
            ("GET", "/apps/bp123", None),
            ("GET", "/fields?tableId=bq123", None),
        ]
    finally:
        cache.close()
