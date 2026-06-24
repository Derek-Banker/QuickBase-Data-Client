# Examples

Example scripts live in `examples/` and are safe by default.

They do not read `.env` automatically. Pass `--env-file` when you want a script to load a
specific local environment file.

## Query Records

Preview the request without contacting Quickbase:

```bash
python examples/query_records.py --table-id bq123456 --select 3,6,7
```

Run a live query only after providing real credentials and `--execute`:

```bash
python examples/query_records.py --env-file .env --table-id bq123456 --execute
```

## Upsert Records

Preview a small upsert payload without contacting Quickbase:

```bash
python examples/upsert_records_dry_run.py --table-id bq123456
```

Live upserts require both `--execute` and `--confirm-upsert`:

```bash
python examples/upsert_records_dry_run.py --env-file .env --table-id bq123456 --execute --confirm-upsert
```

Use a test table when running live examples. The examples refuse placeholder credentials,
but they cannot know whether a real token points at a production tenant.
