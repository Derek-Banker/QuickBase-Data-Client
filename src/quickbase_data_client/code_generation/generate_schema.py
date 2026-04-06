import argparse
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Literal

from quickbase_data_client.config import DEFAULT_SCHEMA_PATH_JSON
from quickbase_data_client.exceptions import (
    QuickbaseNotFoundError,
    QuickbaseSchemaError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_data_client.quickbase_api import Auth, QuickBaseAPI

logger = logging.getLogger(__name__)


class GenerateSchema:
    """
    Generate and update a local QuickBase schema cache (JSON file).
    """

    def __init__(
        self,
        auth: Auth | None = None,
        quickbase_realm: str | None = None,
        quickbase_token: str | None = None,
        mode: Literal["MIN", "MAX"] = "MAX",
        scope: Literal["ALL", "APP", "TABLES", "FIELDS", "REPORTS"] = "ALL",
        schema_path: str = DEFAULT_SCHEMA_PATH_JSON,
    ):
        if isinstance(auth, Auth):
            self.auth = auth
        else:
            if quickbase_realm is None or quickbase_token is None:
                raise QuickbaseValidationError(
                    format_error_message(
                        "GenerateSchema requires either an Auth instance or both quickbase_realm and quickbase_token.",
                        operation="GenerateSchema.__init__",
                    )
                )
            self.auth = Auth(quickbase_realm, quickbase_token)

        self.client = QuickBaseAPI(self.auth)

        self.mode = mode.upper()
        if self.mode not in ("MIN", "MAX"):
            raise QuickbaseValidationError(
                format_error_message(
                    "mode must be 'MIN' or 'MAX'.",
                    operation="GenerateSchema.__init__",
                    mode=mode,
                )
            )

        self.scope = scope.upper()
        valid_scopes = ("ALL", "APP", "TABLES", "FIELDS", "REPORTS")
        if self.scope not in valid_scopes:
            raise QuickbaseValidationError(
                format_error_message(
                    "scope must be one of the supported schema update scopes.",
                    operation="GenerateSchema.__init__",
                    scope=scope,
                    valid_scopes=valid_scopes,
                )
            )

        self.schema_path = Path(schema_path)

    def _unwrap(self, raw_json: Any) -> Any:
        if isinstance(raw_json, dict) and "data" in raw_json:
            return raw_json["data"]
        return raw_json

    def _request_json(self, *, method: Literal["GET", "POST"], endpoint: str, operation: str) -> Any:
        response = self.client.request(method=method, endpoint=endpoint)
        try:
            return self._unwrap(response.json())
        except ValueError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned invalid JSON while generating schema.",
                    operation=operation,
                    endpoint=endpoint,
                    cause=exc,
                )
            ) from exc

    def _load_schema(self) -> Dict[str, Any]:
        if not self.schema_path.is_file():
            return {"Schema": {}}

        try:
            return json.loads(self.schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Schema cache file contains invalid JSON.",
                    operation="GenerateSchema._load_schema",
                    schema_path=str(self.schema_path),
                    cause=exc,
                )
            ) from exc
        except OSError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Failed to read schema cache file.",
                    operation="GenerateSchema._load_schema",
                    schema_path=str(self.schema_path),
                    cause=exc,
                )
            ) from exc

    def _save_schema(self, schema: Dict[str, Any]) -> None:
        try:
            self.schema_path.parent.mkdir(parents=True, exist_ok=True)
            self.schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        except OSError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Failed to write schema cache file.",
                    operation="GenerateSchema._save_schema",
                    schema_path=str(self.schema_path),
                    cause=exc,
                )
            ) from exc

    def _transform(self, data: Dict[str, Any]) -> Dict[str, Any]:
        node = {
            "id": data.get("id"),
            "name": data.get("name") or data.get("label"),
        }

        if self.mode == "MAX":
            for key, value in data.items():
                if key not in node:
                    node[key] = value
        return node

    def _find_app_node(self, schema: Dict[str, Any], app_id: str) -> Dict[str, Any]:
        for app_val in schema.get("Schema", {}).values():
            if app_val.get("id") == app_id:
                return app_val
        raise QuickbaseNotFoundError(
            format_error_message(
                "App was not found in the local schema cache.",
                operation="GenerateSchema._find_app_node",
                app_id=app_id,
                schema_path=str(self.schema_path),
            )
        )

    def _find_table_node(self, app_node: Dict[str, Any], table_id: str) -> Dict[str, Any]:
        for table_node in app_node.get("Tables", {}).values():
            if table_node.get("id") == table_id:
                return table_node
        raise QuickbaseNotFoundError(
            format_error_message(
                "Table was not found in the local schema cache.",
                operation="GenerateSchema._find_table_node",
                table_id=table_id,
                app_id=app_node.get("id"),
                schema_path=str(self.schema_path),
            )
        )

    def update_schema(self, app_id: str, table_id: str | None = None) -> None:
        if self.scope == "APP":
            self.update_app(app_id)
        elif self.scope == "TABLES":
            self.update_tables(app_id)
        elif self.scope in ("FIELDS", "REPORTS") and table_id:
            if self.scope == "FIELDS":
                self.update_table_fields(app_id, table_id)
            else:
                self.update_table_reports(app_id, table_id)
        else:
            self.update_all(app_id)

    def update_app(self, app_id: str) -> None:
        app_meta = self._request_json(
            method="GET",
            endpoint=f"/apps/{app_id}",
            operation="GenerateSchema.update_app",
        )
        node = self._transform(app_meta)

        schema = self._load_schema()
        for key, value in list(schema.get("Schema", {}).items()):
            if value.get("id") == app_id:
                del schema["Schema"][key]

        schema.setdefault("Schema", {})[node["name"]] = node
        self._save_schema(schema)
        logger.info("Updated APP '%s' (%s)", node["name"], app_id)

    def update_tables(self, app_id: str) -> None:
        tables = self._request_json(
            method="GET",
            endpoint=f"/tables?appId={app_id}",
            operation="GenerateSchema.update_tables",
        )
        tables_node = {table["name"]: self._transform(table) for table in tables}

        schema = self._load_schema()
        for app_val in schema.get("Schema", {}).values():
            if app_val.get("id") == app_id:
                base = {key: value for key, value in app_val.items() if key != "Tables"}
                break
        else:
            base = {"id": app_id, "name": app_id}

        base["Tables"] = tables_node
        schema.setdefault("Schema", {})[base["name"]] = base
        self._save_schema(schema)
        logger.info("Updated TABLES for APP '%s' (%s)", base["name"], app_id)

    def update_all(self, app_id: str) -> None:
        app_meta = self._request_json(
            method="GET",
            endpoint=f"/apps/{app_id}",
            operation="GenerateSchema.update_all",
        )
        app_node = self._transform(app_meta)
        app_node["Tables"] = {}

        tables = self._request_json(
            method="GET",
            endpoint=f"/tables?appId={app_id}",
            operation="GenerateSchema.update_all",
        )

        def fetch_children(table: Dict[str, Any]) -> tuple[Dict[str, Any], Any, Any]:
            table_id = table.get("id")
            fields = self._request_json(
                method="GET",
                endpoint=f"/fields?tableId={table_id}",
                operation="GenerateSchema.update_all",
            )
            reports = self._request_json(
                method="GET",
                endpoint=f"/reports?tableId={table_id}",
                operation="GenerateSchema.update_all",
            )
            return table, fields, reports

        with ThreadPoolExecutor() as executor:
            futures = [executor.submit(fetch_children, table) for table in tables]
            for future in as_completed(futures):
                table, fields, reports = future.result()
                node = self._transform(table)
                if fields:
                    node["Fields"] = [self._transform(field) for field in fields]
                if reports:
                    node["Reports"] = [self._transform(report) for report in reports]
                app_node["Tables"][node["name"]] = node

        schema = self._load_schema()
        for key, value in list(schema.get("Schema", {}).items()):
            if value.get("id") == app_id:
                del schema["Schema"][key]

        schema.setdefault("Schema", {})[app_node["name"]] = app_node
        self._save_schema(schema)
        logger.info("Updated ALL metadata for APP '%s' (%s)", app_node["name"], app_id)

    def update_table_fields(self, app_id: str, table_id: str) -> None:
        fields = self._request_json(
            method="GET",
            endpoint=f"/fields?tableId={table_id}",
            operation="GenerateSchema.update_table_fields",
        )

        schema = self._load_schema()
        app_node = self._find_app_node(schema, app_id)
        table_node = self._find_table_node(app_node, table_id)
        table_node["Fields"] = [self._transform(field) for field in fields]

        self._save_schema(schema)
        logger.info("Updated FIELDS for TABLE %s under APP %s", table_id, app_id)

    def update_table_reports(self, app_id: str, table_id: str) -> None:
        reports = self._request_json(
            method="GET",
            endpoint=f"/reports?tableId={table_id}",
            operation="GenerateSchema.update_table_reports",
        )

        schema = self._load_schema()
        app_node = self._find_app_node(schema, app_id)
        table_node = self._find_table_node(app_node, table_id)
        table_node["Reports"] = [self._transform(report) for report in reports]

        self._save_schema(schema)
        logger.info("Updated REPORTS for TABLE %s under APP %s", table_id, app_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or update QuickBase schema JSON.")
    parser.add_argument("app_id", help="QuickBase App ID to fetch.")
    parser.add_argument("--table-id", help="Table ID when using FIELDS or REPORTS scope.")
    parser.add_argument(
        "--scope",
        choices=["ALL", "APP", "TABLES", "FIELDS", "REPORTS"],
        default="ALL",
        help="Scope of metadata to fetch.",
    )
    parser.add_argument(
        "--mode",
        choices=["MIN", "MAX"],
        default="MAX",
        help="Level of details to include (MIN=id/name only, MAX=full).",
    )
    parser.add_argument(
        "--schema-path",
        default=DEFAULT_SCHEMA_PATH_JSON,
        help="Path to write the JSON schema file.",
    )
    args = parser.parse_args()

    realm = os.getenv("QUICKBASE_REALM")
    token = os.getenv("QUICKBASE_USER_TOKEN")
    if not realm or not token:
        parser.error("Environment variables QUICKBASE_REALM and QUICKBASE_USER_TOKEN must be set.")

    generator = GenerateSchema(
        quickbase_realm=realm,
        quickbase_token=token,
        mode=args.mode,
        scope=args.scope,
        schema_path=args.schema_path,
    )
    generator.update_schema(args.app_id, args.table_id)


if __name__ == "__main__":
    main()
