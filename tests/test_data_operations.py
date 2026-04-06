import pandas as pd
import pytest

import quickbase_data_client.table as table_module
from quickbase_data_client import Identifier, QuickBaseClient, SchemaCache
from quickbase_data_client.exceptions import (
    QuickbasePayloadError,
    QuickbaseSchemaError,
    QuickbaseValidationError,
)
from quickbase_data_client.parsers.requests import (
    OptionsProperty,
    QuickBaseRequest,
    RunReportParams,
)
from quickbase_data_client.quickbase_api import Auth


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _make_table():
    client = QuickBaseClient(Auth("example.quickbase.com", "token"))
    return client.table(id="bq12345")


def _make_table_with_schema(tmp_path, monkeypatch, fields_payload):
    cache = SchemaCache(path=tmp_path / "schema.sqlite3")
    client = QuickBaseClient(Auth("example.quickbase.com", "token"), schema_cache=cache)
    calls = []

    def fake_request(*, method, endpoint, payload=None):
        calls.append((method, endpoint, payload))
        return DummyResponse({"data": fields_payload})

    monkeypatch.setattr(client, "request", fake_request)
    return client.table(id="bq12345"), cache, calls


def _upsert_rows(*values: str):
    return [{"6": {"value": value}} for value in values]


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


def test_upsert_records_batches_by_record_count_and_merges_response(monkeypatch) -> None:
    calls = []

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append((table_id, len(data), fields_to_return))
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    response = _make_table().upsert_records(
        _upsert_rows("A", "B", "C", "D", "E"),
        max_batch_record_count=2,
    )

    assert calls == [
        ("bq12345", 2, None),
        ("bq12345", 2, None),
        ("bq12345", 1, None),
    ]
    assert response.status_code == 200
    assert len(response.data) == 5
    assert response.metadata["batchCount"] == 3
    assert response.parsed is response.raw


def test_upsert_records_batches_by_request_size_budget(monkeypatch) -> None:
    calls = []

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append(len(data))
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))
    monkeypatch.setattr(
        table_module,
        "_payload_size_bytes",
        lambda payload: 150 + (len(payload["data"]) * 100),
    )

    response = _make_table().upsert_records(
        _upsert_rows("A", "B", "C"),
        max_batch_record_count=10,
        max_request_size_kb=0.25,
    )

    assert calls == [1, 1, 1]
    assert len(response.data) == 3
    assert response.metadata["batchCount"] == 3


def test_upsert_records_raises_when_single_record_exceeds_budget(monkeypatch) -> None:
    monkeypatch.setattr(
        table_module,
        "_payload_size_bytes",
        lambda payload: 150 if not payload["data"] else 500,
    )

    with pytest.raises(QuickbasePayloadError, match="request-size budget"):
        _make_table().upsert_records(
            _upsert_rows("A"),
            max_request_size_kb=0.2,
        )


def test_upsert_records_accepts_id_only_identifier_dataframe_columns_without_schema(
    monkeypatch,
) -> None:
    calls = []

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append(data)
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    dataframe = pd.DataFrame(
        [["Open"], ["Closed"]],
        columns=[Identifier("FIELD", id="6")],
    )

    _make_table().upsert_records(dataframe)

    assert calls == [
        [
            {"6": {"value": "Open"}},
            {"6": {"value": "Closed"}},
        ]
    ]


def test_upsert_records_accepts_int_and_numeric_string_dataframe_columns_without_schema(
    monkeypatch,
) -> None:
    calls = []

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append(data)
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    dataframe = pd.DataFrame(
        [["Open", 10], ["Closed", 12]],
        columns=[6, "7"],
    )

    _make_table().upsert_records(dataframe)

    assert calls == [
        [
            {"6": {"value": "Open"}, "7": {"value": 10}},
            {"6": {"value": "Closed"}, "7": {"value": 12}},
        ]
    ]


def test_upsert_records_dataframe_name_columns_require_schema_cache() -> None:
    dataframe = pd.DataFrame([["Open"]], columns=["Status"])

    with pytest.raises(
        QuickbaseSchemaError,
        match="Field-name DataFrame columns require cached schema metadata",
    ):
        _make_table().upsert_records(dataframe)


