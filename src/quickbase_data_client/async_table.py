"""Async table wrapper for supported data workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterator, List, TypeAlias, cast, overload

import pandas as Pandas

from quickbase_data_client.exceptions import (
    QuickbasePayloadError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_data_client.file_payload import FilePayload
from quickbase_data_client.identifier import Identifier
from quickbase_data_client.parsers.async_requests import AsyncQuickBaseRequest
from quickbase_data_client.parsers.requests import (
    GroupByProperty,
    OptionsProperty,
    RunReportParams,
    SortByProperty,
)
from quickbase_data_client.parsers.response_factory import ResponseFactory
from quickbase_data_client.parsers.responses import QuickBaseResponse
from quickbase_data_client.table import (
    DEFAULT_UPSERT_BATCH_RECORD_COUNT,
    _merge_upsert_batch_responses,
)
from quickbase_data_client.table import (
    Table as SyncTable,
)

if TYPE_CHECKING:
    from quickbase_data_client.async_app import AsyncApp
    from quickbase_data_client.async_quickbase_api import AsyncQuickBaseAPI

UploadFileEntry: TypeAlias = Dict[str, object]


class AsyncTable:
    """Async table helper for the stable Phase 9 table operations."""

    @overload
    def __init__(self, app: AsyncApp, identifier: Identifier) -> None: ...

    @overload
    def __init__(self, app: AsyncApp, *, id: str) -> None: ...

    @overload
    def __init__(self, app: AsyncApp, *, name: str) -> None: ...

    @overload
    def __init__(self, app: AsyncApp, *, id: str, name: str) -> None: ...

    @overload
    def __init__(
        self,
        api_client: AsyncQuickBaseAPI,
        identifier: Identifier,
        *,
        app: AsyncApp | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        api_client: AsyncQuickBaseAPI,
        *,
        id: str,
        app: AsyncApp | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        api_client: AsyncQuickBaseAPI,
        *,
        name: str,
        app: AsyncApp | None = None,
    ) -> None: ...

    @overload
    def __init__(
        self,
        api_client: AsyncQuickBaseAPI,
        *,
        id: str,
        name: str,
        app: AsyncApp | None = None,
    ) -> None: ...

    def __init__(  # type: ignore[misc]
        self,
        api_client: AsyncQuickBaseAPI | AsyncApp,
        identifier: Identifier | None = None,
        *,
        id: str | None = None,
        name: str | None = None,
        app: AsyncApp | None = None,
    ) -> None:
        """Create an async table wrapper from a client or async app."""
        from quickbase_data_client.async_app import AsyncApp
        from quickbase_data_client.async_quickbase_api import AsyncQuickBaseAPI

        resolved_app: AsyncApp | None = None
        resolved_api_client: AsyncQuickBaseAPI
        if isinstance(api_client, AsyncQuickBaseAPI):
            resolved_api_client = api_client
            resolved_app = app
        elif isinstance(api_client, AsyncApp):
            resolved_api_client = api_client.api_client
            resolved_app = api_client
            if app is not None and app is not resolved_app:
                raise QuickbaseValidationError(
                    format_error_message(
                        "AsyncTable received conflicting app references.",
                        operation="AsyncTable.__init__",
                        table_id=id,
                        table_name=name,
                    )
                )
        else:
            raise QuickbaseValidationError(
                format_error_message(
                    "AsyncTable requires an AsyncQuickBaseAPI or AsyncApp instance.",
                    operation="AsyncTable.__init__",
                    api_client_type=type(api_client).__name__,
                )
            )

        sync_table_factory = cast(Any, SyncTable)
        self._delegate = sync_table_factory(
            resolved_api_client,
            identifier=identifier,
            id=id,
            name=name,
            app=resolved_app,
        )
        self._app = resolved_app

    @property
    def name(self):
        """Return the table name when available or resolvable."""
        return self._delegate.name

    @property
    def id(self):
        """Return the table id when available or resolvable."""
        return self._delegate.id

    @property
    def identifier(self):
        """Return the underlying table identifier."""
        return self._delegate.identifier

    @identifier.setter
    def identifier(self, identifier: Identifier):
        """Replace the underlying table identifier."""
        self._delegate.identifier = identifier

    @property
    def api_client(self) -> AsyncQuickBaseAPI:
        """Return the async API client used by this table wrapper."""
        return cast("AsyncQuickBaseAPI", self._delegate.api_client)

    @api_client.setter
    def api_client(self, api_client: AsyncQuickBaseAPI):
        """Replace the async API client used by this table wrapper."""
        self._delegate.api_client = api_client

    @property
    def app(self) -> AsyncApp | None:
        """Return the parent async app when this table is app-scoped."""
        return self._app

    def _normalize_upsert_data(
        self,
        data: List[Dict[str, Any]] | Pandas.DataFrame,
    ) -> List[Dict[str, Any]]:
        return self._delegate._normalize_upsert_data(data)

    def _iter_upsert_batches(
        self,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None,
        *,
        max_batch_record_count: int,
        max_request_size_kb: int | float,
        operation: str,
    ) -> Iterator[List[Dict[str, Any]]]:
        return self._delegate._iter_upsert_batches(
            data,
            fields_to_return,
            max_batch_record_count=max_batch_record_count,
            max_request_size_kb=max_request_size_kb,
            operation=operation,
        )

    def _coerce_report_identifier(self, report_identifier: Identifier | str | int) -> Identifier:
        return self._delegate._coerce_report_identifier(report_identifier)

    def _resolve_request_size_limit_kb(
        self,
        value: int | float | None,
        *,
        operation: str,
    ) -> float:
        return self._delegate._resolve_request_size_limit_kb(value, operation=operation)

    def _resolve_file_size_limit_kb(
        self,
        value: int | float | None,
        *,
        operation: str,
    ) -> float:
        return self._delegate._resolve_file_size_limit_kb(value, operation=operation)

    async def upsert_records(
        self,
        data: List[Dict[str, Any]] | Pandas.DataFrame,
        fields_to_return: List[int] | None = None,
        *,
        max_batch_record_count: int = DEFAULT_UPSERT_BATCH_RECORD_COUNT,
        max_request_size_kb: int | float | None = None,
    ) -> QuickBaseResponse:
        """Upsert records asynchronously, splitting oversized batches."""
        payload = self._normalize_upsert_data(data)
        request_size_limit_kb = self._resolve_request_size_limit_kb(
            max_request_size_kb,
            operation="AsyncTable.upsert_records",
        )

        raw_responses: List[Dict[str, Any]] = []
        for batch in self._iter_upsert_batches(
            payload,
            fields_to_return,
            max_batch_record_count=max_batch_record_count,
            max_request_size_kb=request_size_limit_kb,
            operation="AsyncTable.upsert_records",
        ):
            raw_responses.append(
                await AsyncQuickBaseRequest.upsert_records(
                    self.api_client,
                    self.id,
                    batch,
                    fields_to_return,
                )
            )

        return ResponseFactory.upsert_records(
            _merge_upsert_batch_responses(raw_responses),
            self.identifier,
        )

    async def query_records(
        self,
        where: str,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None,
    ) -> QuickBaseResponse:
        """Run an asynchronous query-records request."""
        raw_response = await AsyncQuickBaseRequest.query_records(
            self.api_client,
            self.id,
            where,
            select,
            sortBy,
            groupBy,
            options,
        )
        return ResponseFactory.query_records(raw_response, self.identifier)

    async def run_report(
        self,
        report_identifier: Identifier | str | int,
        params: RunReportParams = RunReportParams(),
    ) -> QuickBaseResponse:
        """Run a Quickbase report asynchronously."""
        report_ref = self._coerce_report_identifier(report_identifier)
        table_id = self.id
        if table_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Async table operations require a resolved table id.",
                    operation="AsyncTable.run_report",
                    table_name=self.name,
                    object_ref=repr(self.identifier),
                )
            )
        report_id = report_ref.id
        if report_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Report operations require a resolved report id.",
                    operation="AsyncTable.run_report",
                    table_id=table_id,
                    object_ref=repr(report_ref),
                )
            )
        raw_response = await AsyncQuickBaseRequest.run_report(
            self.api_client,
            table_id,
            report_id,
            params,
        )
        return ResponseFactory.run_report(raw_response, self.identifier)

    async def upload_files(
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
        """Upload one or more file attachments asynchronously."""
        operation = "AsyncTable.upload_files"
        table_id = self.id
        if table_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Async table operations require a resolved table id.",
                    operation=operation,
                    table_name=self.name,
                    object_ref=repr(self.identifier),
                )
            )
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

        raw_responses: List[Dict[str, Any]] = []
        for batch in self._iter_upsert_batches(
            data_payload,
            fields_to_return,
            max_batch_record_count=len(data_payload),
            max_request_size_kb=request_size_limit_kb,
            operation=operation,
        ):
            raw_responses.append(
                await AsyncQuickBaseRequest.upload_files(
                    client=self.api_client,
                    table_id=table_id,
                    data=batch,
                    fields_to_return=fields_to_return,
                )
            )

        return ResponseFactory.upload_files(
            _merge_upsert_batch_responses(raw_responses),
            self.identifier,
        )


AsyncTableRef = AsyncTable
