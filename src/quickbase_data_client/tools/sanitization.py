"""Value sanitization helpers for Quickbase record payloads."""

from datetime import date, datetime, time
from typing import Any, Callable, Dict, Optional, Union

import pandas as pd
from pandas.api.types import is_scalar

from quickbase_data_client.exceptions import QuickbasePayloadError, format_error_message

TYPE_FORMATTERS: Dict[str, Callable[[Any], Any]] = {
    "text": lambda value: str(value),
    "rich-text": lambda value: str(value),
    "text-multi-line": lambda value: str(value),
    "text-multiple-choice": lambda value: str(value),
    "multitext": lambda value: str(value),
    "address": lambda value: str(value),
    "email": lambda value: str(value),
    "url": lambda value: str(value),
    "numeric": lambda value: float(value),
    "percent": lambda value: float(value),
    "rating": lambda value: int(value),
    "currency": lambda value: float(value),
    "date": lambda value: (
        value.strftime("%Y-%m-%d")
        if isinstance(value, (date, datetime))
        else pd.to_datetime(value).date().strftime("%Y-%m-%d")
    ),
    "datetime": lambda value: (
        value.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(value, datetime)
        else pd.to_datetime(value).tz_localize(None).strftime("%Y-%m-%dT%H:%M:%SZ")
    ),
    "timeofday": lambda value: (
        value.strftime("%H:%M:%S.%f")[:-3]
        if isinstance(value, (time, datetime))
        else pd.to_datetime(value).time().strftime("%H:%M:%S.%f")[:-3]
    ),
    "checkbox": lambda value: bool(value),
}


class Sanitizer:
    """Convert Python and pandas values into Quickbase-friendly scalar values."""

    @staticmethod
    def sanitize(
        value: Any,
        type_name: str | None,
    ) -> Optional[Union[str, float, int]]:
        """Sanitize one value according to a Quickbase field type."""
        if Sanitizer._is_missing_scalar(value):
            return None

        formatter = TYPE_FORMATTERS.get(type_name or "")
        if not formatter:
            return value

        try:
            return formatter(value)
        except Exception as exc:
            raise QuickbasePayloadError(
                format_error_message(
                    "Could not sanitize field value for Quickbase payload.",
                    operation="Sanitizer.sanitize",
                    field_type=type_name,
                    value=value,
                    cause=exc,
                )
            ) from exc

    @staticmethod
    def _is_missing_scalar(value: Any) -> bool:
        if value is None or not is_scalar(value):
            return value is None

        try:
            return bool(pd.isna(value))
        except (TypeError, ValueError):
            return False
