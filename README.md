# QuickBase-Data-Client

`QuickBase-Data-Client` is a focused Python client for Quickbase data access.

It is built for record queries, upserts, reports, formulas, file attachments, optional schema-assisted lookup, and pandas-based workflows. It is not a full Quickbase administration SDK, and it does not try to wrap every Quickbase endpoint.

## Supported Surface

- Sync client: `QuickBaseClient`
- Compatibility sync path: `QuickBaseAPI`
- Async client: `AsyncQuickBaseClient`
- Compatibility/explicit async path: `AsyncQuickBaseAPI`
- App/table helpers: `App`, `Table`, `AsyncApp`, `AsyncTable`
- Explicit identifiers: `Identifier`
- Optional schema lookup: `SchemaCache`
- Request tuning: `RequestConfig`
- File uploads/downloads: `FilePayload`

Current maintained capabilities:

- ID-first record query and upsert workflows
- report execution and sync formula execution
- high-level query/report pagination helpers in the sync client
- file upload, download, and delete operations in the sync client
- async core data operations: query, upsert, report, and file upload
- DataFrame conversion and DataFrame-to-upsert workflows
- configurable retries, timeouts, and request/file size limits
- package-level exceptions instead of status-wrapper error signaling

## Installation

```bash
pip install quickbase-data-client
```

The published package name is `quickbase-data-client`. The import path is `quickbase_data_client`.

Python `3.10+` is required. `pandas` and `numpy` are direct dependencies in the current package shape.

## Quickstart

Use IDs directly unless you specifically need schema-assisted name resolution.

```python
from quickbase_data_client import Auth, QuickBaseClient

auth = Auth("example.quickbase.com", "qb-user-token")
client = QuickBaseClient(auth)

orders = client.table(id="bq123456")

query_response = orders.query_records(
    "{3.GT.0}",
    select=[3, 6, 7],
)

upsert_response = orders.upsert_records(
    [
        {"6": {"value": "INV-1001"}, "7": {"value": 125.0}},
        {"6": {"value": "INV-1002"}, "7": {"value": 210.5}},
    ]
)

print(query_response.status_code)
print(len(query_response.data))
print(upsert_response.metadata)
```

`QuickBaseResponse` wrappers expose `status_code`, `status_text`, `metadata`, `fields`, `data`, `raw`, and `parsed`. Query/report responses can also be converted to pandas with `.dataframe(...)`.

## Docs

- [Installation](docs/installation.md)
- [Quickstart](docs/quickstart.md)
- [ID-Only Usage](docs/id-only-usage.md)
- [Schema Cache Usage](docs/schema-cache.md)
- [DataFrame Workflows](docs/dataframe-workflows.md)
- [File Handling](docs/file-handling.md)
- [Exceptions](docs/exceptions.md)
- [Retries and Configuration](docs/retries-and-configuration.md)
- [Async Support](docs/async-support.md)
- [Migration Notes](docs/migration-notes.md)

## Notes On Scope

This package is intentionally narrow.

- It supports Quickbase data operations, not structural app/table administration.
- IDs are the primary contract.
- `SchemaCache` is optional and explicit.
- Async support is intentionally smaller than the sync surface.

## Compatibility Notes

- `QuickBaseClient` is the preferred sync client name.
- `QuickBaseAPI` still works as the compatibility path.
- `AsyncQuickBaseClient` is the preferred async client name.
- `AsyncQuickBaseAPI` still works as the compatibility/explicit async path.
- `App.table(...)` and `AsyncApp.table(...)` are preferred.
- `App.Table(...)` and `AsyncApp.Table(...)` still work, but they are deprecated.
- `QuickBaseHandler` should be imported from `quickbase_data_client.tools.quickbase_log_handler`.
- Package-root compatibility exports for `QuickBaseRequest` and `ResponseFactory` are deprecated.

## Schema Data Safety

Generated schema caches can contain tenant-specific metadata. Treat them as local runtime artifacts, not source files.

- The default SQLite cache path is `models/QuickBase_Schema.sqlite3`.
- Do not publish `models/` contents.
- Do not copy tenant schema payloads into docs or examples.

Phase 11 adds an explicit source-distribution guard so local `models/` cache files are not bundled by accident.

## License

Apache License 2.0. See [LICENSE](LICENSE).
