# Installation

## Requirements

- Python `3.10+`
- A Quickbase realm hostname such as `example.quickbase.com`
- A Quickbase user token

The current package includes `requests`, `pandas`, and `numpy` as direct dependencies. There is no separate DataFrame extra in the maintained Phase 11 surface.

## Install From PyPI

```bash
pip install quickbase-sdk
```

Import it as:

```python
from quickbase_sdk import Auth, QuickBaseClient
```

## Install For Local Development

```bash
pip install -e ".[dev]"
```

That installs the package plus the repo's quality-tooling dependencies.

## Minimal Setup

```python
from quickbase_sdk import Auth, QuickBaseClient

auth = Auth("example.quickbase.com", "qb-user-token")
client = QuickBaseClient(auth)
table = client.table(id="bq123456")
```

`Auth` expects the full realm hostname, not just the subdomain.

## Local Schema Cache Files

If you use `SchemaCache`, keep the cache database local-only. It may contain tenant-specific metadata.

- Default SQLite path: `models/QuickBase_Schema.sqlite3`
- Recommended for publishable projects: choose a local cache path outside files you intend to ship

Example:

```python
from pathlib import Path

from quickbase_sdk import Auth, QuickBaseClient, SchemaCache

cache = SchemaCache(path=Path(".cache/quickbase/schema.sqlite3"))
client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    schema_cache=cache,
)
```
