# Development

## Local Setup

Use Python `3.10+`.

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Or, on Unix/macOS:

```bash
python -m pip install -e ".[dev]"
```

Do not commit `.env`, real Quickbase user tokens, generated schema databases, build
artifacts, or cache directories.

## Quality Checks

Run the narrowest relevant test while iterating, then run the full local gate before a
release or broad change:

```bash
python -m pytest tests -m "not integration"
python -m ruff check src tests examples
python -m mypy src tests examples
python -m pytest tests --cov=quickbase_data_client --cov-report=term-missing -m "not integration"
```

CI runs tests on Python `3.10` and `3.13`. The configured branch coverage floor is `72%`.

## Integration Tests

Integration tests are disabled unless explicitly enabled:

```powershell
$env:QUICKBASE_RUN_INTEGRATION_TESTS = "1"
$env:QUICKBASE_REALM = "example.quickbase.com"
$env:QUICKBASE_USER_TOKEN = "qb-user-token"
$env:QUICKBASE_TEST_APP_ID = "bp123456"
$env:QUICKBASE_TEST_TABLE_ID = "bq123456"
```

Optional query controls:

```powershell
$env:QUICKBASE_TEST_QUERY = "{3.GT.0}"
$env:QUICKBASE_TEST_SELECT = "3,6,7"
```

Only run integration tests against a tenant and table intended for testing.

## Legacy And Generated Areas

`schema_manager.py`, `code_generation/`, and `typed_structs/` are compatibility-heavy or
generated-support areas. They remain excluded from strict lint/type coverage for now.
Changes there should be narrow, tested, and documented when they affect public behavior.

## Release Build

```bash
python -m build --sdist --wheel
```

Before publishing, inspect the source distribution and confirm it includes docs and
examples while excluding local `models/` schema cache artifacts.
