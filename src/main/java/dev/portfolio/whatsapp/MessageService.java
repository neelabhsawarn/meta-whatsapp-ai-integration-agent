package dev.portfolio.whatsapp;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class MessageService {
    private final MessageStore store;
    private final MetaGateway meta;
    private final DiagnosticStore diagnostics;
    private final int maxRetries;
    private final long maxDelayMs;
    private final Sleeper sleeper;

    @FunctionalInterface public interface Sleeper { void sleep(long millis) throws InterruptedException; }

    public MessageService(MessageStore store, MetaGateway meta, DiagnosticStore diagnostics,
                          @Value("${integration.max-rate-retries:2}") int maxRetries,
                          @Value("${integration.max-retry-delay-ms:3000}") long maxDelayMs) {
        this(store, meta, diagnostics, maxRetries, maxDelayMs, Thread::sleep);
    }
    // Package-private overload for deterministic tests without sleeping.
    MessageService(MessageStore store, MetaGateway meta, DiagnosticStore diagnostics,
                   int maxRetries, long maxDelayMs, Sleeper sleeper) {
        this.store = store;
        this.meta = meta;
        this.diagnostics = diagnostics;
        this.maxRetries = Math.max(0, Math.min(5, maxRetries));
        this.maxDelayMs = Math.max(0, Math.min(10_000, maxDelayMs));
        this.sleeper = sleeper;
    }

    public SendResult send(String idempotencyKey, String recipient, String body) {
        if (idempotencyKey == null || idempotencyKey.isBlank() || idempotencyKey.length() > 128) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Idempotency-Key must be 1–128 characters");
        }
        String keyHash = Hashing.sha256(idempotencyKey);
        String payloadHash = Hashing.sha256(recipient + "\n" + body);
        if (!store.reserve(keyHash, payloadHash)) {
            MessageStore.Receipt saved = store.find(keyHash).orElseThrow();
            if (!saved.payloadHash().equals(payloadHash)) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "Key reused with different request payload");
            }
            return new SendResult(saved.state(), saved.providerMessageId(), true);
        }

        for (int attempt = 0; attempt <= maxRetries; attempt++) {
            try {
                MetaGateway.MetaResult response = meta.sendText(recipient, body);
                if (response.accepted()) return complete(keyHash, "SENT", response.messageId(), false);
                if (response.status() == 429 && attempt < maxRetries) {
                    long backoff = Math.min(maxDelayMs, Math.max((250L << attempt), response.retryAfterSeconds() * 1000L));
                    sleeper.sleep(backoff);
                    continue;
                }
                String category = switch (response.status()) {
                    case 400 -> "BAD_REQUEST";
                    case 401, 403 -> "AUTH_OR_PERMISSION";
                    case 429 -> "RATE_LIMIT";
                    default -> response.status() >= 500 ? "UPSTREAM_UNCERTAIN" : "META_REJECTED";
                };
                diagnostics.record(category, response.status(), "send_text");
                // 5xx may represent a processed request followed by an error: do NOT blindly replay.
                String state = response.status() >= 500 ? "UNKNOWN" : "REJECTED";
                return complete(keyHash, state, null, false);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                diagnostics.record("INTERRUPTED", null, "send_text");
                return complete(keyHash, "UNKNOWN", null, false);
            } catch (Exception e) {
                // Network timeouts can occur after Meta accepted the message: no automatic replay.
                diagnostics.record("TRANSPORT_OR_CONFIG", null, "send_text");
                return complete(keyHash, "UNKNOWN", null, false);
            }
        }
        throw new IllegalStateException("Unreachable retry state");
    }

    private SendResult complete(String keyHash, String status, String providerId, boolean replay) {
        store.finish(keyHash, status, providerId);
        return new SendResult(status, providerId, replay);
    }
    public record SendResult(String state, String providerMessageId, boolean duplicate) {}
}
