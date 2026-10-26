# Meta WhatsApp Cloud API + Java AI Diagnostics Agent

[![Java CI](https://github.com/neelabhsawarn/meta-whatsapp-ai-integration-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/neelabhsawarn/meta-whatsapp-ai-integration-agent/actions)

**Java 21 · Spring Boot 4.0.9 · Maven · PostgreSQL · Flyway · Spring JDBC · OpenAI Java SDK · JUnit/Mockito/Testcontainers**

A portfolio-focused backend integration with Meta's **WhatsApp Cloud API test phone number**. It showcases a REST client, bearer-token auth, constant-time webhook HMAC validation, inbound event de-duplication, bounded 429 retry handling, outbound idempotency, sanitized diagnostics, and a **read-only tool-calling LLM agent**.

> **Reality check:** Unit tests mock Meta; Docker/Testcontainers exercises a real PostgreSQL database. Sending real WhatsApp test messages and calling an LLM need developer credentials and were not performed here. Meta's Cloud API does **not** provide guaranteed exactly-once outbound delivery just because this app has an idempotency ledger. An `UNKNOWN` send must be reconciled manually before a new key is used.

The previous Python implementation remains available on the [`python-original`](https://github.com/neelabhsawarn/meta-whatsapp-ai-integration-agent/tree/python-original) branch.

## Architecture

```text
POST /api/messages (local bearer token + Idempotency-Key)
  └─ MessageService -> PostgreSQL outbound_messages (unique hash of key)
       └─ HttpMetaGateway -> Meta Graph /{version}/{phone_id}/messages
                         ├─ 2xx → SENT (save Meta message ID)
                         ├─ 429 → bounded Retry-After/backoff; eventually REJECTED
                         └─ 5xx/timeout → UNKNOWN, do not automatically replay
GET /webhook (Meta challenge) / POST /webhook (raw HMAC SHA-256)
  └─ PostgreSQL inbound_events (hashed event ID + event type/status; no message text)
GET /api/diagnostics → sanitized diagnostic_events
POST /api/diagnose → OpenAI Responses function calls → read-only queries
```

See [`docs/architecture.md`](docs/architecture.md) for the why behind each design decision.

## Requirements

- Java **21**, Maven **3.9+**, Docker Desktop (for PostgreSQL and Testcontainers).
- A Meta developer app with the WhatsApp Cloud API test phone number, access token, and **phone-number ID** from the app's **WhatsApp / API Setup** screen (screen labels/eligibility can change).
- Optional: `OPENAI_API_KEY` for the diagnostic agent. This is an API billing key, separate from ChatGPT subscriptions.

## Quickstart (Windows PowerShell)

```powershell
git clone https://github.com/neelabhsawarn/meta-whatsapp-ai-integration-agent.git
cd meta-whatsapp-ai-integration-agent
Copy-Item .env.example .env
# Edit .env in VS Code. NEVER commit it.
docker compose up -d
```

Spring Boot reads **environment variables**. A plain `.env` file is NOT loaded by `mvn spring-boot:run` automatically. For a quick local test, set values in the current terminal (substitute your own secrets):

```powershell
$env:LOCAL_API_KEY = "a-long-private-local-key"
$env:META_ACCESS_TOKEN = "test-token-from-meta"
$env:META_PHONE_NUMBER_ID = "test-phone-id-from-meta"
$env:META_APP_SECRET = "app-secret-from-meta"
$env:META_VERIFY_TOKEN = "my-private-webhook-verify-token"
$env:OPENAI_API_KEY = "your-optional-openai-api-key"

mvn clean test
mvn spring-boot:run
```

Or load values from your ignored `.env` file into PowerShell (**trusted local file only**):

```powershell
Get-Content .env | Where-Object { $_ -match '^[A-Z][A-Z0-9_]*=' } | ForEach-Object {
  $name, $value = $_ -split '=', 2
  Set-Item -Path "Env:$name" -Value $value
}
mvn spring-boot:run
```

Default PostgreSQL: `localhost:5432`, database/user `whatsapp`, password `local_password`. If you change the password, also set `DB_PASSWORD` before `docker compose up`. On Docker-less machines you can run the pure JUnit tests; the PostgreSQL Testcontainers test is skipped.

Healthcheck: `GET http://localhost:8080/actuator/health`.

## Call the API

Send an approved **test recipient** with a unique key. Meta enforces test-recipient and conversation rules; not every number or message type is permitted in test mode.

```powershell
$headers = @{ Authorization = "Bearer $env:LOCAL_API_KEY"; "Idempotency-Key" = "demo-001" }
$body = @{ to = "447700900001"; text = "Hello from my Java portfolio project" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/messages -Headers $headers -ContentType 'application/json' -Body $body
```

Replace `447700900001` with a recipient Meta has allowed you to test. Repeating the **same key + same body** returns the existing receipt and doesn't call Meta again. Using **the same key with different content** returns HTTP 409. The database stores a hash of the recipient/text combination, not the original text.

```powershell
Invoke-RestMethod -Uri http://localhost:8080/api/diagnostics -Headers @{ Authorization = "Bearer $env:LOCAL_API_KEY" }
$question = @{ question = "Why are send requests being rate limited?" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/diagnose -Headers @{ Authorization = "Bearer $env:LOCAL_API_KEY" } -ContentType 'application/json' -Body $question
```

## Meta webhook setup

1. Create or open your app at [Meta for Developers](https://developers.facebook.com/), add the WhatsApp product where available, and review test-number restrictions in **WhatsApp / API Setup**.
2. Set a **callback URL** publicly reachable over HTTPS, e.g. `https://your-dev-tunnel.example/webhook` (use a tunnel only if trusted and configured securely).
3. Set **Verify Token** to exactly the same value as `META_VERIFY_TOKEN`.
4. Subscribe to the WhatsApp messages webhook field supported by your app. Meta will send a `GET /webhook` challenge and then signed `POST /webhook` notifications.
5. The POST signature is in `X-Hub-Signature-256`; the server computes `HMAC-SHA256(rawRequestBytes, META_APP_SECRET)` before parsing the JSON. Invalid signatures return HTTP 401. Events are stored by hashed `message id` or `status id + status`, never with the sender's phone number or message body.

Never confuse the **verify token** (your own chosen string) with Meta's **App Secret** or **access token** (issued by Meta).

## Error-handling table

| Situation | Response and action |
|---|---|
| No/bad local bearer token | HTTP 401, no send |
| Invalid webhook signature | HTTP 401, no event stored |
| Same idempotency key, different payload | HTTP 409, no send |
| Meta 400/401/403 | `REJECTED`, sanitized category recorded |
| Meta HTTP 429 | Retry up to 2 times with bounded delay (respect numeric `Retry-After` within cap); then `REJECTED` |
| Meta HTTP 500+ or network timeout | `UNKNOWN`, no automatic retry; reconcile first |
| No `OPENAI_API_KEY` | Diagnosis endpoint returns HTTP 503, other endpoints still work |

### Why no retry after a timeout?

A timeout may happen **after** Meta accepted the message. Retrying may send twice. The local idempotency key prevents duplicate submissions *to this service*, but Meta's messages endpoint is not treated as a guaranteed end-to-end exactly-once operation. To keep this example safe, uncertain outcomes are marked `UNKNOWN` and require manual reconciliation. This is an important interview trade-off.

### Troubleshooting

- **PostgreSQL connection refused**: run `docker compose ps` / `docker compose logs postgres`; check port 5432 and credentials.
- **Flyway errors**: start with a clean dev database using `docker compose down -v` (**deletes local data**; never do this on production).
- **Meta 401/403**: confirm access token, permissions, phone-number ID, app test settings, and token expiry.
- **Meta 429**: check rate limit rules and backoff, reduce throughput; no unlimited retries.
- **Webhook verification fails**: confirm public HTTPS callback and exact verify token.
- **Webhook POST HTTP 401**: ensure `META_APP_SECRET` is the *app secret* (not verify token), and no proxy modifies the raw payload.
- **Test number cannot message recipient**: add an allowed test recipient according to the current dashboard limits.
- **LLM diagnosis 503**: set `OPENAI_API_KEY` in the running process and ensure the selected model is accessible.

## Responsible AI & evaluation

The agent only calls `RecentDiagnostics` and `DiagnosticById`. Both are **read-only**, return restricted structured event categories and never expose raw headers, tokens, phone numbers, customer messages, or Meta response bodies. The model **cannot** send messages, change DB rows or deploy fixes. A human must inspect and approve any suggested remediation.

Evaluation inputs are in [`samples/eval_cases.jsonl`](samples/eval_cases.jsonl) with expected diagnostic categories. Example acceptance criteria: it should identify 401 as an auth/permission issue, 429 as a rate limit, and `UNKNOWN` as requiring manual reconciliation; no secrets/PII in responses; no invented repair claims. These cases are not live benchmark scores—run and review them yourself with your own API key.

## Build checks and limits

```bash
mvn -B clean verify
```

`MessageServiceTest`, `WebhookVerifierTest`, and `ApiSecurityTest` are local tests. `DiagnosticStoreTest` uses a disposable PostgreSQL Testcontainer when Docker is available. CI is configured in [GitHub Actions](.github/workflows/ci.yml); check its status after pushing. **Meta and OpenAI network calls are not executed in unit tests.**

Security hardening for an actual deployment: HTTPS everywhere, secrets manager, finer-grained auth/authorisation, robust distributed leasing/recovery for `PROCESSING`, webhook replay detection and retention/erasure policies, request quotas, agent usage limits, and stricter circuit-breaking/observability. This is a learning project, not a ready-to-deploy customer messaging service.
