"""
Schema Manager: load and query a simplified Quickbase JSON/SQLite schema.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from quickbase_sdk.code_generation.generate_sql import sync
from quickbase_sdk.config import DEFAULT_SCHEMA_PATH_JSON, DEFAULT_SCHEMA_PATH_SQLITE
from quickbase_sdk.exceptions import (
    QuickbaseConfigurationError,
    QuickbaseNotFoundError,
    QuickbaseSchemaError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_sdk.identifier import Identifier

database_loaded: bool = False
loaded_database: sqlite3.Connection | None = None
validated_path_JSON: Path | None = None
validated_path_SQL: Path | None = None
logger = logging.getLogger(__name__)


def _get_cursor(operation: str) -> sqlite3.Cursor:
    if not database_loaded or loaded_database is None:
        raise QuickbaseSchemaError(
            format_error_message(
                "Schema database is not loaded.",
                operation=operation,
                json_path=str(validated_path_JSON) if validated_path_JSON else DEFAULT_SCHEMA_PATH_JSON,
                sqlite_path=str(validated_path_SQL) if validated_path_SQL else DEFAULT_SCHEMA_PATH_SQLITE,
            )
        )
    return loaded_database.cursor()


def load_schema_database(
    json_path: str | Path = DEFAULT_SCHEMA_PATH_JSON,
    sqlite_path: str | Path = DEFAULT_SCHEMA_PATH_SQLITE,
    force: bool = False,
) -> None:
    """
    Validate schema/DB paths, sync simplified DB from JSON, and load into memory.
    """
    global loaded_database, validated_path_JSON, validated_path_SQL, database_loaded

    try:
        json_p = Path(json_path)
    except Exception as exc:
        raise QuickbaseConfigurationError(
            format_error_message(
                "Invalid JSON schema path.",
                operation="schema_manager.load_schema_database",
                json_path=json_path,
                cause=exc,
            )
        ) from exc
    if not json_p.exists() or not json_p.is_file():
        raise QuickbaseNotFoundError(
            format_error_message(
                "JSON schema file was not found.",
                operation="schema_manager.load_schema_database",
                json_path=str(json_p),
            )
        )
    validated_path_JSON = json_p

    try:
        sql_p = Path(sqlite_path)
    except Exception as exc:
        raise QuickbaseConfigurationError(
            format_error_message(
                "Invalid SQLite schema path.",
                operation="schema_manager.load_schema_database",
                sqlite_path=sqlite_path,
                cause=exc,
            )
        ) from exc
    validated_path_SQL = sql_p

    try:
        rebuilt = sync(str(validated_path_JSON), str(validated_path_SQL), force=force)
    except SystemExit as exc:
        raise QuickbaseSchemaError(
            format_error_message(
                "Schema sync aborted unexpectedly.",
                operation="schema_manager.load_schema_database",
                json_path=str(validated_path_JSON),
                sqlite_path=str(validated_path_SQL),
                cause=exc,
            )
        ) from exc
    except Exception as exc:
        raise QuickbaseSchemaError(
            format_error_message(
                "Failed to synchronize the SQLite schema cache.",
                operation="schema_manager.load_schema_database",
                json_path=str(validated_path_JSON),
                sqlite_path=str(validated_path_SQL),
                force=force,
                cause=exc,
            )
        ) from exc

    if rebuilt:
        logger.info("SQLite schema regenerated from JSON.")
    else:
        logger.info("SQLite schema up-to-date; no rebuild.")

    loaded_database = _load_database(validated_path_SQL)
    database_loaded = True


def _load_database(db_path: Path) -> sqlite3.Connection:
    """
    Load disk-based SQLite DB into an in-memory connection via backup.
    """
    try:
        disk = sqlite3.connect(str(db_path))
        mem = sqlite3.connect(":memory:")
        disk.backup(mem)
        disk.close()
    except sqlite3.Error as exc:
        raise QuickbaseSchemaError(
            format_error_message(
                "Failed to load SQLite schema cache into memory.",
                operation="schema_manager._load_database",
                sqlite_path=str(db_path),
                cause=exc,
            )
        ) from exc
    return mem


def get_id(
    level: Literal["APP", "TABLE", "FIELD", "REPORT"],
    name: str,
    parent_id: Optional[str] = None,
) -> str:
    """
    Look up the primary key (id) for the given entity-level by its name/label.
    """
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_id")

    if lvl == "APP":
        cur.execute("SELECT id FROM apps WHERE name = ?;", (name,))
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find APP by name.",
                    operation="schema_manager.get_id",
                    level=lvl,
                    name=name,
                )
            )
        return row[0]

    if not parent_id:
        raise QuickbaseValidationError(
            format_error_message(
                "Parent id is required for non-APP schema name lookups.",
                operation="schema_manager.get_id",
                level=lvl,
                name=name,
            )
        )

    if lvl == "TABLE":
        cur.execute(
            "SELECT id FROM tables WHERE app_id = ? AND name = ?;",
            (parent_id, name),
        )
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find TABLE by name.",
                    operation="schema_manager.get_id",
                    level=lvl,
                    name=name,
                    parent_id=parent_id,
                )
            )
        return row[0]

    if lvl == "FIELD":
        cur.execute(
            "SELECT id FROM fields WHERE table_id = ? AND label = ?;",
            (parent_id, name),
        )
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find FIELD by label.",
                    operation="schema_manager.get_id",
                    level=lvl,
                    name=name,
                    parent_id=parent_id,
                )
            )
        return row[0]

    if lvl == "REPORT":
        cur.execute(
            "SELECT id FROM reports WHERE table_id = ? AND name = ?;",
            (parent_id, name),
        )
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find REPORT by name.",
                    operation="schema_manager.get_id",
                    level=lvl,
                    name=name,
                    parent_id=parent_id,
                )
            )
        return row[0]

    raise QuickbaseValidationError(
        format_error_message(
            "Invalid schema level for get_id.",
            operation="schema_manager.get_id",
            level=lvl,
        )
    )


def get_name(
    level: Literal["APP", "TABLE", "FIELD", "REPORT"],
    id: str,
    parent_id: Optional[str] = None,
) -> str:
    """
    Look up the human name/label for the given entity-level by its id.
    """
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_name")

    if lvl == "APP":
        cur.execute("SELECT name FROM apps WHERE id = ?;", (id,))
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find APP by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                )
            )
        return row[0]

    if lvl == "TABLE":
        cur.execute("SELECT name FROM tables WHERE id = ?;", (id,))
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find TABLE by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                )
            )
        return row[0]

    if lvl == "FIELD":
        if parent_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for FIELD lookups by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                )
            )
        cur.execute(
            "SELECT label FROM fields WHERE table_id = ? AND id = ?;",
            (parent_id, id),
        )
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find FIELD by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                    parent_id=parent_id,
                )
            )
        return row[0]

    if lvl == "REPORT":
        if parent_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for REPORT lookups by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                )
            )
        cur.execute(
            "SELECT name FROM reports WHERE table_id = ? AND id = ?;",
            (parent_id, id),
        )
        row = cur.fetchone()
        if not row:
            raise QuickbaseNotFoundError(
                format_error_message(
                    "Schema lookup could not find REPORT by id.",
                    operation="schema_manager.get_name",
                    level=lvl,
                    identifier_id=id,
                    parent_id=parent_id,
                )
            )
        return row[0]

    raise QuickbaseValidationError(
        format_error_message(
            "Invalid schema level for get_name.",
            operation="schema_manager.get_name",
            level=lvl,
        )
    )


def get_parent(
    level: Literal["APP", "TABLE", "FIELD", "REPORT"],
    id: str,
) -> Optional[str]:
    """
    Return the parent ID for the given entity; APP has no parent.
    For FIELD and REPORT, only return if the id is unique within the DB.
    """
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_parent")

    if lvl == "APP":
        return None
    if lvl == "TABLE":
        cur.execute("SELECT app_id FROM tables WHERE id = ?;", (id,))
        row = cur.fetchone()
        return row[0] if row else None

    if lvl == "FIELD":
        cur.execute("SELECT table_id FROM fields WHERE id = ?;", (id,))
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None

    if lvl == "REPORT":
        cur.execute("SELECT table_id FROM reports WHERE id = ?;", (id,))
        rows = cur.fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None

    raise QuickbaseValidationError(
        format_error_message(
            "Invalid schema level for get_parent.",
            operation="schema_manager.get_parent",
            level=level,
        )
    )


def get_children(
    level: Literal["APP", "TABLE", "FIELD", "REPORT"],
    id: str,
    parent_id: Optional[str] = None,
) -> List[Identifier]:
    """
    Return list of child Identifiers: APP->TABLEs, TABLE->FIELDs+REPORTs.
    """
    children: List[Identifier] = []
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_children")

    if lvl == "APP":
        cur.execute("SELECT id FROM tables WHERE app_id = ?;", (id,))
        app_ident = Identifier("APP", id=id)
        for (tbl_id,) in cur.fetchall():
            children.append(Identifier("TABLE", id=tbl_id, parent=app_ident))
        return children

    if lvl == "TABLE":
        if parent_id is None:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent app id is required to enumerate TABLE children.",
                    operation="schema_manager.get_children",
                    level=lvl,
                    identifier_id=id,
                )
            )
        tbl_ident = Identifier("TABLE", id=id, parent=Identifier("APP", id=parent_id))
        cur.execute("SELECT id FROM fields WHERE table_id = ?;", (id,))
        for (fld_id,) in cur.fetchall():
            children.append(Identifier("FIELD", id=fld_id, parent=tbl_ident))
        cur.execute("SELECT id FROM reports WHERE table_id = ?;", (id,))
        for (rpt_id,) in cur.fetchall():
            children.append(Identifier("REPORT", id=rpt_id, parent=tbl_ident))
        return children

    raise QuickbaseValidationError(
        format_error_message(
            "Only APP and TABLE levels support child enumeration.",
            operation="schema_manager.get_children",
            level=lvl,
            identifier_id=id,
        )
    )


def generate_field_identities(table_identifier: Identifier) -> List[Identifier]:
    if table_identifier.level != "TABLE":
        raise QuickbaseValidationError(
            format_error_message(
                "generate_field_identities requires a TABLE identifier.",
                operation="schema_manager.generate_field_identities",
                identifier_level=table_identifier.level,
                object_ref=repr(table_identifier),
            )
        )

    field_identities: List[Identifier] = []
    cur = _get_cursor("schema_manager.generate_field_identities")
    tbl_id = table_identifier.id

    cur.execute("SELECT id, label FROM fields WHERE table_id = ?;", (tbl_id,))
    for field_id, field_label in cur.fetchall():
        child_ident = table_identifier.create_child(
            level="FIELD",
            id=field_id,
            name=field_label,
        )
        field_identities.append(child_ident)

    return field_identities


def get_properties(
    level: Literal["APP", "TABLE", "FIELD", "REPORT"],
    id_or_name: str,
    parent_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Return the raw JSON blob for the given entity, as stored in the `other` column.
    """
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_properties")

    if lvl == "APP":
        cur.execute("SELECT other FROM apps WHERE id = ?;", (id_or_name,))
    elif lvl == "TABLE":
        if not parent_id:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent app id is required for TABLE properties.",
                    operation="schema_manager.get_properties",
                    level=lvl,
                    identifier=id_or_name,
                )
            )
        cur.execute(
            "SELECT other FROM tables WHERE id = ? AND app_id = ?;",
            (id_or_name, parent_id),
        )
    elif lvl == "FIELD":
        if not parent_id:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for FIELD properties.",
                    operation="schema_manager.get_properties",
                    level=lvl,
                    identifier=id_or_name,
                )
            )
        cur.execute(
            "SELECT other FROM fields WHERE id = ? AND table_id = ?;",
            (id_or_name, parent_id),
        )
    elif lvl == "REPORT":
        if not parent_id:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for REPORT properties.",
                    operation="schema_manager.get_properties",
                    level=lvl,
                    identifier=id_or_name,
                )
            )
        cur.execute(
            "SELECT other FROM reports WHERE id = ? AND table_id = ?;",
            (id_or_name, parent_id),
        )
    else:
        raise QuickbaseValidationError(
            format_error_message(
                "Invalid schema level for get_properties.",
                operation="schema_manager.get_properties",
                level=level,
            )
        )

    row = cur.fetchone()
    if not row or row[0] is None:
        return {}

    try:
        return json.loads(row[0])
    except json.JSONDecodeError as exc:
        raise QuickbaseSchemaError(
            format_error_message(
                "Schema cache contains invalid JSON metadata.",
                operation="schema_manager.get_properties",
                level=lvl,
                identifier=id_or_name,
                parent_id=parent_id,
                cause=exc,
            )
        ) from exc


