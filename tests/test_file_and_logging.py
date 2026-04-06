import base64
import logging
from unittest.mock import Mock

import pytest

import quickbase_sdk.table as table_module
import quickbase_sdk.tools.quickbase_log_handler as log_handler_module
from quickbase_sdk import QuickBaseClient
from quickbase_sdk.exceptions import (
    QuickbaseConfigurationError,
    QuickbasePayloadError,
    QuickbaseValidationError,
)
from quickbase_sdk.file_payload import FilePayload
from quickbase_sdk.parsers.requests import QuickBaseRequest
from quickbase_sdk.quickbase_api import Auth, RequestConfig
from quickbase_sdk.tools.quickbase_log_handler import QuickBaseHandler


def _make_table(*, request_config: RequestConfig | None = None):
    client = QuickBaseClient(
        Auth("example.quickbase.com", "token"),
        request_config=request_config,
    )
    return client.table(id="bq12345")


def _upsert_response(rows):
    return {
        "metadata": {"statusCode": 200, "message": "OK"},
        "fields": [{"id": 10, "label": "Attachment", "type": "file"}],
        "data": rows,
    }


class _BinaryDownloadResponse:
    def __init__(self, content: bytes) -> None:
        self.status_code = 200
        self.reason = "OK"
        self.headers = {"Content-Type": "application/octet-stream"}
        self.content = content


def test_upload_files_batches_multi_file_payload_by_request_size(monkeypatch) -> None:
    calls = []

    def fake_upload(client, table_id, data, fields_to_return):
        calls.append((table_id, len(data), fields_to_return))
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upload_files", staticmethod(fake_upload))
    monkeypatch.setattr(
        table_module,
        "_payload_size_bytes",
        lambda payload: 150 + (len(payload["data"]) * 100),
    )

    response = _make_table().upload_files(
        file_field_id=10,
        multi_file_payload=[
            {"file": FilePayload(name="a.txt", data="QQ=="), "record_id": 1},
            {"file": FilePayload(name="b.txt", data="Qg=="), "record_id": 2},
            {"file": FilePayload(name="c.txt", data="Qw=="), "record_id": 3},
        ],
        max_request_size_kb=0.25,
    )

    assert calls == [
        ("bq12345", 1, None),
        ("bq12345", 1, None),
        ("bq12345", 1, None),
    ]
    assert len(response.data) == 3
    assert response.metadata["batchCount"] == 3


def test_upload_files_uses_request_config_limits_for_file_workflows(monkeypatch, tmp_path) -> None:
    file_path = tmp_path / "oversize.bin"
    file_path.write_bytes(b"x" * 1024)

    table = _make_table(
        request_config=RequestConfig(
            retry_count=0,
            jitter=0.0,
            max_file_size_kb=0.5,
            max_request_size_kb=0.25,
        )
    )

    with pytest.raises(QuickbasePayloadError, match="size limit"):
        table.upload_files(
            file_field_id=10,
            file_payload=FilePayload(drive_path=file_path),
        )

    calls = []

    def fake_upload(client, table_id, data, fields_to_return):
        calls.append(len(data))
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upload_files", staticmethod(fake_upload))
    monkeypatch.setattr(
        table_module,
        "_payload_size_bytes",
        lambda payload: 150 + (len(payload["data"]) * 100),
    )

    response = table.upload_files(
        file_field_id=10,
        multi_file_payload=[
            {"file": FilePayload(name="a.txt", data="QQ=="), "record_id": 1},
            {"file": FilePayload(name="b.txt", data="Qg=="), "record_id": 2},
        ],
    )

    assert calls == [1, 1]
    assert response.metadata["batchCount"] == 2


def test_download_file_writes_binary_response_to_disk(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        QuickBaseRequest,
        "download_file",
        staticmethod(lambda *args, **kwargs: _BinaryDownloadResponse(b"hello world")),
    )

    response = _make_table().download_file(
        field_id=10,
        record_id=1,
        version_number=0,
        output_file_name="report.bin",
        output_file_path=tmp_path,
    )

    saved_file = tmp_path / "report.bin"
    assert saved_file.read_bytes() == b"hello world"
    assert response.path == saved_file
    assert response.bytes_written == 11
    assert response.encoding == "binary"


