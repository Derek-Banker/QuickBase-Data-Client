from __future__ import annotations

import os

import pytest

from quickbase_sdk import Auth, QuickBaseClient, SchemaCache
from quickbase_sdk.parsers.requests import OptionsProperty
from tests.integration_support import parse_select_env, require_integration_env

pytestmark = pytest.mark.integration

INTEGRATION_ENV = require_integration_env(require_table_id=True)


def test_live_query_and_schema_cache_smoke(tmp_path) -> None:
    app_id = INTEGRATION_ENV["app_id"]
    table_id = INTEGRATION_ENV["table_id"]
    assert table_id is not None, "QUICKBASE_TEST_TABLE_ID must be set for integration tests."

    cache = SchemaCache(path=tmp_path / "integration-schema.sqlite3")
    client = QuickBaseClient(
        Auth(INTEGRATION_ENV["realm"], INTEGRATION_ENV["user_token"]),
        schema_cache=cache,
    )

    try:
        if app_id:
            cache.refresh_app(app_id)
            cache.refresh_tables(app_id)
            assert cache.get_name("APP", app_id) == cache.get_properties("APP", app_id)["name"]

        cache.refresh_fields(table_id)

        response = client.table(id=table_id).query_records(
            os.getenv("QUICKBASE_TEST_QUERY", "{3.GT.0}"),
            select=parse_select_env("QUICKBASE_TEST_SELECT"),
            options=OptionsProperty(top=1),
        )

        assert response.status_code == 200
    finally:
        cache.close()
