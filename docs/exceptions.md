# Exceptions

The maintained client raises package exceptions instead of returning status wrappers or relying on logger-only failure signaling.

## Hierarchy

- `QuickbaseError`: base package exception
- `QuickbaseValidationError`: invalid caller input
- `QuickbaseConfigurationError`: invalid local configuration
- `QuickbaseTransportError`: timeout, connection, or transport failures before a valid HTTP response
- `QuickbaseHTTPError`: non-success HTTP response from Quickbase
- `QuickbaseAuthError`: authentication or authorization failures
- `QuickbaseRateLimitError`: rate-limit failures such as HTTP `429`
- `QuickbaseSchemaError`: schema-cache lookup or refresh failures
- `QuickbaseNotFoundError`: missing Quickbase object or cached schema entity
- `QuickbasePayloadError`: invalid request or response payload content

## Common Catch Pattern

```python
from quickbase_data_client import Auth, QuickBaseClient
from quickbase_data_client.exceptions import (
    QuickbaseAuthError,
    QuickbaseHTTPError,
    QuickbaseRateLimitError,
    QuickbaseTransportError,
)

client = QuickBaseClient(Auth("example.quickbase.com", "qb-user-token"))

try:
    response = client.table(id="bq123456").query_records("{3.GT.0}")
except QuickbaseRateLimitError:
    ...
except QuickbaseAuthError:
    ...
except QuickbaseTransportError:
    ...
except QuickbaseHTTPError as exc:
    ...
```

## What Raises What

- validation problems such as bad constructor arguments: `QuickbaseValidationError`
- invalid `RequestConfig` values: `QuickbaseConfigurationError`
- timeouts and connection failures after retries are exhausted: `QuickbaseTransportError`
- `401` or `403`: `QuickbaseAuthError`
- `404`: `QuickbaseNotFoundError`
- `429`: `QuickbaseRateLimitError`
- other non-success HTTP responses: `QuickbaseHTTPError`
- missing or invalid schema cache state: `QuickbaseSchemaError`
- invalid file or payload content: `QuickbasePayloadError`

Exception messages include operational context such as the failing operation, endpoint, object reference, retry count, or related identifiers when that detail is available.