def test_upsert_records_dataframe_name_columns_use_schema_and_sanitize_values(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []
    table, cache, schema_calls = _make_table_with_schema(
        tmp_path,
        monkeypatch,
        [
            {"id": 6, "label": "Status", "fieldType": "text"},
            {"id": 7, "label": "Amount", "fieldType": "numeric"},
            {"id": 8, "label": "Due Date", "fieldType": "date"},
        ],
    )

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append(data)
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    try:
        dataframe = pd.DataFrame(
            [["Open", "10.5", "2024-02-03"]],
            columns=["Status", "Amount", "Due Date"],
        )

        table.upsert_records(dataframe)

        assert calls == [
            [
                {
                    "6": {"value": "Open"},
                    "7": {"value": 10.5},
                    "8": {"value": "2024-02-03"},
                }
            ]
        ]
        assert schema_calls == [("GET", "/fields?tableId=bq12345", None)]
    finally:
        cache.close()


def test_upsert_records_dataframe_numeric_string_columns_stay_id_based_with_schema(
    tmp_path,
    monkeypatch,
) -> None:
    calls = []
    table, cache, schema_calls = _make_table_with_schema(
        tmp_path,
        monkeypatch,
        [
            {"id": 6, "label": "Status", "fieldType": "text"},
            {"id": 10, "label": "6", "fieldType": "text"},
        ],
    )

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append(data)
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    try:
        dataframe = pd.DataFrame([["Open"]], columns=["6"])

        table.upsert_records(dataframe)

        assert calls == [[{"6": {"value": "Open"}}]]
        assert schema_calls == []
    finally:
        cache.close()


def test_upsert_records_dataframe_rejects_duplicate_resolved_fields() -> None:
    dataframe = pd.DataFrame([["Open", "Closed"]], columns=[6, "6"])

    with pytest.raises(QuickbaseValidationError, match="same Quickbase field"):
        _make_table().upsert_records(dataframe)


def test_upsert_records_dataframe_rejects_ambiguous_field_names(monkeypatch) -> None:
    table = _make_table()
    first = table.identifier.create_child(level="FIELD", id="6", name="Status", type="text")
    second = table.identifier.create_child(level="FIELD", id="7", name="Status", type="text")
    monkeypatch.setattr(table.identifier, "field_identities", lambda: [first, second])

    with pytest.raises(QuickbaseValidationError, match="ambiguous"):
        table.upsert_records(pd.DataFrame([["Open"]], columns=["Status"]))


def test_iter_query_pages_advances_skip_and_respects_requested_top(monkeypatch) -> None:
    calls = []
    raw_pages = {
        2: _tabular_response(skip=2, count=2, total=7),
        4: _tabular_response(skip=4, count=2, total=7),
        6: _tabular_response(skip=6, count=1, total=7),
    }

    def fake_query(client, table_id, where, select, sortBy, groupBy, options):
        calls.append((table_id, where, options.skip, options.top, options.compareWithAppLocalTime))
        return raw_pages[options.skip]

    monkeypatch.setattr(QuickBaseRequest, "query_records", staticmethod(fake_query))

    pages = list(
        _make_table().iter_query_pages(
            "{3.GT.0}",
            options=OptionsProperty(skip=2, top=5, compareWithAppLocalTime=True),
            page_size=2,
        )
    )

    assert calls == [
        ("bq12345", "{3.GT.0}", 2, 2, True),
        ("bq12345", "{3.GT.0}", 4, 2, True),
        ("bq12345", "{3.GT.0}", 6, 1, True),
    ]
    assert [len(page.data) for page in pages] == [2, 2, 1]
    assert all(page.parsed is page.raw for page in pages)


def test_query_all_merges_query_pages_into_one_response(monkeypatch) -> None:
    calls = []
    raw_pages = {
        0: _tabular_response(skip=0, count=2, total=5),
        2: _tabular_response(skip=2, count=2, total=5),
        4: _tabular_response(skip=4, count=1, total=5),
    }

    def fake_query(client, table_id, where, select, sortBy, groupBy, options):
        calls.append((options.skip, options.top))
        return raw_pages[options.skip]

    monkeypatch.setattr(QuickBaseRequest, "query_records", staticmethod(fake_query))

    response = _make_table().query_all("{3.GT.0}", page_size=2)

    assert calls == [(0, 2), (2, 2), (4, 2)]
    assert response.status_code == 200
    assert len(response.data) == 5
    assert response.metadata["pageCount"] == 3
    assert response.metadata["numRecords"] == 5
    assert response.fields[0]["id"] == 3


def test_iter_report_pages_accepts_raw_report_id_and_advances_skip(monkeypatch) -> None:
    calls = []
    raw_pages = {
        1: _tabular_response(skip=1, count=2, total=5),
        3: _tabular_response(skip=3, count=2, total=5),
    }

    def fake_run_report(client, table_id, report_id, params):
        calls.append((table_id, report_id, params.skip, params.top))
        return raw_pages[params.skip]

    monkeypatch.setattr(QuickBaseRequest, "run_report", staticmethod(fake_run_report))

    pages = list(
        _make_table().iter_report_pages(
            13,
            RunReportParams(skip=1, top=4),
            page_size=2,
        )
    )

    assert calls == [
        ("bq12345", "13", 1, 2),
        ("bq12345", "13", 3, 2),
    ]
    assert [len(page.data) for page in pages] == [2, 2]
