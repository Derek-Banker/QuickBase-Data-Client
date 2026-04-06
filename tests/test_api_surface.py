import importlib
import sys

import pytest

import quickbase_sdk
from quickbase_sdk import AppRef, QuickBaseAPI, QuickBaseClient, SchemaCache, TableRef
from quickbase_sdk.exceptions import QuickbaseSchemaError
from quickbase_sdk.identifier import Identifier
from quickbase_sdk.parsers.requests import QuickBaseRequest
from quickbase_sdk.quickbase_api import Auth


def test_package_root_exports_phase4_primary_names() -> None:
    assert issubclass(QuickBaseClient, QuickBaseAPI)
    assert AppRef is quickbase_sdk.App
    assert TableRef is quickbase_sdk.Table
    assert SchemaCache is quickbase_sdk.SchemaCache


def test_client_table_supports_id_only_without_schema(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "quickbase_sdk.schema_manager", raising=False)

    client = QuickBaseClient(Auth("example.quickbase.com", "token"))
    table = client.table(id="bq12345")

    assert isinstance(table, TableRef)
    assert table.id == "bq12345"
    assert table.app is None
    assert table.identifier.parent is None
    assert "quickbase_sdk.schema_manager" not in sys.modules


def test_app_table_lowercase_injects_parent_and_legacy_method_warns() -> None:
    client = QuickBaseClient(Auth("example.quickbase.com", "token"))
    app = client.app(id="bp12345")

    table = app.table(id="bq12345")

    assert table.app is app
    assert table.identifier.parent is app.identifier

    with pytest.deprecated_call(match=r"App\.Table\(\) is deprecated"):
        legacy_table = app.Table(id="bq99999")

    assert legacy_table.app is app
    assert legacy_table.identifier.parent is app.identifier


def test_run_report_accepts_raw_report_id_without_schema(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "quickbase_sdk.schema_manager", raising=False)

    captured: dict[str, str] = {}

    def fake_run_report(client, table_id, report_id, params):
        captured["table_id"] = table_id
        captured["report_id"] = report_id
        return {"metadata": {"statusCode": 200, "message": "OK"}, "fields": [], "data": []}

    monkeypatch.setattr(QuickBaseRequest, "run_report", staticmethod(fake_run_report))

    client = QuickBaseClient(Auth("example.quickbase.com", "token"))
    table = client.table(id="bq12345")
    response = table.run_report(13)

    assert captured == {"table_id": "bq12345", "report_id": "13"}
    assert response.status_code == 200
    assert "quickbase_sdk.schema_manager" not in sys.modules


def test_identifier_resolves_parent_from_attached_schema_cache(tmp_path, monkeypatch) -> None:
    calls: dict[str, tuple[str, str, str | None] | tuple[str, str]] = {}
    cache = SchemaCache(path=tmp_path / "schema.sqlite3")

    def fake_get_parent(*, level: str, id: str, refresh_policy=None) -> str:
        calls["parent"] = (level, id)
        return "bq12345"

    def fake_get_name(
        *,
        level: str,
        id: str,
        parent_id: str | None = None,
        refresh_policy=None,
    ) -> str:
        calls["name"] = (level, id, parent_id)
        return "Status"

    def fake_get_type(
        *,
        level: str,
        id: str,
        parent_id: str | None = None,
        refresh_policy=None,
    ) -> str:
        calls["type"] = (level, id, parent_id)
        return "text"

    monkeypatch.setattr(cache, "get_parent", fake_get_parent)
    monkeypatch.setattr(cache, "get_name", fake_get_name)
    monkeypatch.setattr(cache, "get_type", fake_get_type)

    field_identifier = Identifier("FIELD", id="7", schema_cache=cache)

    assert field_identifier.parent is not None
    assert field_identifier.parent.id == "bq12345"
    assert field_identifier.parent.schema_cache is cache
    assert field_identifier.name == "Status"
    assert field_identifier.type == "text"
    assert calls["parent"] == ("FIELD", "7")
    assert calls["name"] == ("FIELD", "7", "bq12345")
    assert calls["type"] == ("FIELD", "7", "bq12345")
    cache.close()


def test_identifier_name_lookup_requires_explicit_schema_cache(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "quickbase_sdk.schema_manager", raising=False)

    field_identifier = Identifier("FIELD", id="7")

    with pytest.raises(QuickbaseSchemaError, match="cached schema metadata"):
        _ = field_identifier.name

    assert "quickbase_sdk.schema_manager" not in sys.modules


def test_importing_schema_manager_does_not_auto_load_schema(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "quickbase_sdk.schema_manager", raising=False)

    module = importlib.import_module("quickbase_sdk.schema_manager")

    assert module.database_loaded is False
    assert module.loaded_database is None


def test_package_root_compat_export_warns(monkeypatch) -> None:
    quickbase_sdk.__dict__.pop("QuickBaseRequest", None)

    with pytest.deprecated_call(match="QuickBaseRequest is an internal helper"):
        compat_export = quickbase_sdk.QuickBaseRequest

    assert compat_export is QuickBaseRequest
