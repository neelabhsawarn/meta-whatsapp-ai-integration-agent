import json
import hmac
import hashlib
import httpx
import pytest
from app.api import create_app


@pytest.mark.asyncio
async def test_webhook_handshake_and_rejections(settings):
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        ok = await client.get("/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "test-verify-token", "hub.challenge": "abc123"
        })
        assert ok.status_code == 200 and ok.text == "abc123"
        assert (await client.get("/webhook", params={
            "hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "abc123"
        })).status_code == 403
        assert (await client.post("/webhook", content=b'{}')).status_code == 403


@pytest.mark.asyncio
async def test_signed_webhook_dedupes_message_and_status(settings):
    app = create_app(settings)
    body = json.dumps({"object": "whatsapp_business_account", "entry": [{"changes": [{
        "value": {"messages": [{"id": "wamid.abc", "text": {"body": "private chat text"}, "from": "447000000001"}],
                  "statuses": [{"id": "wamid.status", "status": "sent", "timestamp": "100"}]}
    }]}]}).encode()
    digest = hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {"X-Hub-Signature-256": "sha256=" + digest}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        a = await client.post("/webhook", content=body, headers=headers)
        b = await client.post("/webhook", content=body, headers=headers)
        bad = await client.post("/webhook", content=body + b" ", headers=headers)
    assert a.json() == {"accepted": True, "new_events": 2, "duplicates": 0}
    assert b.json() == {"accepted": True, "new_events": 0, "duplicates": 2}
    assert bad.status_code == 403
    with app.state.ledger.connection() as db:
        rows = db.execute("SELECT * FROM incoming").fetchall()
        assert len(rows) == 2
        assert all("447000000001" not in str(tuple(row)) and "private chat text" not in str(tuple(row)) for row in rows)


@pytest.mark.asyncio
async def test_signed_bad_json_is_rejected(settings):
    app = create_app(settings)
    body = b"not-json"
    sig = "sha256=" + hmac.new(settings.meta_app_secret.encode(), body, hashlib.sha256).hexdigest()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        result = await client.post("/webhook", content=body, headers={"X-Hub-Signature-256": sig})
    assert result.status_code == 400
