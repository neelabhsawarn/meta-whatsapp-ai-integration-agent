import httpx
import pytest
from app.api import create_app

HEADERS = {"X-API-Key": "test-internal-api-key", "Idempotency-Key": "idem-key-001"}
BODY = {"recipient": "447000000001", "text": "Test message - consented sandbox recipient"}


def ok_response() -> httpx.Response:
    return httpx.Response(200, json={"messages": [{"id": "wamid.test.123"}]})


@pytest.mark.asyncio
async def test_send_authorization_allowlist_and_durable_idempotency(settings):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        assert request.headers["Authorization"] == "Bearer test-meta-token-NOT-REAL"
        assert request.url.path == "/v26.0/12345/messages"
        return ok_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_meta:
        app = create_app(settings, client=mock_meta)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            assert (await client.post("/send", json=BODY, headers={"X-API-Key": "wrong", "Idempotency-Key": "idem-key-001"})).status_code == 401
            assert (await client.post("/send", json={**BODY, "recipient": "447000000002"}, headers=HEADERS)).status_code == 403
            first = await client.post("/send", json=BODY, headers=HEADERS)
            second = await client.post("/send", json=BODY, headers=HEADERS)
            conflict = await client.post("/send", json={**BODY, "text": "different"}, headers=HEADERS)
    assert first.status_code == 200 and first.json()["cached"] is False
    assert second.status_code == 200 and second.json()["cached"] is True
    assert conflict.status_code == 409
    assert count == 1


@pytest.mark.asyncio
async def test_retry_on_rate_limit_but_not_on_5xx(settings):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": 130429}})
        return ok_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_meta:
        app = create_app(settings, client=mock_meta, sleep=lambda _: _no_sleep())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            result = await client.post("/send", json=BODY, headers=HEADERS)
    assert result.status_code == 200 and count == 2
    assert app.state.ledger.error_counts()[0]["error_code"] == "130429"

    count_500 = 0

    def fail(request):
        nonlocal count_500
        count_500 += 1
        return httpx.Response(503, json={"error": {"code": 503}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as mock_meta:
        # New db path to avoid existing success under same key.
        from dataclasses import replace
        alt = replace(settings, database_path=settings.database_path + "-2")
        app = create_app(alt, client=mock_meta)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            uncertain = await client.post("/send", json=BODY, headers=HEADERS)
            replay = await client.post("/send", json=BODY, headers=HEADERS)
    assert uncertain.status_code == 502
    assert uncertain.json()["detail"]["state"] == "uncertain"
    assert replay.status_code == 409
    assert count_500 == 1


async def _no_sleep():
    return None


@pytest.mark.asyncio
async def test_exhausted_rate_limit_can_reclaim_same_key(settings):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(429, json={"error": {"code": 130429}}) if count <= 3 else ok_response()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_meta:
        app = create_app(settings, client=mock_meta, sleep=lambda _: _no_sleep())
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            first = await client.post("/send", json=BODY, headers=HEADERS)
            second = await client.post("/send", json=BODY, headers=HEADERS)
    assert first.status_code == 502 and first.json()["detail"]["state"] == "retryable"
    assert second.status_code == 200 and count == 4

@pytest.mark.asyncio
async def test_retry_after_larger_than_wait_budget_fails_safely(settings):
    from dataclasses import replace
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "60"}, json={"error": {"code": 130429}})

    config = replace(settings, retry_max_seconds=5)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_meta:
        app = create_app(config, client=mock_meta)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            result = await client.post("/send", json=BODY, headers=HEADERS)
    assert result.status_code == 502
    assert result.json()["detail"]["state"] == "retryable"
    assert "longer wait" in result.json()["detail"]["advice"]
    assert attempts == 1

@pytest.mark.asyncio
async def test_long_retry_after_is_persistently_enforced(settings):
    from dataclasses import replace
    attempts = 0

    def handler(request):
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, headers={"Retry-After": "60"}, json={"error": {"code": 130429}})

    config = replace(settings, retry_max_seconds=5)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock_meta:
        app = create_app(config, client=mock_meta)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
            first = await client.post("/send", json=BODY, headers=HEADERS)
            again = await client.post("/send", json=BODY, headers=HEADERS)
    assert first.status_code == 502
    assert again.status_code == 409
    assert "cooldown" in again.json()["detail"]
    assert attempts == 1
