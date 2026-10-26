"""Meta HTTP integration with bounded rate-limit retries and honest delivery semantics."""
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import httpx
from .config import Settings
from .db import Ledger

RATE_LIMIT_CODES = {4, 17, 32, 80007, 130429, 131056}


@dataclass
class SendError(Exception):
    kind: str  # retryable, uncertain, permanent
    code: str
    hint: str
    retry_after_seconds: float = 0.0


class MetaClient:
    def __init__(self, settings: Settings, ledger: Ledger, client: httpx.AsyncClient | None = None, sleep=None):
        self.settings = settings
        self.ledger = ledger
        self.client = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0))
        self.owns_client = client is None
        self.sleep = sleep or asyncio.sleep

    @staticmethod
    def _delay(retry_after: str | None, attempt: int, settings: Settings) -> float:
        wait = settings.retry_base_seconds * 2 ** (attempt - 1)
        if retry_after:
            try:
                wait = max(wait, float(retry_after))
            except ValueError:
                try:
                    delta = (parsedate_to_datetime(retry_after) - datetime.now(timezone.utc)).total_seconds()
                    wait = max(wait, delta)
                except (ValueError, TypeError, OverflowError):
                    pass
        return max(wait, 0.0)

    async def send_text(self, recipient: str, text: str) -> str:
        if not self.settings.meta_access_token or not self.settings.meta_phone_number_id:
            raise SendError("permanent", "configuration", "Missing Meta access token or phone number ID")
        url = (f"{self.settings.meta_base_url.rstrip('/')}/"
               f"{self.settings.graph_version}/{self.settings.meta_phone_number_id}/messages")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"body": text},
        }
        headers = {"Authorization": f"Bearer {self.settings.meta_access_token}"}
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                response = await self.client.post(url, json=payload, headers=headers)
            except (httpx.ConnectTimeout, httpx.ConnectError):
                self.ledger.log("meta", "connect_failure", "network_connect", "Connection failed before HTTP response", attempt)
                if attempt == self.settings.max_attempts:
                    raise SendError("retryable", "network_connect", "Connection could not be established")
                await self.sleep(min(self.settings.retry_max_seconds, self._delay(None, attempt, self.settings)))
                continue
            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError):
                self.ledger.log("meta", "ambiguous_delivery", "unknown_outcome", "Request outcome unknown; manual reconciliation required", attempt)
                raise SendError("uncertain", "unknown_outcome", "Request might have been accepted; do not retry blindly")
            try:
                data = response.json()
            except ValueError:
                data = {}
            if response.is_success:
                try:
                    return data["messages"][0]["id"]
                except (KeyError, IndexError, TypeError):
                    self.ledger.log("meta", "ambiguous_delivery", "unexpected_success", "Successful HTTP response lacked a message ID", attempt)
                    raise SendError("uncertain", "unexpected_success", "Successful response with unknown message ID")
            error_code = data.get("error", {}).get("code") if isinstance(data, dict) and isinstance(data.get("error"), dict) else None
            code = str(error_code if error_code is not None else response.status_code)
            if response.status_code == 429 or error_code in RATE_LIMIT_CODES:
                self.ledger.log("meta", "rate_limited", code, "Meta rate limit; backoff before retry", attempt)
                if attempt == self.settings.max_attempts:
                    raise SendError("retryable", code, "Rate limit exhausted; retry the same idempotency key later", self._delay(response.headers.get("Retry-After"), attempt, self.settings))
                delay = self._delay(response.headers.get("Retry-After"), attempt, self.settings)
                if delay > self.settings.retry_max_seconds:
                    raise SendError("retryable", code, "Meta requested a longer wait; retry the same key after the specified delay", delay)
                await self.sleep(delay)
                continue
            if response.status_code >= 500:
                self.ledger.log("meta", "ambiguous_delivery", code, "Meta server error; delivery outcome not certain", attempt)
                raise SendError("uncertain", code, "Meta server error; cannot guarantee message was not accepted")
            self.ledger.log("meta", "permanent_api_error", code, "Check permissions, recipient, token, template and test access", attempt)
            raise SendError("permanent", code, "Meta rejected request; inspect code and permissions")
        raise AssertionError("Unreachable retry loop")
