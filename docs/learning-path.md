# Learn the project in four days

1. **Day 1 — APIs:** Explain `@RestController`, dependency injection, `RestClient`, bearer tokens, JSON and HTTP status codes. Trace `ApiController` → `MessageService` → `HttpMetaGateway`.
2. **Day 2 — Security:** Explain webhook GET challenge vs POST HMAC-SHA256 signature, why raw bytes matter, and why secrets must never enter diagnostics.
3. **Day 3 — Reliability and SQL:** Explain PostgreSQL unique constraints, idempotency keys, 409 conflict, 429 retry with bounded backoff, and why a timeout cannot always be retried.
4. **Day 4 — LLM + Tests:** Explain OpenAI Responses function calls, local read-only tool execution, prompt-injection boundaries, Mockito unit tests and PostgreSQL Testcontainers.

Suggested interview walkthrough: send a message once (success), repeat the same idempotency key (no new send), change payload with same key (409), demonstrate mocked 429 then success, discuss timeout ambiguity, verify forged webhook rejection, and show diagnostic agent reasoning from sanitized metadata.

Never claim you've sent live Meta test messages or evaluated the AI agent until you have performed those steps with your credentials.
