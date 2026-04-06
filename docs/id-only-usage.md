# ID-Only Usage

The maintained client is IDs-first. You do not need schema metadata for normal data operations when you already know app, table, field, and report ids.

## Direct Table Access

```python
from quickbase_sdk import Auth, QuickBaseClient

client = QuickBaseClient(Auth("example.quickbase.com", "qb-user-token"))
orders = client.table(id="bq123456")
```

This is the preferred path when you already know the table id.

## App-Scoped Table Access By ID

```python
app = client.app(id="bp123456")
orders = app.table(id="bq123456")
```

You only need the app object when that extra context is useful to your code.

## Run Reports By Raw Report ID

```python
report = orders.run_report(13)
```

That does not require `SchemaCache`.

## Explicit Field Identifiers

Use `Identifier` when you want a typed field reference without schema name lookup:

```python
from quickbase_sdk import Identifier

status_field = Identifier("FIELD", id="6", parent=orders.identifier)
```

`Identifier` only auto-resolves names, parents, and field types when a `SchemaCache` is attached. Without a cache, id-only identifiers stay id-only.

## DataFrame Columns Without Schema

DataFrame upserts work without schema metadata when the columns are already field ids:

```python
import pandas as pd

frame = pd.DataFrame(
    [
        {"6": "Open", 7: 125.0},
        {"6": "Closed", 7: 0.0},
    ]
)

orders.upsert_records(frame)
```

Supported ID-only DataFrame column forms:

- `Identifier("FIELD", id="...")`
- `int`
- digit-only `str`

Non-numeric field-name strings require cached schema metadata.
