from __future__ import annotations

import warnings

from .app import App, AppRef
from .async_app import AsyncApp, AsyncAppRef
from .async_quickbase_api import AsyncQuickBaseAPI, AsyncQuickBaseClient
from .async_table import AsyncTable, AsyncTableRef
from .exceptions import (
    QuickbaseAuthError,
    QuickbaseConfigurationError,
    QuickbaseError,
    QuickbaseHTTPError,
    QuickbaseNotFoundError,
    QuickbasePayloadError,
    QuickbaseRateLimitError,
    QuickbaseSchemaError,
    QuickbaseTransportError,
    QuickbaseValidationError,
)
from .file_payload import FilePayload
from .identifier import Identifier
from .parsers.responses import QuickBaseResponse
from .quickbase_api import Auth, QuickBaseAPI, QuickBaseClient, RequestConfig, __version__
from .schema_cache import SchemaCache
from .table import Table, TableRef

__all__ = [
    "__version__",
    "Auth",
    "QuickBaseClient",
    "QuickBaseAPI",
    "AsyncQuickBaseClient",
    "AsyncQuickBaseAPI",
    "RequestConfig",
    "AppRef",
    "TableRef",
    "AsyncAppRef",
    "AsyncTableRef",
    "App",
    "Table",
    "AsyncApp",
    "AsyncTable",
    "Identifier",
    "SchemaCache",
    "FilePayload",
    "QuickBaseResponse",
    "QuickbaseError",
    "QuickbaseValidationError",
    "QuickbaseConfigurationError",
    "QuickbaseTransportError",
    "QuickbaseHTTPError",
    "QuickbaseAuthError",
    "QuickbaseRateLimitError",
    "QuickbaseSchemaError",
    "QuickbaseNotFoundError",
    "QuickbasePayloadError",
]

_COMPAT_EXPORTS = {
    "QuickBaseHandler": (
        "quickbase_data_client.tools.quickbase_log_handler",
        "QuickBaseHandler",
        (
            "QuickBaseHandler is deprecated at the package root; import it from "
            "quickbase_data_client.tools.quickbase_log_handler instead."
        ),
    ),
    "QuickBaseRequest": (
        "quickbase_data_client.parsers.requests",
        "QuickBaseRequest",
        (
            "QuickBaseRequest is an internal helper; import it from "
            "quickbase_data_client.parsers.requests only if you need the compatibility path."
        ),
    ),
    "ResponseFactory": (
        "quickbase_data_client.parsers.response_factory",
        "ResponseFactory",
        (
            "ResponseFactory is an internal helper; import it from "
            "quickbase_data_client.parsers.response_factory only if you need the "
            "compatibility path."
        ),
    ),
}


def __getattr__(name: str):
    if name in _COMPAT_EXPORTS:
        module_name, attribute_name, message = _COMPAT_EXPORTS[name]
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        module = __import__(module_name, fromlist=[attribute_name])
        value = getattr(module, attribute_name)
        globals()[name] = value
        return value

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
