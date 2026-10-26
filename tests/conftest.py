import pytest
from app.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        meta_access_token="test-meta-token-NOT-REAL",
        meta_phone_number_id="12345",
        meta_app_secret="test-signing-secret",
        webhook_verify_token="test-verify-token",
        internal_api_key="test-internal-api-key",
        allowed_test_recipients=("447000000001",),
        database_path=str(tmp_path / "ledger.sqlite3"),
        meta_base_url="https://graph.facebook.com",
        retry_base_seconds=0,
        retry_max_seconds=0,
        max_attempts=3,
    )
