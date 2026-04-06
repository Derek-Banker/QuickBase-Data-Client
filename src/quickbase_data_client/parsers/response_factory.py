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
    """
    Factory for creating specialized QuickBaseResponse wrappers.
    """

    @staticmethod
    def run_report(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        return RunReportResponse(raw, table_identifier)

    @staticmethod
    def run_formula(raw: Dict[str, Any]) -> QuickBaseResponse:
        return GenericResponse(raw)

    @staticmethod
    def upsert_records(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        return UpsertRecordsResponse(raw, table_identifier)

    @staticmethod
    def query_records(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        return RunReportResponse(
            raw,
            table_identifier,
        )

    @staticmethod
    def delete_records(raw: Dict[str, Any]) -> QuickBaseResponse:
        return GenericResponse(raw)

    @staticmethod
    def upload_files(raw: Dict[str, Any], table_identifier: Identifier) -> QuickBaseResponse:
        return UpsertRecordsResponse(raw, table_identifier)

    @staticmethod
    def download_file(
        raw: Any,
        file_name: str,
        output_path: Path | str,
    ) -> QuickBaseResponse:
        normalized_raw, saved_to = build_download_response(
            raw,
            output_file_name=file_name,
            output_path=Path(output_path),
        )
        return DownloadFileResponse(normalized_raw, saved_to)

    @staticmethod
    def delete_file(raw: Dict[str, Any]) -> QuickBaseResponse:
        return GenericResponse(raw)
