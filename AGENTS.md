# Repository Instructions

## Scope

These instructions apply to the entire repository.

This is `quickbase-data-client`, a Python package for Quickbase data access. Keep the
project focused on record-level data workflows: querying, upserting, reports, formulas,
file attachments, optional schema-assisted lookup, pandas helpers, retries, and response
parsing. Do not turn this package into a full Quickbase administration or structure SDK.
Structural/app-admin work belongs in a separate package such as
`Derek-Banker/QuickBase-Structure-Client` unless the user explicitly asks to share or
factor code between the projects.

## Working Approach

- Read the relevant implementation and tests before changing behavior.
- Be skeptical of assumptions about Quickbase payloads, schema rows, retry semantics,
  file attachment formats, and DataFrame conversion. Verify against existing tests,
  local docs, or authoritative Quickbase documentation.
- Ask a concise question when requirements are materially ambiguous, a live Quickbase
  operation is involved, or a change could be destructive. Otherwise make the smallest
  reasonable change and proceed.
- Preserve user work. Do not revert or rewrite unrelated local changes.
- Keep behavior changes, documentation changes, and test updates in the same change set
  when they describe the same feature or fix.

## Project Layout

- `src/quickbase_data_client/`: package source.
- `src/quickbase_data_client/__init__.py`: public package exports and compatibility
  export warnings.
- `src/quickbase_data_client/quickbase_api.py`: sync auth, request configuration,
  retries, logging hooks, HTTP error mapping, and `QuickBaseClient`.
- `src/quickbase_data_client/table.py`: sync table-level workflows such as query,
  upsert, pagination, formula execution, and file operations.
- `src/quickbase_data_client/async_quickbase_api.py` and
  `src/quickbase_data_client/async_table.py`: async client and supported async table
  workflows.
- `src/quickbase_data_client/schema_cache.py`: explicit SQLite-backed schema cache.
- `src/quickbase_data_client/schema_manager.py`: legacy/local schema lookup support;
  this file is excluded from strict lint/type coverage.
- `src/quickbase_data_client/parsers/requests.py`: request endpoint and payload builders.
- `src/quickbase_data_client/parsers/responses.py` and
  `src/quickbase_data_client/parsers/response_factory.py`: response wrappers and
  response construction.
- `src/quickbase_data_client/tools/dataframe_encoder.py`: DataFrame conversion rules.
- `src/quickbase_data_client/tools/quickbase_log_handler.py`: logging handler that
  batches log records into Quickbase upserts.
- `src/quickbase_data_client/code_generation/` and
  `src/quickbase_data_client/typed_structs/`: generated or compatibility-heavy areas;
  these are intentionally excluded from some quality checks.
- `tests/`: unit tests plus opt-in live integration tests. Treat tests as the behavioral
  specification.
- `examples/`: dry-run-first example scripts. They are included in linting and type checks.
- `docs/`: long-form user documentation, including `docs/index.md`.
- `models/`: local schema cache artifacts. Treat contents as tenant-specific runtime
  data, not source material.

The root `CHANGELOG.md` follows Keep a Changelog for notable user-facing and
developer-facing changes.

## Environment

Use the repository virtual environment when it exists.

Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests -m "not integration"
```

Unix/macOS:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -m "not integration"
```

Do not read, print, commit, or summarize `.env` contents. Do not commit credentials,
Quickbase user tokens, generated schema databases, build artifacts, or cache directories.

## Validation

Match the configured CI commands before considering a broad change complete:

```bash
python -m pytest tests -m "not integration"
python -m ruff check src tests examples
python -m mypy src tests examples
python -m pytest tests --cov=quickbase_data_client --cov-report=term-missing -m "not integration"
```

CI runs tests on Python 3.10 and 3.13. The package requires Python 3.10+.

The configured branch coverage floor is 72%. Do not lower it to make a change pass.

Run the narrowest relevant test while iterating, then run the broader commands when the
change touches shared behavior, public API, request/response parsing, or documentation.
If a restricted Windows environment cannot access the default pytest temp directory,
append `--basetemp build/pytest-temp` to the pytest command.

## External Systems And Safety

- Unit tests must remain isolated from the network. Use fakes, monkeypatching, or mock
  sessions instead of contacting Quickbase.
- Live Quickbase tests must keep the `integration` marker and the explicit
  `QUICKBASE_RUN_INTEGRATION_TESTS=1` gate.
- Do not run live Quickbase operations unless the user explicitly asks and confirms the
  target environment.
- Treat record deletion, bulk upserts, file deletion, schema refreshes against a live
  tenant, and generated schema data as sensitive operations.
- Never expose authentication tokens, API keys, cookies, or raw sensitive payload values
  in logs, exceptions, tests, docs, or examples.
- Request/response hooks must remain summarized and sanitized. Authorization headers and
  raw payload values must not leak through debug output.

## Implementation Conventions

- Prefer IDs as the primary public contract. Name-based lookup should remain optional and
  explicit through `SchemaCache` or existing identifier behavior.
