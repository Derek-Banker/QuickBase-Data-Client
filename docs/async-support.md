# Async Support

Async support is available, but it is intentionally smaller than the sync surface.

## Preferred Names

- preferred async client: `AsyncQuickBaseClient`
- compatibility or explicit async path: `AsyncQuickBaseAPI`

## Supported Async Operations

Current maintained async table operations:

- `query_records(...)`
- `upsert_records(...)`
- `run_report(...)`
- `upload_files(...)`

## Not Yet Mirrored From Sync

These remain sync-only in the maintained Phase 11 surface:

- `run_formula(...)`
- `download_file(...)`
- `delete_file(...)`
- `query_all(...)`
- `iter_query_pages(...)`
- `iter_report_pages(...)`

## Basic Example

```python
import asyncio

from quickbase_sdk import AsyncQuickBaseClient, Auth


async def main() -> None:
    async with AsyncQuickBaseClient(
        Auth("example.quickbase.com", "qb-user-token")
    ) as client:
        table = client.table(id="bq123456")

        await table.upsert_records(
            [{"6": {"value": "INV-1001"}}]
        )
        response = await table.query_records("{3.GT.0}", select=[3, 6])
        print(len(response.data))


asyncio.run(main())
```

## Notes

- The async client is a separate implementation, not hidden branching inside the sync client.
- `AsyncApp.table(...)` is preferred.
- `AsyncApp.Table(...)` still works, but it is deprecated.
- `SchemaCache` can still be attached to the async client when you need schema-assisted name resolution.
