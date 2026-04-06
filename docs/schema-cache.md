# Schema Cache Usage

`SchemaCache` is optional. Use it when you want name-based resolution for apps, tables, fields, or reports.

It is not a hidden global dependency. You attach it explicitly to a client.

## Create A Cache Safely

Schema cache files can contain tenant-specific metadata. Keep them local.

```python
from pathlib import Path

from quickbase_data_client import Auth, QuickBaseClient, SchemaCache

cache = SchemaCache(
    path=Path(".cache/quickbase/schema.sqlite3"),
    default_refresh_policy="missing",
    stale_after_seconds=3600,
)

client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    schema_cache=cache,
)
```

The default cache path is `models/QuickBase_Schema.sqlite3`. That is convenient for local use, but it should still be treated as generated local state.

## Refresh Policies

Supported refresh policies:

- `"never"`: use cached rows only; do not fetch
- `"missing"`: fetch only when a segment is absent
- `"stale"`: fetch when the segment is older than `stale_after_seconds`
- `"always"`: always refetch the segment

## Refresh Only What You Need

`SchemaCache` stores segmented metadata:

- app metadata by app id
- table lists by app id
- field lists by table id
- report lists by table id

You can refresh segments explicitly:

```python
cache.refresh_app("bp123456")
cache.refresh_tables("bp123456")
cache.refresh_fields("bq123456")
cache.refresh_reports("bq123456")
```

## Resolve Names To IDs

```python
app = client.app(id="bp123456")
orders = app.table(name="Orders")
status = orders.identifier.create_child(level="FIELD", name="Status")

print(orders.id)
print(status.id)
```

With the default `"missing"` policy, table/field/report lookups fetch only the missing segment they need.

## Important APP Lookup Caveat

APP name lookup is cache-only.

This means code like `client.app(name="Operations")` only works after APP metadata for that app has already been refreshed or resolved by id.

Example:

```python
cache.refresh_app("bp123456")
operations = client.app(name="Operations")
```

## Invalidate Cached Segments

```python
cache.invalidate_app("bp123456")
cache.invalidate_tables("bp123456")
cache.invalidate_fields("bq123456")
cache.invalidate_reports("bq123456")
```

## Close The Cache

`SchemaCache` owns a SQLite connection. Close it when you are done with a short-lived cache instance:

```python
cache.close()
```
