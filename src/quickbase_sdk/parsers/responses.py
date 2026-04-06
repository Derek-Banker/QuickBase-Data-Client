import logging
from abc import ABC
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Tuple

import pandas as Pandas

from quickbase_sdk.exceptions import QuickbasePayloadError, format_error_message
from quickbase_sdk.file_payload import FilePayload
from quickbase_sdk.identifier import Identifier
from quickbase_sdk.tools.dataframe_encoder import DataFrameEncoder

logger = logging.getLogger(__name__)


def _extract_status(raw: Dict[str, Any]) -> Tuple[int, str]:
    """
    Grab status_code and status_text from the raw payload metadata (or top level).
    """
    meta = raw.get("metadata", {})
    status_code = meta.get("statusCode", raw.get("statusCode", -1))
    status_text = meta.get("message", raw.get("statusText", ""))
    return status_code, status_text


def _generate_field_identifiers(raw_data: Any, table_identifier: Identifier) -> List[Identifier]:
    fields = raw_data.get("fields", [])
    field_identifiers: List[Identifier] = []

    for field in fields:
        field_identifiers.append(
            table_identifier.create_child(
                level="FIELD",
                id=str(field["id"]),
                name=field["label"],
                type=field["type"],
            )
        )

    logger.debug("field_identifiers=%s", field_identifiers)
    return field_identifiers


def _generate_frame(raw_data: Any, table_identifier: Identifier) -> Pandas.DataFrame:
    field_identifiers = _generate_field_identifiers(raw_data, table_identifier)
    return DataFrameEncoder.to_dataframe(raw_data.get("data", []), field_identifiers)


def _download_metadata(
    raw: Dict[str, Any] | None,
    *,
    status_code: int = 200,
    status_text: str = "OK",
) -> Dict[str, Any]:
    metadata = raw.get("metadata", {}) if isinstance(raw, dict) else {}
    normalized = dict(metadata) if isinstance(metadata, dict) else {}
    normalized["statusCode"] = normalized.get("statusCode", status_code)
    normalized["message"] = normalized.get("message", status_text)
    return normalized


def _extract_base64_download_payload(raw: Dict[str, Any]) -> tuple[str | None, str]:
    candidates = [raw]
    for key in ("value", "file"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    for candidate in candidates:
        source_file_name = candidate.get("fileName")
        normalized_file_name = (
            source_file_name if isinstance(source_file_name, str) and source_file_name else None
        )
        for data_key in ("data", "fileData", "content"):
            encoded = candidate.get(data_key)
            if isinstance(encoded, str) and encoded:
                return normalized_file_name, encoded

    raise QuickbasePayloadError(
        format_error_message(
            "Download response did not include binary content or base64 file data.",
            operation="DownloadFileResponse",
        )
    )


def _build_download_response_from_payload(
    raw: Dict[str, Any],
    *,
    output_file_name: str,
    output_path: Path,
    status_code: int = 200,
    status_text: str = "OK",
    content_type: str | None = None,
) -> tuple[Dict[str, Any], Path]:
    source_file_name, encoded = _extract_base64_download_payload(raw)
    saved_to = FilePayload._decode_file(encoded, output_file_name, output_path)

    normalized_raw = dict(raw)
    normalized_raw["metadata"] = _download_metadata(
        raw,
        status_code=status_code,
        status_text=status_text,
    )
    normalized_raw["fileName"] = output_file_name
    normalized_raw["savedTo"] = str(saved_to)
    normalized_raw["bytesWritten"] = saved_to.stat().st_size
    normalized_raw["encoding"] = "base64"
    if source_file_name and source_file_name != output_file_name:
        normalized_raw["sourceFileName"] = source_file_name
    if content_type and "contentType" not in normalized_raw:
        normalized_raw["contentType"] = content_type
    return normalized_raw, saved_to


def build_download_response(
    raw: Any,
    *,
    output_file_name: str,
    output_path: Path,
) -> tuple[Dict[str, Any], Path]:
    if isinstance(raw, dict):
        return _build_download_response_from_payload(
            raw,
            output_file_name=output_file_name,
            output_path=output_path,
        )

    headers = getattr(raw, "headers", {}) or {}
    normalized_headers: Mapping[str, Any] = headers if isinstance(headers, Mapping) else {}
    content_type = normalized_headers.get("Content-Type")
    content_type_value = str(content_type) if content_type is not None else None
    status_code = getattr(raw, "status_code", 200)
    status_text = getattr(raw, "reason", "OK") or "OK"

    if content_type_value and "json" in content_type_value.lower():
        try:
            payload = raw.json()
        except Exception as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Download response declared JSON content but could not be parsed.",
                    operation="DownloadFileResponse",
                    content_type=content_type_value,
                    cause=exc,
                )
            ) from exc

        if not isinstance(payload, dict):
            raise QuickbasePayloadError(
                format_error_message(
                    "Download response JSON was not an object payload.",
                    operation="DownloadFileResponse",
                    payload_type=type(payload).__name__,
                )
            )

        return _build_download_response_from_payload(
            payload,
            output_file_name=output_file_name,
            output_path=output_path,
            status_code=status_code,
            status_text=status_text,
            content_type=content_type_value,
        )

    content = getattr(raw, "content", None)
    if isinstance(content, bytes):
        file_bytes = content
    elif isinstance(content, bytearray):
        file_bytes = bytes(content)
    elif isinstance(content, str):
        file_bytes = content.encode("utf-8")
    else:
        raise QuickbasePayloadError(
            format_error_message(
                "Download response did not provide binary file content.",
                operation="DownloadFileResponse",
                response_type=type(raw).__name__,
                content_type=content_type_value,
            )
        )

    saved_to = FilePayload._write_bytes(file_bytes, output_file_name, output_path)
    normalized_raw: Dict[str, Any] = {
        "metadata": {
            "statusCode": status_code,
            "message": status_text,
        },
        "fileName": output_file_name,
        "savedTo": str(saved_to),
        "bytesWritten": len(file_bytes),
        "encoding": "binary",
    }
    if content_type_value:
        normalized_raw["contentType"] = content_type_value
    content_disposition = normalized_headers.get("Content-Disposition")
    if content_disposition is not None:
        normalized_raw["contentDisposition"] = str(content_disposition)
    return normalized_raw, saved_to


