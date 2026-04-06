# Migration Notes

This repo keeps compatibility shims where they are still justified, but the preferred surface is narrower and more explicit than older package shapes.

## Preferred Public Names

- use `QuickBaseClient` for sync code
- keep `QuickBaseAPI` only as the compatibility or explicit base-client path
- use `AsyncQuickBaseClient` for async code
- keep `AsyncQuickBaseAPI` only as the compatibility or explicit async path

## App/Table Entry Points

Preferred:

```python
app = client.app(id="bp123456")
table = app.table(id="bq123456")
```

Still supported, but deprecated:

```python
table = app.Table(id="bq123456")
```

The same rule applies to `AsyncApp.table(...)` versus `AsyncApp.Table(...)`.

## Schema Access Is Now Explicit

Do not rely on hidden module-global schema loading.

Preferred:

```python
from pathlib import Path

from quickbase_sdk import Auth, QuickBaseClient, SchemaCache

cache = SchemaCache(path=Path(".cache/quickbase/schema.sqlite3"))
client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    schema_cache=cache,
)
```

If you stay with raw ids, you do not need `SchemaCache`.

## Errors Are Exceptions

Code should catch package exceptions such as:

- `QuickbaseTransportError`
- `QuickbaseHTTPError`
- `QuickbaseAuthError`
- `QuickbaseRateLimitError`
- `QuickbaseSchemaError`
- `QuickbasePayloadError`

Do not assume failures will be signaled only through logs or ad hoc status wrappers.

## Compatibility Imports

These compatibility paths still exist, but they are not the preferred public surface:

- `quickbase_sdk.QuickBaseHandler`
- `quickbase_sdk.QuickBaseRequest`
- `quickbase_sdk.ResponseFactory`

Preferred imports:

```python
from quickbase_sdk.tools.quickbase_log_handler import QuickBaseHandler
```

Internal parser helpers should be imported from their actual modules only when you knowingly depend on a compatibility path.

## Async Scope Changed Less Than Sync

If you are migrating sync code to async, do not assume feature parity. The maintained async surface is limited to query, upsert, report, and file upload.

## Package Identity In This Repo

The install name remains `quickbase-sdk` and the import path remains `quickbase_sdk` in this repo state.
