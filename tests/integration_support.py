from __future__ import annotations

import os
from typing import TypedDict

import pytest


class IntegrationEnv(TypedDict):
    realm: str
    user_token: str
    app_id: str | None
    table_id: str | None


_FALSEY_VALUES = {"", "0", "false", "no", "off"}


def _is_enabled(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value not in _FALSEY_VALUES


def _first_env(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def require_integration_env(*, require_table_id: bool = False) -> IntegrationEnv:
    if not _is_enabled("QUICKBASE_RUN_INTEGRATION_TESTS"):
        pytest.skip(
            "Set QUICKBASE_RUN_INTEGRATION_TESTS=1 to enable live Quickbase integration tests.",
            allow_module_level=True,
        )

    realm = _first_env("QUICKBASE_REALM")
    user_token = _first_env("QUICKBASE_USER_TOKEN")
    app_id = _first_env("QUICKBASE_TEST_APP_ID", "QUICKBASE_APP_ID")
    table_id = _first_env("QUICKBASE_TEST_TABLE_ID")

    missing = []
    if not realm:
        missing.append("QUICKBASE_REALM")
    if not user_token:
        missing.append("QUICKBASE_USER_TOKEN")
    if require_table_id and not table_id:
        missing.append("QUICKBASE_TEST_TABLE_ID")

    if missing:
        pytest.skip(
            "Missing integration-test environment variables: " + ", ".join(missing),
            allow_module_level=True,
        )

    assert realm is not None
    assert user_token is not None

    return {
        "realm": realm,
        "user_token": user_token,
        "app_id": app_id,
        "table_id": table_id,
    }


def parse_select_env(name: str) -> list[int] | None:
    raw_value = os.getenv(name)
    if not raw_value:
        return None

    values = [segment.strip() for segment in raw_value.split(",") if segment.strip()]
    if not values:
        return None
    return [int(value) for value in values]
