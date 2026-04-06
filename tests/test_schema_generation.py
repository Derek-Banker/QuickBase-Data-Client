
import pytest

from quickbase_sdk import Auth
from quickbase_sdk.code_generation import generate_sql
from quickbase_sdk.code_generation.generate_schema import GenerateSchema
from tests.integration_support import require_integration_env

pytestmark = pytest.mark.integration

INTEGRATION_ENV = require_integration_env()


def test_schema_generation_integration() -> None:
    app_id = INTEGRATION_ENV["app_id"]
    assert app_id, "QUICKBASE_TEST_APP_ID or QUICKBASE_APP_ID must be set for integration tests."

    GenerateSchema(
        Auth(INTEGRATION_ENV["realm"], INTEGRATION_ENV["user_token"])
    ).update_all(app_id)
    generate_sql.sync()
