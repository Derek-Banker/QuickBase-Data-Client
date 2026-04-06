from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, TypeAlias, overload

import pandas as Pandas

from quickbase_sdk.config import DEFAULT_MAX_REQUEST_SIZE
from quickbase_sdk.exceptions import (
    QuickbasePayloadError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_sdk.file_payload import FilePayload
from quickbase_sdk.identifier import Identifier
from quickbase_sdk.parsers.requests import (
    GroupByProperty,
    OptionsProperty,
    QuickBaseRequest,
    RunReportParams,
    SortByProperty,
)
from quickbase_sdk.parsers.response_factory import ResponseFactory
from quickbase_sdk.parsers.responses import QuickBaseResponse
from quickbase_sdk.quickbase_api import QuickBaseAPI

if TYPE_CHECKING:
    from quickbase_sdk.app import App

logger = logging.getLogger(__name__)

DEFAULT_UPSERT_BATCH_RECORD_COUNT = 1000
DEFAULT_PAGE_SIZE = 1000
UploadFileEntry: TypeAlias = Dict[str, object]


def _status_from_raw(raw: Dict[str, Any]) -> tuple[int, str]:
    metadata = raw.get("metadata", {})
    if isinstance(metadata, dict):
        return (
            metadata.get("statusCode", raw.get("statusCode", 200)),
            metadata.get("message", raw.get("statusText", "OK")),
        )
    return raw.get("statusCode", 200), raw.get("statusText", "OK")


def _payload_size_bytes(payload: Dict[str, Any]) -> int:
    return len(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _build_upsert_payload(
    *,
    table_id: str,
    data: List[Dict[str, Any]],
    fields_to_return: List[int] | None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"to": table_id, "data": data}
    if fields_to_return:
        payload["fieldsToReturn"] = fields_to_return
    return payload


def _empty_tabular_raw() -> Dict[str, Any]:
    return {
        "metadata": {
            "statusCode": 200,
            "message": "OK",
            "skip": 0,
            "numRecords": 0,
            "totalRecords": 0,
            "pageCount": 0,
        },
        "fields": [],
        "data": [],
    }


def _merge_upsert_batch_responses(raw_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not raw_responses:
        return {"metadata": {"statusCode": 200, "message": "OK", "numRecords": 0}, "data": []}

    if len(raw_responses) == 1:
        return raw_responses[0]

    last_response = raw_responses[-1]
    status_code, status_text = _status_from_raw(last_response)
    merged_fields: List[Dict[str, Any]] = []
    merged_data: List[Dict[str, Any]] = []

    for raw_response in raw_responses:
        fields = raw_response.get("fields")
        if not merged_fields and isinstance(fields, list):
            merged_fields = fields

        data = raw_response.get("data")
        if isinstance(data, list):
            merged_data.extend(data)

    metadata = last_response.get("metadata", {})
    merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    merged_metadata.update(
        {
            "statusCode": status_code,
            "message": status_text,
            "numRecords": len(merged_data),
            "batchCount": len(raw_responses),
        }
    )

    merged = {
        "metadata": merged_metadata,
        "statusCode": status_code,
        "statusText": status_text,
        "data": merged_data,
        "batches": raw_responses,
    }
    if merged_fields:
        merged["fields"] = merged_fields
    return merged


def _merge_tabular_responses(raw_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not raw_responses:
        return _empty_tabular_raw()

    if len(raw_responses) == 1:
        return raw_responses[0]

    first_response = raw_responses[0]
    last_response = raw_responses[-1]
    status_code, status_text = _status_from_raw(last_response)
    merged_fields = first_response.get("fields", [])
    merged_data: List[Dict[str, Any]] = []
    first_skip = 0
    total_records = 0

    for index, raw_response in enumerate(raw_responses):
        data = raw_response.get("data")
        if isinstance(data, list):
            merged_data.extend(data)

        metadata = raw_response.get("metadata", {})
        if not isinstance(metadata, dict):
            continue

        if index == 0 and isinstance(metadata.get("skip"), int):
            first_skip = metadata["skip"]

        if isinstance(metadata.get("totalRecords"), int):
            total_records = max(total_records, metadata["totalRecords"])

    metadata = last_response.get("metadata", {})
    merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    merged_metadata.update(
        {
            "statusCode": status_code,
            "message": status_text,
            "skip": first_skip,
            "numRecords": len(merged_data),
            "totalRecords": max(total_records, first_skip + len(merged_data)),
            "pageCount": len(raw_responses),
        }
    )

    return {
        "metadata": merged_metadata,
        "statusCode": status_code,
        "statusText": status_text,
        "fields": merged_fields if isinstance(merged_fields, list) else [],
        "data": merged_data,
        "pages": raw_responses,
    }


class Table:
    """
    Helper for interacting with a specific QuickBase table.
    """

    @overload
    def __init__(self, app: App, identifier: Identifier) -> None: ...

    @overload
    def __init__(self, app: App, *, id: str) -> None: ...

    @overload
    def __init__(self, app: App, *, name: str) -> None: ...

    @overload
    def __init__(self, app: App, *, id: str, name: str) -> None: ...

    @overload
    def __init__(
        self,
        api_client: QuickBaseAPI,
        identifier: Identifier,
        *,
        app: App | None = None,
    ) -> None: ...

    @overload
    def __init__(self, api_client: QuickBaseAPI, *, id: str, app: App | None = None) -> None: ...

    @overload
    def __init__(self, api_client: QuickBaseAPI, *, name: str, app: App | None = None) -> None: ...

    @overload
    def __init__(
        self,
        api_client: QuickBaseAPI,
        *,
        id: str,
        name: str,
        app: App | None = None,
    ) -> None: ...

    def __init__(  # type: ignore[misc]
        self,
        api_client: QuickBaseAPI | App,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        app: App | None = None,
    ) -> None:
        from quickbase_sdk.app import App

        resolved_app: App | None = None
        resolved_api_client: QuickBaseAPI
        if isinstance(api_client, QuickBaseAPI):
            resolved_api_client = api_client
            resolved_app = app
        elif isinstance(api_client, App):
            resolved_api_client = api_client.api_client
            resolved_app = api_client
            if app is not None and app is not resolved_app:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Table received conflicting app references.",
                        operation="Table.__init__",
                        table_id=id,
                        table_name=name,
                    )
                )
        else:
            raise QuickbaseValidationError(
                format_error_message(
                    "Table requires a QuickBaseAPI or App instance.",
                    operation="Table.__init__",
                    api_client_type=type(api_client).__name__,
                )
            )

        self._identifier = Identifier.factory(
            identifier=identifier,
            valid_levels="TABLE",
            id=id,
            name=name,
            default_level="TABLE",
            parent=resolved_app.identifier if resolved_app is not None else None,
            schema_cache=resolved_api_client.schema_cache,
        )
        self._app = resolved_app
        self._api_client = resolved_api_client

    @property
    def name(self):
        return self._identifier.name

    @property
    def id(self):
        return self._identifier.id

    @property
    def identifier(self):
        return self._identifier

    @identifier.setter
    def identifier(self, identifier: Identifier):
        if not isinstance(identifier, Identifier):
            raise QuickbaseValidationError(
                format_error_message(
                    "Table.identifier must be an Identifier instance.",
                    operation="Table.identifier",
                    identifier_type=type(identifier).__name__,
                    table_id=self.id,
                )
            )
        self._identifier = Identifier.factory(
            identifier,
            valid_levels="TABLE",
            default_level="TABLE",
            parent=self._app.identifier if self._app is not None else None,
            schema_cache=self._api_client.schema_cache,
        )

    @property
    def api_client(self):
        return self._api_client

    @api_client.setter
    def api_client(self, api_client: QuickBaseAPI):
        if not isinstance(api_client, QuickBaseAPI):
            raise QuickbaseValidationError(
                format_error_message(
                    "Table.api_client must be a QuickBaseAPI instance.",
                    operation="Table.api_client",
                    api_client_type=type(api_client).__name__,
                    table_id=self.id,
                )
            )
        self._api_client = api_client

    @property
    def app(self) -> App | None:
        return self._app

    def _coerce_report_identifier(self, report_identifier: Identifier | str | int) -> Identifier:
        if isinstance(report_identifier, Identifier):
            return Identifier.factory(
                report_identifier,
                valid_levels="REPORT",
                default_level="REPORT",
                parent=self.identifier,
                schema_cache=self.identifier.schema_cache,
            )

        return Identifier.factory(
            None,
            valid_levels="REPORT",
            id=str(report_identifier),
            default_level="REPORT",
            parent=self.identifier,
            schema_cache=self.identifier.schema_cache,
        )

    def _require_table_id(self, operation: str) -> str:
        table_id = self.id
        if table_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Table operations require a resolved table id.",
                    operation=operation,
                    table_name=self.name,
                    object_ref=repr(self.identifier),
                )
            )
        return table_id

    def _validate_positive_int(self, value: int, *, name: str, operation: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise QuickbaseValidationError(
                (
                    f"{name} must be a positive integer. "
                    f"[operation={operation}, table_id={self.id!r}, {name}={value!r}]"
                )
            )
        return value

    def _validate_non_negative_int(
        self,
        value: int | None,
        *,
        name: str,
        operation: str,
    ) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise QuickbaseValidationError(
                (
                    f"{name} must be a non-negative integer. "
                    f"[operation={operation}, table_id={self.id!r}, {name}={value!r}]"
                )
            )
        return value

    def _validate_positive_number(
        self,
        value: int | float,
        *,
        name: str,
        operation: str,
    ) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise QuickbaseValidationError(
                (
                    f"{name} must be greater than zero. "
                    f"[operation={operation}, table_id={self.id!r}, {name}={value!r}]"
                )
            )
        return float(value)

    def _resolve_request_size_limit_kb(
        self,
        value: int | float | None,
        *,
        operation: str,
    ) -> float:
        configured = (
            self._api_client.request_config.max_request_size_kb
            if value is None
            else value
        )
        return self._validate_positive_number(
            configured,
            name="max_request_size_kb",
            operation=operation,
        )

    def _resolve_file_size_limit_kb(
        self,
        value: int | float | None,
        *,
        operation: str,
    ) -> float:
        configured = (
            self._api_client.request_config.max_file_size_kb
            if value is None
            else value
        )
        return self._validate_positive_number(
            configured,
            name="max_file_size_kb",
            operation=operation,
        )

    def _normalize_upsert_data(
        self,
        data: List[Dict[str, Any]] | Pandas.DataFrame,
    ) -> List[Dict[str, Any]]:
        if isinstance(data, Pandas.DataFrame):
            from quickbase_sdk.tools.dataframe_encoder import DataFrameEncoder

            return DataFrameEncoder.from_dataframe(
                data,
                table_identifier=self.identifier,
            )

        return data

    def _iter_upsert_batches(
        self,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None,
        *,
        max_batch_record_count: int,
        max_request_size_kb: int | float,
        operation: str = "Table.upsert_records",
    ) -> Iterator[List[Dict[str, Any]]]:
        table_id = self._require_table_id(operation)
        batch_record_count = self._validate_positive_int(
            max_batch_record_count,
            name="max_batch_record_count",
            operation=operation,
        )
        max_request_size_bytes = int(
            self._validate_positive_number(
                max_request_size_kb,
                name="max_request_size_kb",
                operation=operation,
            )
            * 1024
        )

        try:
            empty_payload_size = _payload_size_bytes(
                _build_upsert_payload(
                    table_id=table_id,
                    data=[],
                    fields_to_return=fields_to_return,
                )
            )
        except (TypeError, ValueError) as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Could not serialize upsert payload for request-size batching.",
                    operation=operation,
                    table_id=self.id,
                    cause=exc,
                )
            ) from exc

        if empty_payload_size > max_request_size_bytes:
            raise QuickbasePayloadError(
                format_error_message(
                    "fields_to_return exceeds the configured request-size budget.",
                    operation=operation,
                    table_id=self.id,
                    max_request_size_kb=max_request_size_kb,
                    empty_payload_size_bytes=empty_payload_size,
                )
            )

        if not data:
            yield []
            return

        current_batch: List[Dict[str, Any]] = []
        for record in data:
            candidate_batch = current_batch + [record]
            candidate_payload = _build_upsert_payload(
                table_id=table_id,
                data=candidate_batch,
                fields_to_return=fields_to_return,
            )

            try:
                candidate_size = _payload_size_bytes(candidate_payload)
            except (TypeError, ValueError) as exc:
                raise QuickbasePayloadError(
                    format_error_message(
                        "Could not serialize upsert payload for request-size batching.",
                        operation=operation,
                        table_id=self.id,
                        cause=exc,
                    )
                ) from exc

            if (
                len(candidate_batch) <= batch_record_count
                and candidate_size <= max_request_size_bytes
            ):
                current_batch = candidate_batch
                continue

            if current_batch:
                yield current_batch

            single_record_payload = _build_upsert_payload(
                table_id=table_id,
                data=[record],
                fields_to_return=fields_to_return,
            )
            try:
                single_record_size = _payload_size_bytes(single_record_payload)
            except (TypeError, ValueError) as exc:
                raise QuickbasePayloadError(
                    format_error_message(
                        "Could not serialize upsert payload for request-size batching.",
                        operation=operation,
                        table_id=self.id,
                        cause=exc,
                    )
                ) from exc
            if single_record_size > max_request_size_bytes:
                raise QuickbasePayloadError(
                    format_error_message(
                        "A single record exceeds the configured request-size budget.",
                        operation=operation,
                        table_id=self.id,
                        max_request_size_kb=max_request_size_kb,
                        record_size_bytes=single_record_size,
                    )
                )

            current_batch = [record]

        if current_batch:
            yield current_batch

    def upsert_records(
        self,
        data: List[Dict[str, Any]] | Pandas.DataFrame,
        fields_to_return: List[int] | None = None,
        *,
        max_batch_record_count: int = DEFAULT_UPSERT_BATCH_RECORD_COUNT,
        max_request_size_kb: int | float = DEFAULT_MAX_REQUEST_SIZE,
    ) -> QuickBaseResponse:
        table_id = self._require_table_id("Table.upsert_records")
        payload = self._normalize_upsert_data(data)
        raw_responses = [
            QuickBaseRequest.upsert_records(
                self._api_client,
                table_id,
                batch,
                fields_to_return,
            )
            for batch in self._iter_upsert_batches(
                payload,
                fields_to_return,
                max_batch_record_count=max_batch_record_count,
                max_request_size_kb=max_request_size_kb,
                operation="Table.upsert_records",
            )
        ]

        return ResponseFactory.upsert_records(
            _merge_upsert_batch_responses(raw_responses),
            self.identifier,
        )

    def query_records(
        self,
        where: str,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None,
    ) -> QuickBaseResponse:
        table_id = self._require_table_id("Table.query_records")
        raw_response = QuickBaseRequest.query_records(
            self._api_client,
            table_id,
            where,
            select,
            sortBy,
            groupBy,
            options,
        )
        return ResponseFactory.query_records(raw_response, self.identifier)

    def iter_query_pages(
        self,
        where: str,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Iterator[QuickBaseResponse]:
        operation = "Table.iter_query_pages"
        page_size = self._validate_positive_int(
            page_size,
            name="page_size",
            operation=operation,
        )
        skip = self._validate_non_negative_int(
            options.skip if options is not None else None,
            name="skip",
            operation=operation,
        ) or 0
        remaining = self._validate_non_negative_int(
            options.top if options is not None else None,
            name="top",
            operation=operation,
        )
        compare_with_app_local_time = (
            options.compareWithAppLocalTime if options is not None else False
        )

        while remaining is None or remaining > 0:
            current_top = page_size if remaining is None else min(page_size, remaining)
            if current_top <= 0:
                return

            current_options = OptionsProperty(
                skip=skip,
                top=current_top,
                compareWithAppLocalTime=compare_with_app_local_time,
            )
            response = self.query_records(
                where,
                select,
                sortBy,
                groupBy,
                current_options,
            )
            yield response

            data = response.raw.get("data", [])
            page_record_count = len(data) if isinstance(data, list) else 0
            if page_record_count == 0:
                return

            metadata = response.raw.get("metadata", {})
            response_skip = skip
            total_records = None
            if isinstance(metadata, dict):
                if isinstance(metadata.get("skip"), int):
                    response_skip = metadata["skip"]
                if isinstance(metadata.get("totalRecords"), int):
                    total_records = metadata["totalRecords"]

            skip = response_skip + page_record_count
            if remaining is not None:
                remaining -= page_record_count
                if remaining <= 0:
                    return

            if total_records is not None and skip >= total_records:
                return
            if page_record_count < current_top:
                return

    def query_all(
        self,
        where: str,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> QuickBaseResponse:
        raw_responses = [
            response.raw
            for response in self.iter_query_pages(
                where,
                select,
                sortBy,
                groupBy,
                options,
                page_size=page_size,
            )
        ]
        return ResponseFactory.query_records(
            _merge_tabular_responses(raw_responses),
            self.identifier,
        )

    def run_report(
        self,
        report_identifier: Identifier | str | int,
        params: RunReportParams = RunReportParams(),
    ) -> QuickBaseResponse:
        report_ref = self._coerce_report_identifier(report_identifier)
        table_id = self._require_table_id("Table.run_report")
        report_id = report_ref.id
        if report_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Report operations require a resolved report id.",
                    operation="Table.run_report",
                    table_id=table_id,
                    object_ref=repr(report_ref),
                )
            )
        raw_response = QuickBaseRequest.run_report(
            self._api_client,
            table_id,
            report_id,
            params,
        )
        logger.debug("Table.run_report: raw_response=%s", raw_response)
        return ResponseFactory.run_report(raw_response, self.identifier)

    def iter_report_pages(
        self,
        report_identifier: Identifier | str | int,
        params: RunReportParams = RunReportParams(),
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Iterator[QuickBaseResponse]:
        operation = "Table.iter_report_pages"
        page_size = self._validate_positive_int(
            page_size,
            name="page_size",
            operation=operation,
        )
        skip = self._validate_non_negative_int(
            params.skip,
            name="skip",
            operation=operation,
        ) or 0
        remaining = self._validate_non_negative_int(
            params.top,
            name="top",
            operation=operation,
        )
        report_ref = self._coerce_report_identifier(report_identifier)

        while remaining is None or remaining > 0:
            current_top = page_size if remaining is None else min(page_size, remaining)
            if current_top <= 0:
                return

            response = self.run_report(
                report_ref,
                RunReportParams(skip=skip, top=current_top),
            )
            yield response

            data = response.raw.get("data", [])
            page_record_count = len(data) if isinstance(data, list) else 0
            if page_record_count == 0:
                return

            metadata = response.raw.get("metadata", {})
            response_skip = skip
            total_records = None
            if isinstance(metadata, dict):
                if isinstance(metadata.get("skip"), int):
                    response_skip = metadata["skip"]
                if isinstance(metadata.get("totalRecords"), int):
                    total_records = metadata["totalRecords"]

            skip = response_skip + page_record_count
            if remaining is not None:
                remaining -= page_record_count
                if remaining <= 0:
                    return

            if total_records is not None and skip >= total_records:
                return
            if page_record_count < current_top:
                return

    def run_formula(self, formula: str, record_id: int | None = None) -> QuickBaseResponse:
        table_id = self._require_table_id("Table.run_formula")
        raw_response = QuickBaseRequest.run_formula(
            self._api_client,
            table_id,
            formula,
            record_id,
        )
        return ResponseFactory.run_formula(raw_response)

    def upload_files(
        self,
        file_field_id: int,
        record_id: int | None = None,
        file_payload: FilePayload | None = None,
        *,
        multi_file_payload: List[UploadFileEntry] | None = None,
        fields_to_return: List[int] | None = None,
        max_file_size_kb: int | float | None = None,
        max_request_size_kb: int | float | None = None,
    ) -> QuickBaseResponse:
        operation = "Table.upload_files"
        table_id = self._require_table_id(operation)
        if file_field_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "upload_files requires file_field_id.",
                    operation=operation,
                    table_id=table_id,
                )
            )

        if multi_file_payload is not None and (file_payload is not None or record_id is not None):
            raise QuickbaseValidationError(
                format_error_message(
                    "Cannot mix single-file arguments with multi_file_payload.",
                    operation=operation,
                    table_id=table_id,
                    file_field_id=file_field_id,
                )
            )

        if multi_file_payload is None:
            if file_payload is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Single-file upload requires file_payload.",
                        operation=operation,
                        table_id=table_id,
                        file_field_id=file_field_id,
                    )
                )
            single_entry: UploadFileEntry = {"file": file_payload}
            if record_id is not None:
                single_entry["record_id"] = record_id
            multi_file_payload = [single_entry]

        if not multi_file_payload:
            raise QuickbaseValidationError(
                format_error_message(
                    "upload_files requires at least one file payload.",
                    operation=operation,
                    table_id=table_id,
                    file_field_id=file_field_id,
                )
            )

        file_size_limit_kb = self._resolve_file_size_limit_kb(
            max_file_size_kb,
            operation=operation,
        )
        request_size_limit_kb = self._resolve_request_size_limit_kb(
            max_request_size_kb,
            operation=operation,
        )

        data_payload: List[Dict[str, Any]] = []
        for entry in multi_file_payload:
            file_obj = entry.get("file")
            if not isinstance(file_obj, FilePayload):
                raise QuickbaseValidationError(
                    format_error_message(
                        "Each multi_file_payload entry must include a FilePayload under 'file'.",
                        operation=operation,
                        table_id=table_id,
                        file_field_id=file_field_id,
                        entry=entry,
                    )
                )

            try:
                file_dict = file_obj.as_dict(size_limit_kb=file_size_limit_kb)
            except Exception as exc:
                raise QuickbasePayloadError(
                    format_error_message(
                        "Failed to serialize file payload for upload.",
                        operation=operation,
                        table_id=table_id,
                        file_field_id=file_field_id,
                        entry=entry,
                        cause=exc,
                    )
                ) from exc

            per_record: Dict[str, Any] = {
                str(file_field_id): {"value": file_dict},
            }

            rec_id_candidate = entry.get("record_id")
            if rec_id_candidate is not None:
                if isinstance(rec_id_candidate, bool) or not isinstance(rec_id_candidate, int):
                    raise QuickbaseValidationError(
                        format_error_message(
                            "record_id must be an integer when provided.",
                            operation=operation,
                            table_id=table_id,
                            file_field_id=file_field_id,
                            record_id=rec_id_candidate,
                        )
                    )
                per_record["3"] = {"value": rec_id_candidate}

            data_payload.append(per_record)

        raw_responses = [
            QuickBaseRequest.upload_files(
                client=self._api_client,
                table_id=table_id,
                data=batch,
                fields_to_return=fields_to_return,
            )
            for batch in self._iter_upsert_batches(
                data_payload,
                fields_to_return,
                max_batch_record_count=len(data_payload),
                max_request_size_kb=request_size_limit_kb,
                operation=operation,
            )
        ]

        return ResponseFactory.upload_files(
            _merge_upsert_batch_responses(raw_responses),
            self.identifier,
        )

    def download_file(
        self,
        field_id: int,
        record_id: int,
        version_number: int,
        output_file_name: str,
        output_file_path: Path | str,
    ) -> QuickBaseResponse:
        table_id = self._require_table_id("Table.download_file")
        raw_response = QuickBaseRequest.download_file(
            self._api_client,
            table_id,
            field_id,
            record_id,
            version_number,
        )
        return ResponseFactory.download_file(
            raw_response,
            output_file_name,
            Path(output_file_path),
        )

    def delete_file(self, field_id: int, record_id: int, version_number: int) -> QuickBaseResponse:
        table_id = self._require_table_id("Table.delete_file")
        raw_response = QuickBaseRequest.delete_file(
            self._api_client,
            table_id,
            field_id,
            record_id,
            version_number,
        )
        return ResponseFactory.delete_file(raw_response)


TableRef = Table
