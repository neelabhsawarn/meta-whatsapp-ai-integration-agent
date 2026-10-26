package dev.portfolio.whatsapp;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.HexFormat;

public final class WebhookVerifier {
    private WebhookVerifier() {}

    /** HMAC must be calculated over the *unaltered* request bytes, not parsed JSON. */
    public static boolean valid(String appSecret, byte[] rawBody, String header) {
        if (appSecret == null || appSecret.isBlank() || header == null || !header.startsWith("sha256=")) return false;
        String hex = header.substring(7);
        if (hex.length() != 64 || !hex.matches("[a-fA-F0-9]{64}")) return false;
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(appSecret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return MessageDigest.isEqual(mac.doFinal(rawBody), HexFormat.of().parseHex(hex));
        } catch (Exception e) { return false; }
    }

    public static boolean verifyToken(String expected, String received) {
        return expected != null && !expected.isBlank() && received != null &&
                MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), received.getBytes(StandardCharsets.UTF_8));
    }
}
