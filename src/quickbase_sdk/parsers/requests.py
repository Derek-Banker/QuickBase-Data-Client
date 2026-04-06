# QuickBasePythonSDK\src\quickbase_sdk\parsers\requests.py
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Literal

from quickbase_sdk.quickbase_api import QuickBaseAPI

# from quickbase_sdk.parsers.requests import encode_file

# ======================================================
# Data classes for additional optional request parameters
# ======================================================

@dataclass(frozen=True)
class SortByProperty:
    field_id: int | None = None
    order: Literal["ASC", "DESC", "equal-values"] | None = None

@dataclass(frozen=True)
class GroupByProperty:
    field_id: int | None = None
    order: Literal["equal-values"] | None = None

@dataclass(frozen=True)
class OptionsProperty:
    skip: int | None = None
    top: int | None = None
    compareWithAppLocalTime: bool = False

# Parameter dataclasses for IDE support
@dataclass(frozen=True)
class RunReportParams:
    skip: int | None = None   # number of records to skip
    top:  int | None = None   # maximum records to return

@dataclass(frozen=True)
class QueryRecordsParams:
    select: List[int] | None = None
    where: str | None = None
    sortBy: List[SortByProperty] | None = None
    groupBy: List[GroupByProperty] | None = None
    options: OptionsProperty | None = None


def _build_records_payload(
    table_id: str,
    data: List[Dict[str, Any]],
    fields_to_return: List[int] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"to": table_id, "data": data}
    if fields_to_return:
        payload["fieldsToReturn"] = fields_to_return
    return payload


def build_upload_files_request(
    table_id: str,
    data: List[Dict[str, Any]],
    fields_to_return: List[int] | None = None,
) -> tuple[str, Dict[str, Any]]:
    return "/records", _build_records_payload(table_id, data, fields_to_return)


def build_download_file_request(
    table_id: str,
    field_id: int,
    record_id: int,
    version_number: int,
) -> tuple[str, None]:
    return f"/files/{table_id}/{record_id}/{field_id}/{version_number}", None


def build_delete_file_request(
    table_id: str,
    field_id: int,
    record_id: int,
    version_number: int,
) -> tuple[str, None]:
    return f"/files/{table_id}/{record_id}/{field_id}/{version_number}", None


def build_run_report_request(
    table_id: str,
    report_id: str,
    params: RunReportParams = RunReportParams(),
) -> tuple[str, Dict[str, Any]]:
    endpoint = f"/reports/{report_id}/run?tableId={table_id}"
    payload = {key: value for key, value in asdict(params).items() if value is not None}
    return endpoint, payload


def build_upsert_records_request(
    table_id: str,
    data: List[Dict[str, Any]],
    fields_to_return: List[int] | None = None,
) -> tuple[str, Dict[str, Any]]:
    return "/records", _build_records_payload(table_id, data, fields_to_return)


def build_query_records_request(
    table_id: str,
    where: str | None = None,
    select: List[int] | None = None,
    sortBy: List[SortByProperty] | None = None,
    groupBy: List[GroupByProperty] | None = None,
    options: OptionsProperty | None = None,
) -> tuple[str, Dict[str, Any]]:
    endpoint = "/records/query"
    payload: Dict[str, Any] = {"from": table_id}
    if where is not None:
        payload["where"] = where
    if select is not None:
        payload["select"] = select
    if sortBy is not None:
        payload["sortBy"] = [asdict(sort_by) for sort_by in sortBy]
    if groupBy is not None:
        payload["groupBy"] = [asdict(group_by) for group_by in groupBy]
    if options is not None:
        payload["options"] = {
            key: value for key, value in asdict(options).items() if value is not None
        }
    return endpoint, payload


def build_run_formula_request(
    table_id: str,
    formula: str,
    record_id: int | None = None,
) -> tuple[str, Dict[str, Any]]:
    endpoint = "/formula"
    payload: Dict[str, Any] = {"from": table_id, "formula": formula}
    if record_id is not None:
        payload["rid"] = record_id
    return endpoint, payload


# ======================================================
# Request class for QuickBase API calls
# ======================================================

class QuickBaseRequest:
    """
    Factory for building and executing QuickBase API calls.
    Each method defines its own dataclass for parameters, assembles
    the endpoint and payload, then invokes the API client.
    """

    @staticmethod
    def upload_files(
        client: QuickBaseAPI,
        table_id: str,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None = None
    ) -> Any:
        endpoint, payload = build_upload_files_request(table_id, data, fields_to_return)
        response = client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    def download_file(
        client: QuickBaseAPI,
        table_id: str,
        field_id: int,
        record_id: int,
        version_number: int
    ) -> Any:
        endpoint, _ = build_download_file_request(table_id, field_id, record_id, version_number)
        response = client.request(method="GET", endpoint=endpoint)
        return response

    @staticmethod
    def delete_file(
        client: QuickBaseAPI,
        table_id: str,
        field_id: int,
        record_id: int,
        version_number: int
    ) -> Any:
        endpoint, _ = build_delete_file_request(table_id, field_id, record_id, version_number)
        response = client.request(method="DELETE", endpoint=endpoint)
        return response.json()

    @staticmethod
    def run_report(
        client: QuickBaseAPI,
        table_id: str,
        report_id: str,
        params: RunReportParams = RunReportParams()
    ) -> Any:
        endpoint, payload = build_run_report_request(table_id, report_id, params)
        response = client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    def upsert_records(
        client: QuickBaseAPI,
        table_id: str,
        data: List[Dict[str, Any]],
        fields_to_return: List[int] | None = None
    ) -> Any:
        endpoint, payload = build_upsert_records_request(table_id, data, fields_to_return)
        response = client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    def query_records(
        client: QuickBaseAPI,
        table_id: str,
        where: str | None = None,
        select: List[int] | None = None,
        sortBy: List[SortByProperty] | None = None,
        groupBy: List[GroupByProperty] | None = None,
        options: OptionsProperty | None = None
    ) -> Any:
        endpoint, payload = build_query_records_request(
            table_id,
            where,
            select,
            sortBy,
            groupBy,
            options,
        )
        response = client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()

    @staticmethod
    def run_formula(
        client: QuickBaseAPI,
        table_id: str,
        formula: str,
        record_id: int | None = None
    ) -> Any:
        endpoint, payload = build_run_formula_request(table_id, formula, record_id)
        response = client.request(method="POST", endpoint=endpoint, payload=payload)
        return response.json()
