"""Environment configuration. The app never supplies real secrets by default."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    meta_access_token: str
    meta_phone_number_id: str
    meta_app_secret: str
    webhook_verify_token: str
    internal_api_key: str
    allowed_test_recipients: tuple[str, ...]
    database_path: str = "runtime/integration.sqlite3"
    graph_version: str = "v26.0"
    meta_base_url: str = "https://graph.facebook.com"
    max_attempts: int = 3
    retry_base_seconds: float = 0.2
    retry_max_seconds: float = 5.0
    openai_model: str = "gpt-5-mini"

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        settings = cls(
            meta_access_token=os.getenv("META_ACCESS_TOKEN", ""),
            meta_phone_number_id=os.getenv("META_PHONE_NUMBER_ID", ""),
            meta_app_secret=os.getenv("META_APP_SECRET", ""),
            webhook_verify_token=os.getenv("WEBHOOK_VERIFY_TOKEN", ""),
            internal_api_key=os.getenv("INTERNAL_API_KEY", ""),
            allowed_test_recipients=tuple(
                value.strip() for value in os.getenv("ALLOWED_TEST_RECIPIENTS", "").split(",")
                if value.strip()
            ),
            database_path=os.getenv("DATABASE_PATH", "runtime/integration.sqlite3"),
            graph_version=os.getenv("GRAPH_VERSION", "v26.0"),
            max_attempts=int(os.getenv("MAX_ATTEMPTS", "3")),
            retry_base_seconds=float(os.getenv("RETRY_BASE_SECONDS", "0.2")),
            retry_max_seconds=float(os.getenv("RETRY_MAX_SECONDS", "5")),
            openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for key in ("meta_app_secret", "webhook_verify_token", "internal_api_key"):
            if not getattr(self, key):
                raise ValueError(f"Missing {key}; set it in .env")
        if not self.graph_version.startswith("v") or not self.graph_version[1:].replace(".", "").isdigit():
            raise ValueError("Invalid GRAPH_VERSION")
        if self.max_attempts < 1 or self.max_attempts > 10:
            raise ValueError("MAX_ATTEMPTS must be 1-10")
        if self.retry_base_seconds < 0 or self.retry_max_seconds < 0:
            raise ValueError("Retry delays must be nonnegative")
