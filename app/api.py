"""FastAPI endpoints. No webhook content or Meta access tokens are logged."""
from __future__ import annotations
import hashlib
import hmac
import json
import re
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from .config import Settings
from .db import Ledger
from .meta import MetaClient, SendError
from .security import check_signature, payload_fingerprint, private_id


class SendRequest(BaseModel):
    recipient: str = Field(pattern=r"^[1-9][0-9]{7,14}$", description="E.164 digits, no +")
    text: str = Field(min_length=1, max_length=1024)


def _webhook_identifiers(payload: dict, raw: bytes, secret: str) -> list[tuple[str, str]]:
    """Return pseudonymous event keys; no chat text, numbers or names retained."""
    found: list[tuple[str, str]] = []
    if not isinstance(payload, dict):
        return found
    for entry in payload.get("entry", []):
        if not isinstance(entry, dict):
            continue
        for change in entry.get("changes", []):
            if not isinstance(change, dict):
                continue
            value = change.get("value", {})
            if not isinstance(value, dict):
                continue
            for msg in value.get("messages", []):
                if isinstance(msg, dict) and msg.get("id"):
                    found.append((private_id(secret, "message:" + str(msg["id"])), "message"))
            for status in value.get("statuses", []):
                if isinstance(status, dict) and status.get("id"):
                    fingerprint = f"status:{status['id']}:{status.get('status', '')}:{status.get('timestamp', '')}"
                    found.append((private_id(secret, fingerprint), "status"))
    if not found:
        found.append((private_id(secret, "other:" + hashlib.sha256(raw).hexdigest()), "other"))
    return found


def create_app(settings: Settings | None = None, client: httpx.AsyncClient | None = None, sleep=None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    ledger = Ledger(settings.database_path)
    meta = MetaClient(settings, ledger, client, sleep)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            yield
        finally:
            if meta.owns_client:
                await meta.client.aclose()

    app = FastAPI(title="Meta WhatsApp Integration + Incident Agent", version="0.1.0", lifespan=lifespan)
    app.state.ledger = ledger

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/webhook", response_class=PlainTextResponse)
    async def verify_webhook(
        mode: str | None = Query(None, alias="hub.mode"),
        token: str | None = Query(None, alias="hub.verify_token"),
        challenge: str | None = Query(None, alias="hub.challenge"),
    ):
        if (mode == "subscribe" and token is not None and challenge is not None
                and hmac.compare_digest(token, settings.webhook_verify_token)):
            return challenge
        raise HTTPException(status_code=403, detail="Webhook verification rejected")

    @app.post("/webhook")
    async def receive_webhook(request: Request, x_hub_signature_256: str | None = Header(None)):
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Payload too large")
        raw = await request.body()
        if len(raw) > 1024 * 1024:
            raise HTTPException(status_code=413, detail="Payload too large")
        if not check_signature(raw, x_hub_signature_256, settings.meta_app_secret):
            ledger.log("webhook", "authentication_failure", "bad_signature", "HMAC SHA-256 verification failed")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON")
        if not isinstance(data, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")
        identifiers = _webhook_identifiers(data, raw, settings.meta_app_secret)
        inserted = sum(1 for event_id, kind in identifiers if ledger.receive_once(event_id, kind))
        return {"accepted": True, "new_events": inserted, "duplicates": len(identifiers) - inserted}

    @app.post("/send")
    async def send_message(
        payload: SendRequest,
        idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=128),
        x_api_key: str = Header(..., alias="X-API-Key"),
    ):
        if not hmac.compare_digest(x_api_key, settings.internal_api_key):
            raise HTTPException(status_code=401, detail="Bad internal API key")
        if not re.fullmatch(r"[\x21-\x7E]{8,128}", idempotency_key):
            raise HTTPException(status_code=422, detail="Invalid idempotency key")
        if payload.recipient not in settings.allowed_test_recipients:
            raise HTTPException(status_code=403, detail="Recipient not on ALLOWED_TEST_RECIPIENTS")
        fingerprint = payload_fingerprint(settings.meta_app_secret, payload.recipient, payload.text)
        state, old_meta_id = ledger.claim_outgoing(idempotency_key, fingerprint)
        if state == "conflict":
            raise HTTPException(status_code=409, detail="Idempotency key reused with different payload")
        if state == "succeeded":
            return {"status": "sent", "meta_message_id": old_meta_id, "cached": True}
        if state != "claimed":
            raise HTTPException(status_code=409, detail=f"Existing request state: {state}; review before resending")
        try:
            meta_id = await meta.send_text(payload.recipient, payload.text)
        except SendError as exc:
            ledger.complete_outgoing(idempotency_key, {
                "retryable": "retryable", "uncertain": "uncertain", "permanent": "permanent"
            }[exc.kind], retry_after_seconds=exc.retry_after_seconds)
            raise HTTPException(status_code=502, detail={"error_code": exc.code, "state": exc.kind, "advice": exc.hint})
        except Exception:
            # Deliberately fail closed if an unexpected exception occurs after a send attempt.
            ledger.complete_outgoing(idempotency_key, "uncertain")
            raise
        ledger.complete_outgoing(idempotency_key, "succeeded", meta_id)
        return {"status": "sent", "meta_message_id": meta_id, "cached": False}

    return app