def get_type(
    level: Literal["FIELD", "REPORT"],
    id: str,
    parent_id: str | None,
) -> str:
    """
    Return the 'fieldType' for a FIELD or the 'type' for a REPORT.
    """
    lvl = level.upper()
    cur = _get_cursor("schema_manager.get_type")

    if lvl == "FIELD":
        if not parent_id:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for FIELD type lookup.",
                    operation="schema_manager.get_type",
                    level=lvl,
                    identifier_id=id,
                )
            )
        cur.execute(
            "SELECT fieldType FROM fields WHERE id = ? AND table_id = ?;",
            (id, parent_id),
        )
    elif lvl == "REPORT":
        if not parent_id:
            raise QuickbaseValidationError(
                format_error_message(
                    "Parent table id is required for REPORT type lookup.",
                    operation="schema_manager.get_type",
                    level=lvl,
                    identifier_id=id,
                )
            )
        cur.execute(
            "SELECT type FROM reports WHERE id = ? AND table_id = ?;",
            (id, parent_id),
        )
    else:
        raise QuickbaseValidationError(
            format_error_message(
                "Invalid schema level for get_type.",
                operation="schema_manager.get_type",
                level=level,
            )
        )

    row = cur.fetchone()
    if not row or row[0] is None:
        raise QuickbaseNotFoundError(
            format_error_message(
                "Schema lookup could not find object type.",
                operation="schema_manager.get_type",
                level=lvl,
                identifier_id=id,
                parent_id=parent_id,
            )
        )

    return row[0]


def main():
    if not database_loaded:
        load_schema_database()
        logger.warning("Schema manager loaded the default schema cache automatically.")
