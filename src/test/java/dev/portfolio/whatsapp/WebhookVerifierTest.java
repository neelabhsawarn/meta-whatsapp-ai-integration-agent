package dev.portfolio.whatsapp;

import org.junit.jupiter.api.Test;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;
import static org.junit.jupiter.api.Assertions.*;

class WebhookVerifierTest {
    @Test void acceptsValidSignature() throws Exception {
        byte[] payload = "{\"ok\":true}".getBytes(StandardCharsets.UTF_8);
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec("local-secret".getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String signature = "sha256=" + HexFormat.of().formatHex(mac.doFinal(payload));
        assertTrue(WebhookVerifier.valid("local-secret", payload, signature));
        assertFalse(WebhookVerifier.valid("local-secret", "tampered".getBytes(StandardCharsets.UTF_8), signature));
    }
    @Test void rejectsMalformedHeaderAndMissingSecret() {
        assertFalse(WebhookVerifier.valid("secret", new byte[0], "sha1=broken"));
        assertFalse(WebhookVerifier.valid("secret", new byte[0], "sha256=zzzz"));
        assertFalse(WebhookVerifier.valid("", new byte[0], "sha256=" + "0".repeat(64)));
    }
    @Test void challengesRequireMatchingNonEmptyToken() {
        assertTrue(WebhookVerifier.verifyToken("verify", "verify"));
        assertFalse(WebhookVerifier.verifyToken("verify", "wrong"));
        assertFalse(WebhookVerifier.verifyToken("", ""));
    }
}
