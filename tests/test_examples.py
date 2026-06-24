from __future__ import annotations

import pytest
from examples import query_records, upsert_records_dry_run


def test_query_records_dry_run_does_not_create_client(monkeypatch, capsys) -> None:
    def fail_client(*args, **kwargs):
        raise AssertionError("dry run should not create a QuickBaseClient")

    monkeypatch.setattr(query_records, "QuickBaseClient", fail_client)

    result = query_records.main(["--table-id", "bq123456", "--select", "3,6,7"])

    assert result == 0
    assert "query_records dry run" in capsys.readouterr().out


def test_query_records_execute_refuses_placeholder_credentials() -> None:
    with pytest.raises(SystemExit, match="Live execution requires real"):
        query_records.main(
            [
                "--table-id",
                "bq123456",
                "--realm",
                "example.quickbase.com",
                "--user-token",
                "qb-user-token",
                "--execute",
            ]
        )


def test_upsert_records_dry_run_does_not_create_client(monkeypatch, capsys) -> None:
    def fail_client(*args, **kwargs):
        raise AssertionError("dry run should not create a QuickBaseClient")

    monkeypatch.setattr(upsert_records_dry_run, "QuickBaseClient", fail_client)

    result = upsert_records_dry_run.main(["--table-id", "bq123456"])

    assert result == 0
    assert "upsert_records dry run" in capsys.readouterr().out


def test_upsert_records_execute_requires_confirmation() -> None:
    with pytest.raises(SystemExit, match="--confirm-upsert"):
        upsert_records_dry_run.main(
            [
                "--table-id",
                "bq123456",
                "--realm",
                "real.quickbase.com",
                "--user-token",
                "real-token",
                "--execute",
            ]
        )
