"""Factory helpers for Quickbase response wrapper objects."""

from pathlib import Path
from typing import Any, Dict

from quickbase_data_client.identifier import Identifier

from .responses import (
    DownloadFileResponse,
    GenericResponse,
    QuickBaseResponse,
    RunReportResponse,
    UpsertRecordsResponse,
    build_download_response,
)


class ResponseFactory:
    """Factory for creating specialized response wrappers."""

    @staticmethod
    def run_report(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        """Create a report response wrapper."""
        return RunReportResponse(raw, table_identifier)

    @staticmethod
    def run_formula(raw: Dict[str, Any]) -> QuickBaseResponse:
        """Create a formula response wrapper."""
        return GenericResponse(raw)

    @staticmethod
    def upsert_records(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        """Create an upsert-records response wrapper."""
        return UpsertRecordsResponse(raw, table_identifier)

    @staticmethod
    def query_records(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        """Create a query-records response wrapper."""
        return RunReportResponse(
            raw,
            table_identifier,
        )

    @staticmethod
    def delete_records(raw: Dict[str, Any]) -> QuickBaseResponse:
        """Create a delete-records response wrapper."""
        return GenericResponse(raw)

    @staticmethod
    def upload_files(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        """Create an upload-files response wrapper."""
        return UpsertRecordsResponse(raw, table_identifier)

    @staticmethod
    def download_file(
        raw: Any,
        file_name: str,
        output_path: Path | str,
    ) -> QuickBaseResponse:
        """Create a download-file response wrapper and write the file."""
        normalized_raw, saved_to = build_download_response(
            raw,
            output_file_name=file_name,
            output_path=Path(output_path),
        )
        return DownloadFileResponse(normalized_raw, saved_to)

    @staticmethod
    def delete_file(raw: Dict[str, Any]) -> QuickBaseResponse:
        """Create a delete-file response wrapper."""
        return GenericResponse(raw)