- Do not introduce import-time schema loading, network calls, or `.env` reads.
- Keep sync transport behavior centralized in `QuickBaseAPI.request`.
- Keep async transport behavior centralized in `AsyncQuickBaseAPI.request`.
- Keep endpoint and payload construction in `parsers.requests` where practical.
- Keep response normalization in `parsers.responses` and `ResponseFactory`.
- Preserve the split between the fuller sync surface and the intentionally smaller async
  surface. Do not add async parity unless there is a concrete requirement and tests.
- Use the package exception hierarchy from `exceptions.py`. Invalid caller input should
  raise a specific package validation/configuration/payload error. External HTTP and
  transport failures should be mapped through package exceptions.
- When wrapping another exception, preserve the traceback with `raise ... from exc`.
- Validate request sizes, file sizes, field identifiers, record identifiers, and paging
  arguments before issuing requests.
- For DataFrame changes, update `DataFrameEncoder` tests around ID columns, numeric
  string columns, name-based columns, duplicate/ambiguous fields, and sanitization.
- Keep generated schema cache files out of source and documentation. Do not copy tenant
  metadata into examples or tests.

## Public API And Compatibility

- The public package surface is defined in `src/quickbase_data_client/__init__.py` and
  `__all__`.
- `QuickBaseClient` and `AsyncQuickBaseClient` are the preferred client names.
- `QuickBaseAPI` and `AsyncQuickBaseAPI` remain compatibility/explicit paths.
- Deprecated compatibility exports should warn with `DeprecationWarning` and keep tests
  that prove the warning behavior.
- `App.table(...)` and `AsyncApp.table(...)` are preferred. Legacy `Table(...)` methods
  should continue warning unless a deliberate breaking release removes them.
- The package version is declared in `pyproject.toml`; runtime `__version__` is read from
  installed package metadata in `quickbase_api.py`.
- The current license is the Unlicense. Keep `LICENSE`, `README.md`, and `pyproject.toml`
  license metadata consistent.

## Python Style

- Follow the existing type-annotated style and keep Python 3.10 compatibility.
- Use `from __future__ import annotations` in new Python modules.
- Keep lines at or below 100 characters.
- Ruff currently enforces `D`, `E`, `F`, and `I` for `src`, `tests`, and `examples`.
  Tests ignore docstring rules.
- Mypy runs over `src`, `tests`, and `examples`, with explicit overrides for
  generated/legacy areas.
- Avoid broad `except Exception` unless translating failures at a deliberate package
  boundary, such as payload serialization, response parsing, schema refresh, or logging.
- Do not add runtime dependencies, async APIs, or abstraction layers without a concrete
  requirement.

## Documentation

- Keep the root `README.md` concise: what the package does, the supported public surface,
  a working quickstart, links to docs, scope boundaries, schema-data safety, and license.
- Put detailed user guidance under `docs/`.
- When public behavior changes, update the relevant docs page in the same change.
- Keep README and docs examples aligned with the public API and the ID-first recommendation.
- Do not document placeholder credentials in a way that could be executed against a real
  tenant by mistake.
- Add notable user-facing or developer-facing changes to `CHANGELOG.md` under
  `Unreleased`. Do not list trivial formatting-only edits.

### Python Docstrings

* Follow the [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) for Python docstrings. (This requirement applies to documentation style; the codebase line length remains 100 characters).
* Use triple double quotes (`\"\"\"`). Start with a one-line summary that ends with punctuation and stays within 80 characters. Add a blank line before longer details or section headings.
* Add module docstrings to non-test modules. Add docstrings to public classes, methods, and functions, plus internal helpers whose contract or side effects are not obvious.
* Use Google-style `Args:`, `Returns:`, `Yields:`, `Raises:`, and `Attributes:` sections where applicable. Do not repeat type information already expressed by annotations.
* Document behavior, units, accepted formats, side effects, mutation, external I/O, and exceptions callers are expected to handle. Do not narrate the implementation.
* Keep docstrings synchronized with signatures and behavior in the same change.

## Tests

- Add or update tests for every behavior change.
- Follow the existing `test_<behavior>` function style.
- Use pytest fixtures, monkeypatching, simple fakes, and `tmp_path` for filesystem work.
- Assert methods, endpoints, payloads, headers, and parsed response shapes when testing
  API interactions.
- For retry and backoff behavior, monkeypatch sleep/randomness so tests stay fast and
  deterministic.
- Cover both successful behavior and relevant validation/error paths.
- Do not weaken assertions just to accommodate an implementation change.

## Packaging And Release

- Do not edit generated contents under `build/`, `dist/`, `*.egg-info/`, or cache
  directories.
- Source distribution safety matters because `models/` may contain tenant-specific schema
  data. Keep `MANIFEST.in` and package discovery aligned with that boundary.
- Release builds use:

```bash
python -m build --sdist --wheel
```

The GitHub release workflow attaches `dist/*` artifacts and publishes them to PyPI.

## This Document

This file is project policy for future agent work. Update it when the project
direction changes, but only when the user explicitly asks for repository
instructions to change. Changes may be suggested without prompting when appropriate, but they must be explicitly approved. 