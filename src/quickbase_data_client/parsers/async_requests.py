"""Async request helpers for supported table operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from quickbase_data_client.parsers.requests import (
    GroupByProperty,
    OptionsProperty,
    RunReportParams,
    SortByProperty,
    build_query_records_request,
    build_run_report_request,
    build_upload_files_request,
    build_upsert_records_request,
)

if TYPE_CHECKING:
    from quickbase_data_client.async_quickbase_api import AsyncQuickBaseAPI


class AsyncQuickBaseRequest:
    """Async request wrapper for the stable Phase 9 table operations."""

    @staticmethod
    async def upload_files(
        client: AsyncQuickBaseAPI,
        table_id: str,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None = None,
    ) -> Any:
        """Upload file attachment payloads asynchronously."""
        endpoint, payload = build_upload_files_request(table_id, data, fields_to_return)
        response = await client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    async def run_report(
        client: AsyncQuickBaseAPI,
        table_id: str,
        report_id: str,
        params: RunReportParams = RunReportParams(),
    ) -> Any:
        """Run a report asynchronously."""
        endpoint, payload = build_run_report_request(table_id, report_id, params)
        response = await client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    async def upsert_records(
        client: AsyncQuickBaseAPI,
        table_id: str,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None = None,
    ) -> Any:
        """Upsert records asynchronously."""
        endpoint, payload = build_upsert_records_request(table_id, data, fields_to_return)
        response = await client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    async def query_records(
        client: AsyncQuickBaseAPI,
        table_id: str,
        where: str | None = None,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None,
    ) -> Any:
        """Query records asynchronously."""
        endpoint, payload = build_query_records_request(
            table_id,
            where,
            select,
            sortBy,
            groupBy,
            options,
        )
        response = await client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()
