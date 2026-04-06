#!/usr/bin/env python3
"""
Module: generate_sql.py

Converts a Quickbase JSON schema file into a simplified SQLite database:
- apps(id, name, other)
- app_variables(app_id, name, value)
- tables(id, app_id, name, other)
- fields(id, table_id, label, fieldType, other)
- reports(id, table_id, name, type, other)

Supports:
- CLI entry point
- Programmatic sync(json_path, sqlite_path, force=False)
- JSON hash-based versioning (metadata.schema_hash)
- Path validation
- --force option to always rebuild
"""
import os
import sys
import sqlite3
import json
import hashlib
import shutil
import argparse
from pathlib import Path

from quickbase_data_client.config import DEFAULT_SCHEMA_PATH_JSON, DEFAULT_SCHEMA_PATH_SQLITE

SCHEMA_HASH_KEY = 'schema_hash'


def compute_hash(path: Path) -> str:
    """Compute SHA-256 hash of a file's contents."""
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def _validate_path(path: Path, must_exist: bool = True) -> Path | None:  # type: ignore
    """Ensure path is a Path and, if must_exist, that it exists."""
    try:
        p = Path(path)
    except Exception:
        print(f"ERROR: Invalid path: {path}", file=sys.stderr)
        sys.exit(1)
    if must_exist and not p.exists():
        print(f"ERROR: Path not found: {p}", file=sys.stderr)
        sys.exit(1)
    return p


def convert(json_path: Path, sqlite_path: Path) -> None:
    """Always rebuild the SQLite DB from the JSON schema."""
    temp = sqlite_path.with_suffix(sqlite_path.suffix + '.tmp')

    # load JSON
    payload = json.loads(json_path.read_text(encoding='utf-8'))
    schema = payload.get('Schema', {})

    # compute hash
    schema_hash = compute_hash(json_path)

    # open DB
    conn = sqlite3.connect(str(temp))
    cur = conn.cursor()

    # metadata
    cur.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);")
    cur.execute(
        "INSERT OR REPLACE INTO metadata(key,value) VALUES (?,?);",
        (SCHEMA_HASH_KEY, schema_hash)
    )

    # apps
    cur.execute("CREATE TABLE IF NOT EXISTS apps(id TEXT PRIMARY KEY, name TEXT NOT NULL, other JSON);")
    cur.execute(
        "CREATE TABLE IF NOT EXISTS app_variables("
        "app_id TEXT, name TEXT, value TEXT, PRIMARY KEY(app_id,name)"
        ");"
    )

    # tables
    cur.execute("CREATE TABLE IF NOT EXISTS tables("
                "id TEXT PRIMARY KEY, app_id TEXT, name TEXT NOT NULL, other JSON"
                ");")

    # fields (now composite PK: table_id + id)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS fields("
        "table_id TEXT NOT NULL,"
        "id       TEXT NOT NULL,"
        "label    TEXT NOT NULL,"
        "fieldType TEXT,"
        "other    JSON,"
        "PRIMARY KEY(table_id, id),"
        "UNIQUE(table_id, label)"
        ");"
    )

    # reports (composite PK: table_id + id)
    cur.execute(
        "CREATE TABLE IF NOT EXISTS reports("
        "table_id TEXT NOT NULL,"
        "id       TEXT NOT NULL,"
        "name     TEXT NOT NULL,"
        "type     TEXT,"
        "other    JSON,"
        "PRIMARY KEY(table_id, id)"
        ");"
    )

    # populate
    for raw_app_key, app in schema.items():
        # apps
        app_id   = app['id']
        app_name = app['name']
        app_other = {
            k: v for k, v in app.items()
            if k not in ('id', 'name', 'variables', 'Tables')
        }
        cur.execute(
            "INSERT OR REPLACE INTO apps(id,name,other) VALUES (?,?,?);",
            (app_id, app_name, json.dumps(app_other))
        )

        # variables
        for var in app.get('variables', []):
            cur.execute(
                "INSERT OR REPLACE INTO app_variables(app_id,name,value) VALUES (?,?,?);",
                (app_id, var.get('name'), var.get('value'))
            )

        # tables
        for tbl in app.get('Tables', {}).values():
            tbl_id    = tbl['id']
            tbl_name  = tbl['name']
            tbl_other = {
                k: v for k, v in tbl.items()
                if k not in ('id', 'name', 'Fields', 'Reports')
            }
            cur.execute(
                "INSERT OR REPLACE INTO tables(id,app_id,name,other) VALUES (?,?,?,?);",
                (tbl_id, app_id, tbl_name, json.dumps(tbl_other))
            )

            # fields
            for fld in tbl.get('Fields', []):
                fld_id    = str(fld['id'])
                label     = fld['label']
                ftype     = fld.get('fieldType')
                fld_other = {
                    k: v for k, v in fld.items()
                    if k not in ('id', 'label', 'fieldType')
                }
                cur.execute(
                    "INSERT OR REPLACE INTO fields(table_id,id,label,fieldType,other) VALUES (?,?,?,?,?);",
                    (tbl_id, fld_id, label, ftype, json.dumps(fld_other))
                )

            # reports
            for rpt in tbl.get('Reports', []):
                rpt_id    = str(rpt['id'])
                rpt_name  = rpt['name']
                rpt_type  = rpt.get('type')
                rpt_other = {
                    k: v for k, v in rpt.items()
                    if k not in ('id', 'name', 'type')
                }
                cur.execute(
                    "INSERT OR REPLACE INTO reports(table_id,id,name,type,other) VALUES (?,?,?,?,?);",
                    (tbl_id, rpt_id, rpt_name, rpt_type, json.dumps(rpt_other))
                )

    conn.commit()
    conn.close()

    # atomic replace
    shutil.move(str(temp), str(sqlite_path))



def sync(json_path: str = DEFAULT_SCHEMA_PATH_JSON, sqlite_path: str = DEFAULT_SCHEMA_PATH_SQLITE, force: bool = False) -> bool:
    """
    Ensure sqlite reflects JSON. Returns True if rebuilt.
    """
    jpath = _validate_path(Path(json_path), must_exist=True)
    spath = Path(sqlite_path)
    # existing hash
    old_hash = None
    if not force and spath.exists():
        try:
            con = sqlite3.connect(str(spath))
            cur = con.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);")
            cur.execute("SELECT value FROM metadata WHERE key = ?;", (SCHEMA_HASH_KEY,))
            row = cur.fetchone()
            old_hash = row[0] if row else None
            con.close()
        except sqlite3.DatabaseError:
            old_hash = None
    new_hash = compute_hash(jpath)
    if force or old_hash != new_hash:
        convert(jpath, spath)
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Sync simplified Quickbase schema to SQLite.")
    parser.add_argument('json',   help='Path to Quickbase JSON schema')
    parser.add_argument('sqlite', help='Target SQLite DB file')
    parser.add_argument('--force', action='store_true', help='Force rebuild')
    args = parser.parse_args()
    rebuilt = sync(args.json, args.sqlite, force=args.force)
    sys.exit(0 if not rebuilt else 1)


if __name__ == '__main__':
    main()
