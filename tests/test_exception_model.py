from unittest.mock import Mock

import pytest
import requests

from quickbase_sdk.exceptions import (
    QuickbasePayloadError,
    QuickbaseRateLimitError,
    QuickbaseValidationError,
    format_error_message,
)
from quickbase_sdk.file_payload import FilePayload
from quickbase_sdk.identifier import Identifier
from quickbase_sdk.quickbase_api import Auth, QuickBaseAPI, RequestConfig
from quickbase_sdk.tools.sanitization import Sanitizer


def test_format_error_message_includes_context_and_cause() -> None:
    message = format_error_message(
        "Operation failed.",
        operation="tests.example",
        endpoint="/v1/test",
        item_id="abc123",
        cause=ValueError("bad value"),
    )

    assert "Operation failed." in message
    assert "operation=tests.example" in message
    assert "endpoint=/v1/test" in message
    assert "item_id='abc123'" in message
    assert "ValueError: bad value" in message


def test_identifier_requires_id_or_name() -> None:
    with pytest.raises(QuickbaseValidationError, match="operation=Identifier.__init__"):
        Identifier("TABLE")


def test_file_payload_rejects_directory_paths(tmp_path) -> None:
    with pytest.raises(QuickbasePayloadError, match="operation=FilePayload._validate_path"):
        FilePayload(drive_path=tmp_path)


def test_sanitizer_wraps_conversion_errors() -> None:
    with pytest.raises(QuickbasePayloadError, match="operation=Sanitizer.sanitize"):
        Sanitizer.sanitize("not-a-number", "numeric")


def test_quickbase_api_maps_rate_limits_to_package_exception(monkeypatch) -> None:
    api = QuickBaseAPI(
        Auth("example.quickbase.com", "token"),
        request_config=RequestConfig(retry_count=0, jitter=0.0),
    )

    response = Mock()
    response.status_code = 429
    response.text = "rate limited"
    response.raise_for_status.side_effect = requests.HTTPError(response=response)
    monkeypatch.setattr(api.session, "request", Mock(return_value=response))

    with pytest.raises(QuickbaseRateLimitError, match="status_code=429"):
        api.request(method="GET", endpoint="/records")
