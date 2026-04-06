from dataclasses import dataclass
from numbers import Integral
from typing import Any, Dict, List, Literal

import numpy as np
import pandas as Pandas

from quickbase_data_client.exceptions import (
    QuickbaseError,
    QuickbaseNotFoundError,
    QuickbaseSchemaError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_data_client.identifier import Identifier
from quickbase_data_client.tools.sanitization import Sanitizer


@dataclass(frozen=True)
class _ResolvedColumn:
    original: Any
    field_id: str
    field_type: str | None


class DataFrameEncoder:
    @staticmethod
    def to_dataframe(
        data: List[Dict[str, Dict[str, Any]]],
        field_identities: List[Identifier],
    ) -> Pandas.DataFrame:
        raw_rows = []
        for record in data:
            row: Dict[Identifier, Any] = {}
            for ident in field_identities:
                if not isinstance(ident, Identifier):
                    raise QuickbaseValidationError(
                        format_error_message(
                            "All field_identities must be Identifier instances.",
                            operation="DataFrameEncoder.to_dataframe",
                            identifier_type=type(ident).__name__,
                        )
                    )
                raw = record.get(str(ident.id), {}).get("value", None)
                row[ident] = raw
            raw_rows.append(row)

        dataframe = Pandas.DataFrame.from_records(raw_rows, columns=field_identities)

        for ident in field_identities:
            field_type = (ident.type or "").lower()
            if field_type in ("number", "numeric"):
                dataframe[ident] = Pandas.to_numeric(dataframe[ident], errors="coerce")
            elif field_type == "date":
                dataframe[ident] = Pandas.to_datetime(dataframe[ident], errors="coerce").dt.date
            elif field_type in ("datetime", "timestamp"):
                dataframe[ident] = Pandas.to_datetime(dataframe[ident], errors="coerce")

        return dataframe

    @staticmethod
    def change_header(
        dataframe: Pandas.DataFrame,
        header_type: Literal["NAME", "ID"],
    ) -> Pandas.DataFrame:
        if header_type not in ("NAME", "ID"):
            raise QuickbaseValidationError(
                format_error_message(
                    "header_type must be 'NAME' or 'ID'.",
                    operation="DataFrameEncoder.change_header",
                    header_type=header_type,
                )
            )

        for column in dataframe.columns:
            if not isinstance(column, Identifier):
                raise QuickbaseValidationError(
                    format_error_message(
                        "All DataFrame columns must be Identifier instances.",
                        operation="DataFrameEncoder.change_header",
                        column_type=type(column).__name__,
                    )
                )

        if header_type == "NAME":
            rename_map = {ident: ident.name for ident in dataframe.columns}
        else:
            rename_map = {ident: str(ident.id) for ident in dataframe.columns}

        return dataframe.rename(columns=rename_map)

    @staticmethod
    def from_dataframe(
        dataframe: Pandas.DataFrame,
        table_identifier: Identifier | None = None,
    ) -> List[Dict[str, Dict[str, Any]]]:
        resolved_columns = DataFrameEncoder._resolve_columns(
            dataframe.columns,
            table_identifier=table_identifier,
        )
        records: List[Dict[str, Dict[str, Any]]] = []
        for row_values in dataframe.itertuples(index=False, name=None):
            record: Dict[str, Dict[str, Any]] = {}
            for resolved_column, value in zip(resolved_columns, row_values):
                value = Sanitizer.sanitize(value, resolved_column.field_type)
                if isinstance(value, np.generic):
                    value = value.item()
                record[resolved_column.field_id] = {"value": value}
            records.append(record)

        return records

    @staticmethod
    def _resolve_columns(
        columns: Any,
        *,
        table_identifier: Identifier | None,
    ) -> List[_ResolvedColumn]:
        resolved_columns: List[_ResolvedColumn] = []
        seen_field_ids: Dict[str, Any] = {}

        for column in columns:
            resolved = DataFrameEncoder._resolve_column(
                column,
                table_identifier=table_identifier,
            )
            prior_column = seen_field_ids.get(resolved.field_id)
            if prior_column is not None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Multiple DataFrame columns resolve to the same Quickbase field.",
                        operation="DataFrameEncoder.from_dataframe",
                        field_id=resolved.field_id,
                        first_column=prior_column,
                        second_column=column,
                    )
                )
            seen_field_ids[resolved.field_id] = column
            resolved_columns.append(resolved)

        return resolved_columns

    @staticmethod
    def _resolve_column(
        column: Any,
        *,
        table_identifier: Identifier | None,
    ) -> _ResolvedColumn:
        if isinstance(column, Identifier):
            if column.level != "FIELD":
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier DataFrame columns must reference FIELD identifiers.",
                        operation="DataFrameEncoder.from_dataframe",
                        identifier_level=column.level,
                        column=repr(column),
                    )
                )

            field_id = column.id
            if field_id is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "Identifier DataFrame columns must resolve to a field id.",
                        operation="DataFrameEncoder.from_dataframe",
                        column=repr(column),
                    )
                )

            return _ResolvedColumn(
                original=column,
                field_id=str(field_id),
                field_type=DataFrameEncoder._field_type_from_identifier(column),
            )

        if isinstance(column, bool):
            raise QuickbaseValidationError(
                format_error_message(
                    "Boolean DataFrame columns are not valid Quickbase field references.",
                    operation="DataFrameEncoder.from_dataframe",
                    column=column,
                )
            )

        if isinstance(column, Integral):
            return _ResolvedColumn(original=column, field_id=str(int(column)), field_type=None)

        if isinstance(column, str):
            if column.isdigit():
                return _ResolvedColumn(original=column, field_id=column, field_type=None)

            matched_identifier = DataFrameEncoder._resolve_named_column(
                column,
                table_identifier=table_identifier,
            )
            matched_field_id = matched_identifier.id
            if matched_field_id is None:
                raise QuickbaseSchemaError(
                    format_error_message(
                        "Schema-resolved DataFrame field name did not include an id.",
                        operation="DataFrameEncoder.from_dataframe",
                        column=column,
                        table_id=table_identifier.id if table_identifier is not None else None,
                    )
                )

            return _ResolvedColumn(
                original=column,
                field_id=str(matched_field_id),
                field_type=matched_identifier.type,
            )

        raise QuickbaseValidationError(
            format_error_message(
                "Unsupported DataFrame column type for Quickbase field resolution.",
                operation="DataFrameEncoder.from_dataframe",
                column=column,
                column_type=type(column).__name__,
            )
        )

    @staticmethod
    def _resolve_named_column(
        column_name: str,
        *,
        table_identifier: Identifier | None,
    ) -> Identifier:
        if table_identifier is None or table_identifier.level != "TABLE":
            raise QuickbaseSchemaError(
                format_error_message(
                    (
                        "Field-name DataFrame columns require cached schema "
                        "metadata on a TABLE identifier."
                    ),
                    operation="DataFrameEncoder.from_dataframe",
                    column=column_name,
                    table_identifier_level=(
                        table_identifier.level if table_identifier is not None else None
                    ),
                )
            )

        try:
            field_identities = table_identifier.field_identities()
        except QuickbaseSchemaError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Field-name DataFrame columns require cached schema metadata.",
                    operation="DataFrameEncoder.from_dataframe",
                    column=column_name,
                    table_id=table_identifier.id,
                    cause=exc,
                )
            ) from exc

        if field_identities is None:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Field-name DataFrame columns require cached schema metadata.",
                    operation="DataFrameEncoder.from_dataframe",
                    column=column_name,
                    table_id=table_identifier.id,
                )
            )

        matches = [identifier for identifier in field_identities if identifier.name == column_name]
        if not matches:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find a field for the DataFrame column name.",
                    operation="DataFrameEncoder.from_dataframe",
                    column=column_name,
                    table_id=table_identifier.id,
                )
            )

        if len(matches) > 1:
            raise QuickbaseValidationError(
                format_error_message(
                    "DataFrame column name is ambiguous across multiple Quickbase fields.",
                    operation="DataFrameEncoder.from_dataframe",
                    column=column_name,
                    table_id=table_identifier.id,
                    matching_field_ids=[match.id for match in matches],
                )
            )

        return matches[0]

    @staticmethod
    def _field_type_from_identifier(identifier: Identifier) -> str | None:
        try:
            return identifier.type
        except QuickbaseError:
            return None
