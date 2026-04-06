# DataFrame Workflows

The maintained DataFrame support is explicit and IDs-first. It does not guess through ambiguous mappings.

Assume the examples below already have a table handle such as:

```python
from quickbase_sdk import Auth, QuickBaseClient

client = QuickBaseClient(Auth("example.quickbase.com", "qb-user-token"))
table = client.table(id="bq123456")
```

## Convert Query/Report Results To A DataFrame

```python
frame = table.query_records("{3.GT.0}", select=[3, 6, 7]).dataframe("NAME")
```

Header choices:

- `"IDENTIFIER"`: `Identifier` objects
- `"ID"`: string field ids
- `"NAME"`: field labels

## Upsert A DataFrame By Field ID

```python
import pandas as pd

frame = pd.DataFrame(
    [
        {"6": "Open", 7: 125.0},
        {"6": "Closed", 7: 0.0},
    ]
)

table.upsert_records(frame)
```

Accepted column forms without schema lookup:

- `Identifier("FIELD", id="...")`
- `int`
- digit-only `str`

## Upsert A DataFrame By Field Name

Field-name columns only work when the table has access to cached schema metadata.

```python
import pandas as pd
from pathlib import Path

from quickbase_sdk import Auth, QuickBaseClient, SchemaCache

cache = SchemaCache(path=Path(".cache/quickbase/schema.sqlite3"))
client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    schema_cache=cache,
)

table = client.table(id="bq123456")
frame = pd.DataFrame([{"Status": "Open", "Amount": "10.5"}])

table.upsert_records(frame)
```

When field types are known from cached schema metadata, outgoing values are sanitized using those field types. Numeric and date-like string values can be normalized during that path.

## Ambiguity Rules

The encoder raises instead of guessing when:

- a field-name column is used without cached schema metadata
- a field name does not exist in the cached table schema
- a field name is ambiguous across multiple fields
- two columns resolve to the same field id

One important rule: digit-only strings stay ID-based even if the schema contains a field label like `"6"`.

If you really mean the field name `"6"`, use an explicit `Identifier`:

```python
from quickbase_sdk import Identifier

frame = pd.DataFrame(
    [["Open"]],
    columns=[Identifier("FIELD", id="10", name="6", parent=table.identifier)],
)
```