def test_download_file_decodes_base64_payload_to_disk(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        QuickBaseRequest,
        "download_file",
        staticmethod(
            lambda *args, **kwargs: {
                "metadata": {"statusCode": 200, "message": "OK"},
                "fileName": "server-name.txt",
                "data": base64.b64encode(b"hello from base64").decode("ascii"),
            }
        ),
    )

    response = _make_table().download_file(
        field_id=10,
        record_id=1,
        version_number=0,
        output_file_name="local-name.txt",
        output_file_path=tmp_path,
    )

    saved_file = tmp_path / "local-name.txt"
    assert saved_file.read_bytes() == b"hello from base64"
    assert response.path == saved_file
    assert response.encoding == "base64"
    assert response.raw["sourceFileName"] == "server-name.txt"


def test_quickbase_handler_flush_builds_valid_upsert_payload_without_stdout(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(log_handler_module.atexit, "register", lambda func: None)
    calls = []

    def fake_upsert(client, table_id, data, fields_to_return):
        calls.append((table_id, data, fields_to_return))
        return _upsert_response(data)

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    handler = QuickBaseHandler(
        Auth("example.quickbase.com", "token"),
        "bq12345",
        {
            "date_time": "6",
            "level": "7",
            "message": "8",
        },
        batch_size=2,
    )

    handler.emit(
        logging.makeLogRecord(
            {"msg": "first", "levelno": logging.INFO, "levelname": "INFO"}
        )
    )
    handler.emit(
        logging.makeLogRecord(
            {"msg": "second", "levelno": logging.WARNING, "levelname": "WARNING"}
        )
    )

    assert len(calls) == 1
    table_id, data, fields_to_return = calls[0]
    assert table_id == "bq12345"
    assert fields_to_return == []
    assert len(data) == 2
    assert set(data[0]) == {"6", "7", "8"}
    assert data[0]["7"]["value"] == "INFO"
    assert data[0]["8"]["value"] == "first"
    assert len(data[0]["6"]["value"]) == 19
    assert data[1]["7"]["value"] == "WARNING"
    assert data[1]["8"]["value"] == "second"
    assert capsys.readouterr().out == ""

    handler.close()


def test_quickbase_handler_uses_handle_error_on_flush_failure(monkeypatch) -> None:
    monkeypatch.setattr(log_handler_module.atexit, "register", lambda func: None)

    def fake_upsert(client, table_id, data, fields_to_return):
        raise RuntimeError("boom")

    monkeypatch.setattr(QuickBaseRequest, "upsert_records", staticmethod(fake_upsert))

    handler = QuickBaseHandler(
        Auth("example.quickbase.com", "token"),
        "bq12345",
        {"date_time": "6", "level": "7", "message": "8"},
        batch_size=10,
    )
    mock_handle_error = Mock()
    monkeypatch.setattr(handler, "handleError", mock_handle_error)
    record = logging.makeLogRecord({"msg": "hello", "levelno": logging.INFO, "levelname": "INFO"})
    handler.emit(record)

    handler.flush()

    mock_handle_error.assert_called_once_with(record)


def test_quickbase_handler_requires_core_field_mappings(monkeypatch) -> None:
    monkeypatch.setattr(log_handler_module.atexit, "register", lambda func: None)

    with pytest.raises(QuickbaseValidationError, match="missing_fids"):
        QuickBaseHandler(
            Auth("example.quickbase.com", "token"),
            "bq12345",
            {"date_time": "6"},
        )


def test_request_config_validates_file_workflow_size_limits() -> None:
    config = RequestConfig(max_request_size_kb=1024, max_file_size_kb=256)

    assert config.max_request_size_kb == 1024.0
    assert config.max_file_size_kb == 256.0

    with pytest.raises(QuickbaseConfigurationError, match="max_file_size_kb"):
        RequestConfig(max_file_size_kb=0)
