# Quickstart

Use IDs directly unless you specifically need schema-assisted lookup.

## Authenticate And Get A Table

```python
from quickbase_sdk import Auth, QuickBaseClient

client = QuickBaseClient(Auth("example.quickbase.com", "qb-user-token"))
orders = client.table(id="bq123456")
```

You can also start from an app:

```python
app = client.app(id="bp123456")
orders = app.table(id="bq123456")
```

## Query Records

```python
response = orders.query_records(
    "{3.GT.0}",
    select=[3, 6, 7],
)

for row in response.data:
    print(row["3"]["value"], row["6"]["value"])
```

`response.metadata` exposes the metadata block returned by Quickbase, and `response.raw` keeps the decoded payload.

## Upsert Records

```python
response = orders.upsert_records(
    [
        {"6": {"value": "INV-1001"}, "7": {"value": 125.0}},
        {"6": {"value": "INV-1002"}, "7": {"value": 210.5}},
    ],
    fields_to_return=[3, 6, 7],
)
```

If you already have a large `rows` list, batching can be capped explicitly:

```python
response = orders.upsert_records(
    rows,
    max_batch_record_count=500,
    max_request_size_kb=10_000,
)
```

## Reports And Formulas

`run_report(...)` accepts a raw report id, so schema lookup is optional:

```python
report = orders.run_report(13)
formula = orders.run_formula("ToText([Record ID#])")
```

`run_formula(...)` is currently sync-only.

## Pagination Helpers

The sync client exposes higher-level helpers for large result sets:

```python
all_rows = orders.query_all("{3.GT.0}", page_size=500)

for page in orders.iter_query_pages("{3.GT.0}", page_size=500):
    print(page.metadata["skip"], len(page.data))

for page in orders.iter_report_pages(13, page_size=500):
    print(page.metadata["skip"], len(page.data))
```

Use `query_records(..., options=...)` and `run_report(..., params=...)` if you want low-level paging control.

## DataFrames From Query/Report Responses

```python
frame = orders.query_records("{3.GT.0}", select=[3, 6, 7]).dataframe("NAME")
```

Supported headers for `.dataframe(...)` are:

- `"IDENTIFIER"`
- `"ID"`
- `"NAME"`

See [DataFrame Workflows](dataframe-workflows.md) for DataFrame upsert rules.
