from typing import Final, Literal

DEFAULT_SCHEMA_NAME_JSON: Final[str] = "QuickBase_Schema"
DEFAULT_SCHEMA_PATH_JSON: Final[str] = f"models/{DEFAULT_SCHEMA_NAME_JSON}.json"
DEFAULT_SCHEMA_NAME_SQLITE: Final[str] = "QuickBase_Schema"
DEFAULT_SCHEMA_PATH_SQLITE: Final[str] = f"models/{DEFAULT_SCHEMA_NAME_SQLITE}.sqlite3"

LEVELS_LIST: Final[list[str]] = ["APP", "TABLE", "FIELD", "REPORT"]
LEVELS_LITERAL = Literal["APP", "TABLE", "FIELD", "REPORT"]

BASE_URL = "https://api.quickbase.com/v1"

DEFAULT_REQUEST_TIMEOUT: Final[tuple[float, float]] = (3.0, 25.0)
DEFAULT_RETRY_COUNT = 2
DEFAULT_RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({429, 502, 503, 504})
DEFAULT_RETRY_BACKOFF_FACTOR = 0.5
DEFAULT_RETRY_JITTER = 0.25

DEFAULT_MAX_FILE_SIZE = 10000
DEFAULT_MAX_REQUEST_SIZE = 35000

SUPPORTED_REPORT_TYPES_LIST: Final[list[str]] = [
    "STACKED-BAR",
    "SOLID-GAUGE",
    "BAR",
    "PIE",
    "LINE-BAR",
    "LINE",
    "TABLE",
]
SUPPORTED_REPORT_TYPES_LITERAL = Literal[
    "STACKED-BAR",
    "SOLID-GAUGE",
    "BAR",
    "PIE",
    "LINE-BAR",
    "LINE",
    "TABLE",
]

DEFAULT_EXPORT_PATH = "exports"
