from __future__ import annotations

import base64
from typing import cast

import pytest

from quickbase_sdk.exceptions import QuickbasePayloadError
from quickbase_sdk.identifier import Identifier
from quickbase_sdk.parsers.response_factory import ResponseFactory
from quickbase_sdk.parsers.responses import DownloadFileResponse


class JsonDownloadResponse:
    def __init__(
        self,
        *,
        payload=None,
        error: Exception | None = None,
        status_code: int = 200,
        reason: str = "OK",
    ) -> None:
        self._payload = payload
        self._error = error
        self.status_code = status_code
        self.reason = reason
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        if self._error is not None:
            raise self._error
        return self._payload


def _table_identifier() -> Identifier:
    return Identifier("TABLE", id="bq12345")


def test_download_file_response_factory_reads_json_transport_payload(tmp_path) -> None:
    payload = {
        "file": {
            "fileName": "server-name.txt",
            "data": base64.b64encode(b"hello from json").decode("ascii"),
        }
    }

    response = cast(
        DownloadFileResponse,
        ResponseFactory.download_file(
            JsonDownloadResponse(payload=payload),
            "local-name.txt",
            tmp_path,
        ),
    )

    assert response.encoding == "base64"
    assert response.path.read_bytes() == b"hello from json"
    assert response.raw["sourceFileName"] == "server-name.txt"


def test_download_file_response_factory_rejects_invalid_json_transport_payload(tmp_path) -> None:
    with pytest.raises(QuickbasePayloadError, match="declared JSON content"):
        ResponseFactory.download_file(
            JsonDownloadResponse(error=ValueError("bad json")),
            "local-name.txt",
            tmp_path,
        )


def test_download_file_response_factory_rejects_missing_content(tmp_path) -> None:
    with pytest.raises(QuickbasePayloadError, match="did not include binary content or base64"):
        ResponseFactory.download_file(
            {"metadata": {"statusCode": 200, "message": "OK"}},
            "local-name.txt",
            tmp_path,
        )


def test_upsert_response_dataframe_requires_rows() -> None:
    response = ResponseFactory.upsert_records(
        {
            "metadata": {"statusCode": 200, "message": "OK"},
            "fields": [{"id": 6, "label": "Status", "type": "text"}],
            "data": [],
        },
        _table_identifier(),
    )

    with pytest.raises(QuickbasePayloadError, match="did not include any row data"):
        response.dataframe()


def test_query_response_dataframe_supports_name_headers() -> None:
    response = ResponseFactory.query_records(
        {
            "metadata": {"statusCode": 200, "message": "OK"},
            "fields": [
                {"id": 3, "label": "Record ID#", "type": "numeric"},
                {"id": 6, "label": "Status", "type": "text"},
            ],
            "data": [
                {
                    "3": {"value": 1},
                    "6": {"value": "Open"},
                }
            ],
        },
        _table_identifier(),
    )

    dataframe = response.dataframe("NAME")
    assert dataframe is not None

    assert list(dataframe.columns) == ["Record ID#", "Status"]
    assert dataframe.iloc[0].to_dict() == {
        "Record ID#": 1,
        "Status": "Open",
    }
