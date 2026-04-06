# Retries And Configuration

Use `RequestConfig` to control timeouts, retries, logging hooks, and request/file size limits.

## Defaults

Current defaults:

- `timeout=(3.0, 25.0)`
- `retry_count=2`
- `retryable_status_codes={429, 502, 503, 504}`
- `backoff_factor=0.5`
- `jitter=0.25`
- `respect_retry_after=True`
- `max_request_size_kb=35000`
- `max_file_size_kb=10000`

## Basic Configuration

```python
from quickbase_sdk import Auth, QuickBaseClient, RequestConfig

config = RequestConfig(
    timeout=(5.0, 30.0),
    retry_count=3,
    backoff_factor=1.0,
    jitter=0.0,
)

client = QuickBaseClient(
    Auth("example.quickbase.com", "qb-user-token"),
    request_config=config,
)
```

The same `RequestConfig` object type is used by the async client.

## Retry Behavior

The maintained request layer retries:

- timeouts
- connection errors
- HTTP `429`
- HTTP `502`
- HTTP `503`
- HTTP `504`

When `respect_retry_after=True`, a `Retry-After` header is honored for retryable responses such as `429`.

## Request/Response Logging Hooks

Hooks receive summarized request/response events:

```python
request_events = []
response_events = []

config = RequestConfig(
    request_log_hook=request_events.append,
    response_log_hook=response_events.append,
)
```

The hook payload is intentionally summarized and sensitive headers such as `Authorization` are redacted. Payload values are not echoed back into the summary.

## Size Limits

`max_request_size_kb` and `max_file_size_kb` are used by the maintained batching and file-upload paths.

Example:

```python
config = RequestConfig(
    max_request_size_kb=10_000,
    max_file_size_kb=5_000,
)
```

Those limits are especially relevant for:

- large record upserts
- multi-file uploads
- file payload validation
