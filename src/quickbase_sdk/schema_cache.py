from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Dict, Literal, cast

from quickbase_sdk.config import DEFAULT_SCHEMA_PATH_SQLITE
from quickbase_sdk.exceptions import (
    QuickbaseConfigurationError,
    QuickbaseNotFoundError,
    QuickbaseSchemaError,
    QuickbaseValidationError,
    format_error_message,
)

if TYPE_CHECKING:
    from quickbase_sdk.identifier import Identifier
    from quickbase_sdk.quickbase_api import QuickBaseAPI

logger = logging.getLogger(__name__)

RefreshPolicy = Literal["never", "missing", "stale", "always"]
_REFRESH_POLICIES = {"never", "missing", "stale", "always"}


async def _await_value(value: Awaitable[Any]) -> Any:
    return await value


def _resolve_maybe_awaitable(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(_await_value(cast(Awaitable[Any], value)))
        except BaseException as exc:
            error["exc"] = exc

    thread = threading.Thread(
        target=_runner,
        name="quickbase-sdk-schema-cache-request",
    )
    thread.start()
    thread.join()

    if "exc" in error:
        raise error["exc"]
    return result.get("value")


class SchemaCache:
    """
    Explicit SQLite-backed schema cache.

    Cache granularity is intentionally segmented:
    - APP metadata by app id
    - TABLES list by app id
    - FIELDS list by table id
    - REPORTS list by table id
    """

    def __init__(
        self,
        api_client: QuickBaseAPI | None = None,
        *,
        path: str | Path = DEFAULT_SCHEMA_PATH_SQLITE,
        default_refresh_policy: RefreshPolicy = "missing",
        stale_after_seconds: float = 3600.0,
    ) -> None:
        self._path = self._normalize_path(path)
        self._default_refresh_policy = self._normalize_refresh_policy(
            default_refresh_policy,
            operation="SchemaCache.__init__",
        )
        self._stale_after_seconds = self._normalize_stale_after_seconds(stale_after_seconds)
        self._api_client: QuickBaseAPI | None = None
        self._connection = self._connect()
        self._initialize_database()

        if api_client is not None:
            self.api_client = api_client

    @property
    def api_client(self) -> QuickBaseAPI | None:
        return self._api_client

    @api_client.setter
    def api_client(self, api_client: QuickBaseAPI) -> None:
        from quickbase_sdk.quickbase_api import QuickBaseAPI

        if not isinstance(api_client, QuickBaseAPI):
            raise QuickbaseValidationError(
                format_error_message(
                    "SchemaCache.api_client must be a QuickBaseAPI instance.",
                    operation="SchemaCache.api_client",
                    api_client_type=type(api_client).__name__,
                )
            )
        self._api_client = api_client

    @property
    def path(self) -> str:
        if isinstance(self._path, Path):
            return str(self._path)
        return self._path

    @property
    def default_refresh_policy(self) -> RefreshPolicy:
        return self._default_refresh_policy

    @property
    def stale_after_seconds(self) -> float:
        return self._stale_after_seconds

    def close(self) -> None:
        self._connection.close()

    def refresh_app(self, app_id: str) -> None:
        payload = self._request_json(
            method="GET",
            endpoint=f"/apps/{app_id}",
            operation="SchemaCache.refresh_app",
        )
        if not isinstance(payload, dict):
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned unexpected APP metadata.",
                    operation="SchemaCache.refresh_app",
                    app_id=app_id,
                )
            )

        normalized_app_id = self._require_identifier(
            payload.get("id"),
            operation="SchemaCache.refresh_app",
            key="app_id",
        )
        app_name = self._require_name(
            payload,
            operation="SchemaCache.refresh_app",
            key="app_name",
        )
        fetched_at = time.time()

        cursor = self._connection.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO apps(id, name, payload, fetched_at)
            VALUES (?, ?, ?, ?);
            """,
            (normalized_app_id, app_name, self._serialize_payload(payload), fetched_at),
        )
        cursor.execute(
            """
            INSERT OR REPLACE INTO schema_segments(segment, owner_id, fetched_at)
            VALUES (?, ?, ?);
            """,
            ("APP", normalized_app_id, fetched_at),
        )
        self._connection.commit()

    def refresh_tables(self, app_id: str) -> None:
        payload = self._request_json(
            method="GET",
            endpoint=f"/tables?appId={app_id}",
            operation="SchemaCache.refresh_tables",
        )
        if not isinstance(payload, list):
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned unexpected TABLE metadata.",
                    operation="SchemaCache.refresh_tables",
                    app_id=app_id,
                )
            )

        normalized_app_id = str(app_id)
        fetched_at = time.time()
        cursor = self._connection.cursor()
        cursor.execute("SELECT id FROM tables WHERE app_id = ?;", (normalized_app_id,))
        existing_ids = {row[0] for row in cursor.fetchall()}
        seen_ids: set[str] = set()

        for table in payload:
            if not isinstance(table, dict):
                continue
            table_id = self._require_identifier(
                table.get("id"),
                operation="SchemaCache.refresh_tables",
                key="table_id",
            )
            table_name = self._require_name(
                table,
                operation="SchemaCache.refresh_tables",
                key="table_name",
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO tables(id, app_id, name, payload, fetched_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (
                    table_id,
                    normalized_app_id,
                    table_name,
                    self._serialize_payload(table),
                    fetched_at,
                ),
            )
            seen_ids.add(table_id)

        removed_ids = existing_ids - seen_ids
        self._remove_tables(cursor, removed_ids)
        cursor.execute(
            """
            INSERT OR REPLACE INTO schema_segments(segment, owner_id, fetched_at)
            VALUES (?, ?, ?);
            """,
            ("TABLES", normalized_app_id, fetched_at),
        )
        self._connection.commit()

    def refresh_fields(self, table_id: str) -> None:
        payload = self._request_json(
            method="GET",
            endpoint=f"/fields?tableId={table_id}",
            operation="SchemaCache.refresh_fields",
        )
        if not isinstance(payload, list):
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned unexpected FIELD metadata.",
                    operation="SchemaCache.refresh_fields",
                    table_id=table_id,
                )
            )

        normalized_table_id = str(table_id)
        fetched_at = time.time()
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM fields WHERE table_id = ?;", (normalized_table_id,))

        for field in payload:
            if not isinstance(field, dict):
                continue
            field_id = self._require_identifier(
                field.get("id"),
                operation="SchemaCache.refresh_fields",
                key="field_id",
            )
            field_label = self._require_name(
                field,
                operation="SchemaCache.refresh_fields",
                key="field_label",
                preferred_key="label",
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO fields(table_id, id, label, field_type, payload, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    normalized_table_id,
                    field_id,
                    field_label,
                    field.get("fieldType"),
                    self._serialize_payload(field),
                    fetched_at,
                ),
            )

        cursor.execute(
            """
            INSERT OR REPLACE INTO schema_segments(segment, owner_id, fetched_at)
            VALUES (?, ?, ?);
            """,
            ("FIELDS", normalized_table_id, fetched_at),
        )
        self._connection.commit()

    def refresh_reports(self, table_id: str) -> None:
        payload = self._request_json(
            method="GET",
            endpoint=f"/reports?tableId={table_id}",
            operation="SchemaCache.refresh_reports",
        )
        if not isinstance(payload, list):
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned unexpected REPORT metadata.",
                    operation="SchemaCache.refresh_reports",
                    table_id=table_id,
                )
            )

        normalized_table_id = str(table_id)
        fetched_at = time.time()
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM reports WHERE table_id = ?;", (normalized_table_id,))

        for report in payload:
            if not isinstance(report, dict):
                continue
            report_id = self._require_identifier(
                report.get("id"),
                operation="SchemaCache.refresh_reports",
                key="report_id",
            )
            report_name = self._require_name(
                report,
                operation="SchemaCache.refresh_reports",
                key="report_name",
            )
            cursor.execute(
                """
                INSERT OR REPLACE INTO reports(table_id, id, name, report_type, payload, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    normalized_table_id,
                    report_id,
                    report_name,
                    report.get("type"),
                    self._serialize_payload(report),
                    fetched_at,
                ),
            )

        cursor.execute(
            """
            INSERT OR REPLACE INTO schema_segments(segment, owner_id, fetched_at)
            VALUES (?, ?, ?);
            """,
            ("REPORTS", normalized_table_id, fetched_at),
        )
        self._connection.commit()

    def invalidate_app(self, app_id: str) -> None:
        normalized_app_id = str(app_id)
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM apps WHERE id = ?;", (normalized_app_id,))
        cursor.execute(
            "DELETE FROM schema_segments WHERE segment = ? AND owner_id = ?;",
            ("APP", normalized_app_id),
        )
        self._connection.commit()

    def invalidate_tables(self, app_id: str) -> None:
        normalized_app_id = str(app_id)
        cursor = self._connection.cursor()
        cursor.execute("SELECT id FROM tables WHERE app_id = ?;", (normalized_app_id,))
        table_ids = {row[0] for row in cursor.fetchall()}
        self._remove_tables(cursor, table_ids)
        cursor.execute(
            "DELETE FROM schema_segments WHERE segment = ? AND owner_id = ?;",
            ("TABLES", normalized_app_id),
        )
        self._connection.commit()

    def invalidate_fields(self, table_id: str) -> None:
        normalized_table_id = str(table_id)
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM fields WHERE table_id = ?;", (normalized_table_id,))
        cursor.execute(
            "DELETE FROM schema_segments WHERE segment = ? AND owner_id = ?;",
            ("FIELDS", normalized_table_id),
        )
        self._connection.commit()

    def invalidate_reports(self, table_id: str) -> None:
        normalized_table_id = str(table_id)
        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM reports WHERE table_id = ?;", (normalized_table_id,))
        cursor.execute(
            "DELETE FROM schema_segments WHERE segment = ? AND owner_id = ?;",
            ("REPORTS", normalized_table_id),
        )
        self._connection.commit()

    def get_id(
        self,
        level: Literal["APP", "TABLE", "FIELD", "REPORT"],
        name: str,
        parent_id: str | None = None,
        refresh_policy: RefreshPolicy | None = None,
    ) -> str:
        normalized_level = self._normalize_level(level, operation="SchemaCache.get_id")

        if normalized_level == "APP":
            row = self._connection.execute(
                "SELECT id FROM apps WHERE name = ?;",
                (name,),
            ).fetchone()
            if row is not None:
                return str(row[0])
            raise QuickbaseNotFoundError(
                format_error_message(
                    (
                        "APP name lookup requires cached app metadata. Refresh "
                        "that app explicitly before resolving by name."
                    ),
                    operation="SchemaCache.get_id",
                    level=normalized_level,
                    name=name,
                )
            )

        normalized_parent_id = self._require_parent_id(
            parent_id,
            level=normalized_level,
            operation="SchemaCache.get_id",
            name=name,
        )

        if normalized_level == "TABLE":
            self._maybe_refresh_segment(
                "TABLES",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_id",
            )
            row = self._connection.execute(
                "SELECT id FROM tables WHERE app_id = ? AND name = ?;",
                (normalized_parent_id, name),
            ).fetchone()
        elif normalized_level == "FIELD":
            self._maybe_refresh_segment(
                "FIELDS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_id",
            )
            row = self._connection.execute(
                "SELECT id FROM fields WHERE table_id = ? AND label = ?;",
                (normalized_parent_id, name),
            ).fetchone()
        else:
            self._maybe_refresh_segment(
                "REPORTS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_id",
            )
            row = self._connection.execute(
                "SELECT id FROM reports WHERE table_id = ? AND name = ?;",
                (normalized_parent_id, name),
            ).fetchone()

        if row is None:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find the requested object by name.",
                    operation="SchemaCache.get_id",
                    level=normalized_level,
                    name=name,
                    parent_id=normalized_parent_id,
                )
            )
        return str(row[0])

    def get_name(
        self,
        level: Literal["APP", "TABLE", "FIELD", "REPORT"],
        id: str,
        parent_id: str | None = None,
        refresh_policy: RefreshPolicy | None = None,
    ) -> str:
        normalized_level = self._normalize_level(level, operation="SchemaCache.get_name")
        normalized_id = str(id)

        if normalized_level == "APP":
            self._maybe_refresh_segment(
                "APP",
                normalized_id,
                refresh_policy,
                operation="SchemaCache.get_name",
            )
            row = self._connection.execute(
                "SELECT name FROM apps WHERE id = ?;",
                (normalized_id,),
            ).fetchone()
        elif normalized_level == "TABLE":
            if parent_id is not None:
                normalized_parent_id = str(parent_id)
                self._maybe_refresh_segment(
                    "TABLES",
                    normalized_parent_id,
                    refresh_policy,
                    operation="SchemaCache.get_name",
                )
                row = self._connection.execute(
                    "SELECT name FROM tables WHERE id = ? AND app_id = ?;",
                    (normalized_id, normalized_parent_id),
                ).fetchone()
            else:
                row = self._connection.execute(
                    "SELECT name FROM tables WHERE id = ?;",
                    (normalized_id,),
                ).fetchone()
        elif normalized_level == "FIELD":
            normalized_parent_id = self._require_parent_id(
                parent_id,
                level=normalized_level,
                operation="SchemaCache.get_name",
                identifier_id=normalized_id,
            )
            self._maybe_refresh_segment(
                "FIELDS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_name",
            )
            row = self._connection.execute(
                "SELECT label FROM fields WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, normalized_id),
            ).fetchone()
        else:
            normalized_parent_id = self._require_parent_id(
                parent_id,
                level=normalized_level,
                operation="SchemaCache.get_name",
                identifier_id=normalized_id,
            )
            self._maybe_refresh_segment(
                "REPORTS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_name",
            )
            row = self._connection.execute(
                "SELECT name FROM reports WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, normalized_id),
            ).fetchone()

        if row is None:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find the requested object by id.",
                    operation="SchemaCache.get_name",
                    level=normalized_level,
                    identifier_id=normalized_id,
                    parent_id=parent_id,
                )
            )
        return str(row[0])

    def get_parent(
        self,
        level: Literal["APP", "TABLE", "FIELD", "REPORT"],
        id: str,
        refresh_policy: RefreshPolicy | None = None,
    ) -> str | None:
        normalized_level = self._normalize_level(level, operation="SchemaCache.get_parent")
        normalized_id = str(id)

        if refresh_policy is not None:
            self._normalize_refresh_policy(refresh_policy, operation="SchemaCache.get_parent")

        if normalized_level == "APP":
            return None
        if normalized_level == "TABLE":
            row = self._connection.execute(
                "SELECT app_id FROM tables WHERE id = ?;",
                (normalized_id,),
            ).fetchone()
            return None if row is None else str(row[0])

        table_name = "fields" if normalized_level == "FIELD" else "reports"
        rows = self._connection.execute(
            f"SELECT table_id FROM {table_name} WHERE id = ?;",
            (normalized_id,),
        ).fetchall()
        if len(rows) == 1:
            return str(rows[0][0])
        return None

    def get_properties(
        self,
        level: Literal["APP", "TABLE", "FIELD", "REPORT"],
        id_or_name: str,
        parent_id: str | None = None,
        refresh_policy: RefreshPolicy | None = None,
    ) -> Dict[str, Any]:
        normalized_level = self._normalize_level(level, operation="SchemaCache.get_properties")
        identifier = str(id_or_name)

        if normalized_level == "APP":
            self._maybe_refresh_segment(
                "APP",
                identifier,
                refresh_policy,
                operation="SchemaCache.get_properties",
            )
            row = self._connection.execute(
                "SELECT payload FROM apps WHERE id = ?;",
                (identifier,),
            ).fetchone()
        elif normalized_level == "TABLE":
            if parent_id is not None:
                normalized_parent_id = str(parent_id)
                self._maybe_refresh_segment(
                    "TABLES",
                    normalized_parent_id,
                    refresh_policy,
                    operation="SchemaCache.get_properties",
                )
                row = self._connection.execute(
                    "SELECT payload FROM tables WHERE id = ? AND app_id = ?;",
                    (identifier, normalized_parent_id),
                ).fetchone()
            else:
                row = self._connection.execute(
                    "SELECT payload FROM tables WHERE id = ?;",
                    (identifier,),
                ).fetchone()
        elif normalized_level == "FIELD":
            normalized_parent_id = self._require_parent_id(
                parent_id,
                level=normalized_level,
                operation="SchemaCache.get_properties",
                identifier=identifier,
            )
            self._maybe_refresh_segment(
                "FIELDS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_properties",
            )
            row = self._connection.execute(
                "SELECT payload FROM fields WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, identifier),
            ).fetchone()
        else:
            normalized_parent_id = self._require_parent_id(
                parent_id,
                level=normalized_level,
                operation="SchemaCache.get_properties",
                identifier=identifier,
            )
            self._maybe_refresh_segment(
                "REPORTS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_properties",
            )
            row = self._connection.execute(
                "SELECT payload FROM reports WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, identifier),
            ).fetchone()

        if row is None or row[0] is None:
            return {}

        try:
            payload = json.loads(str(row[0]))
        except json.JSONDecodeError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Schema cache contains invalid JSON metadata.",
                    operation="SchemaCache.get_properties",
                    level=normalized_level,
                    identifier=identifier,
                    parent_id=parent_id,
                    cause=exc,
                )
            ) from exc

        if not isinstance(payload, dict):
            return {}
        return cast(Dict[str, Any], payload)

    def get_type(
        self,
        level: Literal["FIELD", "REPORT"],
        id: str,
        parent_id: str | None,
        refresh_policy: RefreshPolicy | None = None,
    ) -> str:
        normalized_level = self._normalize_level(level, operation="SchemaCache.get_type")
        if normalized_level not in {"FIELD", "REPORT"}:
            raise QuickbaseValidationError(
                format_error_message(
                    "Schema type lookups are only valid for FIELD and REPORT identifiers.",
                    operation="SchemaCache.get_type",
                    level=level,
                )
            )

        normalized_parent_id = self._require_parent_id(
            parent_id,
            level=normalized_level,
            operation="SchemaCache.get_type",
            identifier_id=id,
        )

        if normalized_level == "FIELD":
            self._maybe_refresh_segment(
                "FIELDS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_type",
            )
            row = self._connection.execute(
                "SELECT field_type FROM fields WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, str(id)),
            ).fetchone()
        else:
            self._maybe_refresh_segment(
                "REPORTS",
                normalized_parent_id,
                refresh_policy,
                operation="SchemaCache.get_type",
            )
            row = self._connection.execute(
                "SELECT report_type FROM reports WHERE table_id = ? AND id = ?;",
                (normalized_parent_id, str(id)),
            ).fetchone()

        if row is None or row[0] is None:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find object type.",
                    operation="SchemaCache.get_type",
                    level=normalized_level,
                    identifier_id=id,
                    parent_id=normalized_parent_id,
                )
            )
        return str(row[0])

    def generate_field_identities(
        self,
        table_identifier: Identifier,
        refresh_policy: RefreshPolicy | None = None,
    ) -> list[Identifier]:
        if table_identifier.level != "TABLE":
            raise QuickbaseValidationError(
                format_error_message(
                    "generate_field_identities requires a TABLE identifier.",
                    operation="SchemaCache.generate_field_identities",
                    identifier_level=table_identifier.level,
                    object_ref=repr(table_identifier),
                )
            )

        table_id = table_identifier.id
        if table_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "TABLE identifier requires an id before field identities can be generated.",
                    operation="SchemaCache.generate_field_identities",
                    object_ref=repr(table_identifier),
                )
            )

        self._maybe_refresh_segment(
            "FIELDS",
            table_id,
            refresh_policy,
            operation="SchemaCache.generate_field_identities",
        )
        rows = self._connection.execute(
            """
            SELECT id, label, field_type
            FROM fields
            WHERE table_id = ?
            ORDER BY CAST(id AS INTEGER), id;
            """,
            (table_id,),
        ).fetchall()

        field_identities: list[Identifier] = []
        for field_id, label, field_type in rows:
            field_identities.append(
                table_identifier.create_child(
                    level="FIELD",
                    id=str(field_id),
                    name=str(label),
                    type=None if field_type is None else str(field_type),
                )
            )
        return field_identities

    def _connect(self) -> sqlite3.Connection:
        if isinstance(self._path, Path):
            self._path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self._path))
        else:
            connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        cursor = self._connection.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_segments(
                segment TEXT NOT NULL,
                owner_id TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY(segment, owner_id)
            );

            CREATE TABLE IF NOT EXISTS apps(
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                fetched_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_apps_name ON apps(name);

            CREATE TABLE IF NOT EXISTS tables(
                id TEXT PRIMARY KEY,
                app_id TEXT NOT NULL,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                fetched_at REAL NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tables_app_name ON tables(app_id, name);
            CREATE INDEX IF NOT EXISTS idx_tables_app_id ON tables(app_id);

            CREATE TABLE IF NOT EXISTS fields(
                table_id TEXT NOT NULL,
                id TEXT NOT NULL,
                label TEXT NOT NULL,
                field_type TEXT,
                payload TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY(table_id, id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_fields_table_label ON fields(table_id, label);
            CREATE INDEX IF NOT EXISTS idx_fields_id ON fields(id);

            CREATE TABLE IF NOT EXISTS reports(
                table_id TEXT NOT NULL,
                id TEXT NOT NULL,
                name TEXT NOT NULL,
                report_type TEXT,
                payload TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                PRIMARY KEY(table_id, id)
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_table_name ON reports(table_id, name);
            CREATE INDEX IF NOT EXISTS idx_reports_id ON reports(id);
            """
        )
        self._connection.commit()

    def _request_json(
        self,
        *,
        method: Literal["GET", "POST"],
        endpoint: str,
        operation: str,
    ) -> Any:
        if self._api_client is None:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Schema cache refresh requires a QuickBaseAPI client.",
                    operation=operation,
                    endpoint=endpoint,
                    cache_path=self.path,
                )
            )

        response = self._api_client.request(method=method, endpoint=endpoint)
        response = _resolve_maybe_awaitable(response)
        try:
            payload = response.json()
        except ValueError as exc:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase returned invalid JSON while refreshing schema cache.",
                    operation=operation,
                    endpoint=endpoint,
                    cause=exc,
                )
            ) from exc

        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    def _maybe_refresh_segment(
        self,
        segment: Literal["APP", "TABLES", "FIELDS", "REPORTS"],
        owner_id: str,
        refresh_policy: RefreshPolicy | None,
        *,
        operation: str,
    ) -> None:
        policy = self._effective_refresh_policy(refresh_policy, operation=operation)
        if not self._should_refresh(segment, owner_id, policy):
            return

        if segment == "APP":
            self.refresh_app(owner_id)
        elif segment == "TABLES":
            self.refresh_tables(owner_id)
        elif segment == "FIELDS":
            self.refresh_fields(owner_id)
        else:
            self.refresh_reports(owner_id)

    def _should_refresh(
        self,
        segment: Literal["APP", "TABLES", "FIELDS", "REPORTS"],
        owner_id: str,
        refresh_policy: RefreshPolicy,
    ) -> bool:
        if refresh_policy == "always":
            return True
        if refresh_policy == "never":
            return False

        fetched_at = self._connection.execute(
            """
            SELECT fetched_at
            FROM schema_segments
            WHERE segment = ? AND owner_id = ?;
            """,
            (segment, owner_id),
        ).fetchone()

        if fetched_at is None:
            return True
        if refresh_policy == "missing":
            return False

        age = time.time() - float(fetched_at[0])
        return age >= self._stale_after_seconds

    def _remove_tables(self, cursor: sqlite3.Cursor, table_ids: set[str]) -> None:
        if not table_ids:
            return
        for table_id in table_ids:
            cursor.execute("DELETE FROM fields WHERE table_id = ?;", (table_id,))
            cursor.execute("DELETE FROM reports WHERE table_id = ?;", (table_id,))
            cursor.execute("DELETE FROM tables WHERE id = ?;", (table_id,))
            cursor.execute(
                "DELETE FROM schema_segments WHERE owner_id = ? AND segment IN (?, ?);",
                (table_id, "FIELDS", "REPORTS"),
            )

    @staticmethod
    def _serialize_payload(payload: Dict[str, Any]) -> str:
        return json.dumps(payload)

    @staticmethod
    def _normalize_level(
        level: str,
        *,
        operation: str,
    ) -> Literal["APP", "TABLE", "FIELD", "REPORT"]:
        normalized_level = level.upper()
        if normalized_level not in {"APP", "TABLE", "FIELD", "REPORT"}:
            raise QuickbaseValidationError(
                format_error_message(
                    "Schema level must be one of APP, TABLE, FIELD, or REPORT.",
                    operation=operation,
                    level=level,
                )
            )
        return cast(Literal["APP", "TABLE", "FIELD", "REPORT"], normalized_level)

    @staticmethod
    def _normalize_path(path: str | Path) -> str | Path:
        if isinstance(path, Path):
            return path
        if isinstance(path, str):
            return path if path == ":memory:" else Path(path)
        raise QuickbaseConfigurationError(
            format_error_message(
                "SchemaCache.path must be a string or Path.",
                operation="SchemaCache.__init__",
                path_type=type(path).__name__,
            )
        )

    @staticmethod
    def _normalize_refresh_policy(
        refresh_policy: RefreshPolicy,
        *,
        operation: str,
    ) -> RefreshPolicy:
        normalized_policy = str(refresh_policy).lower()
        if normalized_policy not in _REFRESH_POLICIES:
            raise QuickbaseConfigurationError(
                format_error_message(
                    "Invalid schema refresh policy.",
                    operation=operation,
                    refresh_policy=refresh_policy,
                    valid_refresh_policies=sorted(_REFRESH_POLICIES),
                )
            )
        return cast(RefreshPolicy, normalized_policy)

    @staticmethod
    def _normalize_stale_after_seconds(stale_after_seconds: float) -> float:
        if (
            isinstance(stale_after_seconds, bool)
            or not isinstance(stale_after_seconds, (int, float))
            or float(stale_after_seconds) < 0
        ):
            raise QuickbaseConfigurationError(
                format_error_message(
                    "stale_after_seconds must be a non-negative number.",
                    operation="SchemaCache.__init__",
                    stale_after_seconds=stale_after_seconds,
                )
            )
        return float(stale_after_seconds)

    def _effective_refresh_policy(
        self,
        refresh_policy: RefreshPolicy | None,
        *,
        operation: str,
    ) -> RefreshPolicy:
        if refresh_policy is None:
            return self._default_refresh_policy
        return self._normalize_refresh_policy(refresh_policy, operation=operation)

    @staticmethod
    def _require_identifier(value: Any, *, operation: str, key: str) -> str:
        if value is None:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase schema metadata is missing an identifier.",
                    operation=operation,
                    missing_key=key,
                )
            )
        return str(value)

    @staticmethod
    def _require_name(
        payload: Dict[str, Any],
        *,
        operation: str,
        key: str,
        preferred_key: str = "name",
    ) -> str:
        value = payload.get(preferred_key)
        if value is None and preferred_key != "label":
            value = payload.get("label")
        if value is None:
            raise QuickbaseSchemaError(
                format_error_message(
                    "Quickbase schema metadata is missing a name.",
                    operation=operation,
                    missing_key=key,
                )
            )
        return str(value)

    @staticmethod
    def _require_parent_id(
        parent_id: str | None,
        *,
        level: str,
        operation: str,
        **details: Any,
    ) -> str:
        if parent_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent id is required for this schema lookup.",
                    operation=operation,
                    level=level,
                    **details,
                )
            )
        return str(parent_id)