class QuickBaseResponse(ABC):
    """Base interface for all QuickBase responses.

    `raw` always exposes the original decoded JSON payload that came back from
    Quickbase or a Phase 6 aggregate built from multiple compatible payloads.
    `parsed` is the canonical structured view for callers who do not need to
    distinguish between the raw transport payload and a lightly normalized one.
    """

    def __init__(self, raw: Dict[str, Any]) -> None:
        code, text = _extract_status(raw)
        self.status_code = code
        self.status_text = text
        self._raw = raw
        self._parsed: Any = raw
        self._dataframe: Pandas.DataFrame | None = None

    @property
    def raw(self) -> Dict[str, Any]:
        return self._raw

    @property
    def parsed(self) -> Any:
        return self._parsed

    @property
    def metadata(self) -> Dict[str, Any]:
        metadata = self._raw.get("metadata", {})
        return metadata if isinstance(metadata, dict) else {}

    @property
    def fields(self) -> List[Dict[str, Any]]:
        fields = self._raw.get("fields", [])
        return fields if isinstance(fields, list) else []

    @property
    def data(self) -> List[Dict[str, Any]]:
        data = self._raw.get("data", [])
        return data if isinstance(data, list) else []

    def dataframe(
        self,
        header: Literal["IDENTIFIER", "ID", "NAME"] = "IDENTIFIER",
    ) -> Pandas.DataFrame | None:
        logger.warning(
            "%s.dataframe called, but no DataFrame implementation is available.",
            self.__class__.__name__,
        )
        return None


class RunReportResponse(QuickBaseResponse):
    """Handles the query/report tabular response shape."""

    def __init__(self, raw: Dict[str, Any], table_identifier: Identifier) -> None:
        super().__init__(raw)
        self._table_identifier = table_identifier

    def dataframe(
        self,
        header: Literal["IDENTIFIER", "ID", "NAME"] = "IDENTIFIER",
    ) -> Pandas.DataFrame:
        if self._dataframe is None:
            self._dataframe = _generate_frame(self._raw, self._table_identifier)

        if header != "IDENTIFIER":
            return DataFrameEncoder.change_header(self._dataframe, header)
        return self._dataframe


class UpsertRecordsResponse(QuickBaseResponse):
    """
    Response wrapper for `/records` upsert and file-upload operations.

    Phase 6 may aggregate multiple compatible `/records` responses into a single
    logical wrapper when the Table layer batches large upserts.
    """

    def __init__(self, raw: Dict[str, Any], table_identifier: Identifier) -> None:
        super().__init__(raw)
        self._table_identifier = table_identifier

    def dataframe(
        self,
        header: Literal["IDENTIFIER", "ID", "NAME"] = "IDENTIFIER",
    ) -> Pandas.DataFrame:
        if self._dataframe is None:
            data = self.data
            if not data:
                raise QuickbasePayloadError(
                    format_error_message(
                        "Upsert response did not include any row data.",
                        operation="UpsertRecordsResponse.dataframe",
                        table_id=self._table_identifier.id,
                    )
                )
            self._dataframe = _generate_frame(self._raw, self._table_identifier)

        if header != "IDENTIFIER":
            return DataFrameEncoder.change_header(self._dataframe, header)
        return self._dataframe


class GenericResponse(QuickBaseResponse):
    """Catch-all response wrapper for operations without specialized parsing."""

    def __init__(self, raw: Dict[str, Any]) -> None:
        super().__init__(raw)


class DownloadFileResponse(QuickBaseResponse):
    """Response wrapper for file downloads that persist content to disk."""

    def __init__(self, raw: Dict[str, Any], saved_to: Path) -> None:
        super().__init__(raw)
        self._path = saved_to
        self._parsed = {
            "path": saved_to,
            "file_name": saved_to.name,
            "bytes_written": self.bytes_written,
            "encoding": self.encoding,
        }

    @property
    def path(self) -> Path:
        return self._path

    @property
    def file_name(self) -> str:
        return self._path.name

    @property
    def bytes_written(self) -> int:
        value = self._raw.get("bytesWritten", 0)
        return value if isinstance(value, int) else 0

    @property
    def encoding(self) -> str | None:
        value = self._raw.get("encoding")
        return value if isinstance(value, str) else None
