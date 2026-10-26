# Architecture and design trade-offs

## Layers

- `ApiController` accepts authenticated integration requests and diagnostic questions.
- `MessageService` implements the state machine; `MessageStore` is a replaceable persistence interface.
- `HttpMetaGateway` isolates Meta REST transport and parses only status, Retry-After and message id.
- `WebhookController` challenges Meta and validates raw-byte signatures before parsing.
- `DiagnosticStore` stores fixed diagnostic categories and status codes only.
- `DiagnosticAgent` calls the official OpenAI Java SDK with **read-only** tool definitions.

## Outbound idempotency

Key and payload are hashed with SHA-256 before storage. The table's unique constraint allows only the first concurrent submission with an idempotency key to proceed. A replay with equal payload returns the stored state; a mismatched payload returns 409. This deduplicates *client requests to our service*, not delivery across all systems. The simple synchronous design does not recover from a process crash in `PROCESSING`; production would need leases, explicit reconciliation and a supervised recovery flow.

## Rate limits vs uncertainty

For explicit HTTP **429**, the service retries at most twice with a bounded numeric Retry-After and exponential fallback. For a **5xx** or transport exception it marks the send `UNKNOWN`, not replayed. This avoids avoidable double messages when the remote acceptance status is unclear. A production system would use remote delivery-status webhooks + reconciliation and limit concurrent users based on Meta's actual quota.

## Webhook authenticity and de-duplication

The HMAC uses the Meta application secret and raw request bytes; digest comparison is constant-time. A separate GET verification token establishes webhook ownership. Incoming message IDs and each stage of message status are SHA-256 hashed and inserted under a unique key. This app deliberately never forwards or persists customer message bodies. In production add strict body-size limits, event schema validation, ingress throttling, and durable queue processing.

## AI boundary

The LLM is optional; if missing an API key the main integration remains usable. The agent can see categories, codes and timestamps—not raw Meta JSON. Function tools use bounded read-only SQL and execute only after local API authentication. The agent cannot make remediation changes. Limit loops to three tool-call turns. This example asks the human operator to confirm actions.

## Why not Resilience4j here?

The core code intentionally implements a small, explicit retry loop to make exactly which statuses are retried obvious in an interview. A next iteration can add Resilience4j `Retry`, `RateLimiter`, and `CircuitBreaker` policies around the gateway while preserving the crucial rule: **never automatically retry ambiguous sends**. Introducing a generic retry-on-any-exception decorator without that rule would be unsafe.
