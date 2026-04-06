# src/quickbase_data_client/typed_structs/response_structs.py

from typing import TypedDict, List, Dict, Union

from quickbase_data_client.typed_structs.base_structs import AppStruct, TableStruct, FieldStruct
from quickbase_data_client.typed_structs.report_structs import ReportStruct

class GetAppResponse(AppStruct):
    """alias for GET /v1/apps/{appId} result"""

class GetTablesResponse(TypedDict):
    tables: List[TableStruct]

class GetFieldsResponse(TypedDict):
    fields: List[FieldStruct]

class GetReportsResponse(TypedDict):
    reports: List[ReportStruct]

# --- leaf wrapper around each value in `data` ---
class ValueWrapper(TypedDict):
    value: Union[str, int, float]

# --- each entry in the `data` list is a mapping fieldId→ValueWrapper ---
ReportRecord = Dict[str, ValueWrapper]

# --- fields array: static keys ---
class ReportField(TypedDict):
    id: int
    label: str
    type: str

# --- metadata object ---
class ReportMetadata(TypedDict):
    numFields: int
    numRecords: int
    skip: int
    totalRecords: int

# --- full run‐report response ---
class RunReportResponse(TypedDict):
    data: List[ReportRecord]
    fields: List[ReportField]
    metadata: ReportMetadata
