package dev.portfolio.whatsapp;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.Map;

@RestController
public class WebhookController {
    private final String secret, token;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;

    public WebhookController(@Value("${integration.meta-app-secret:}") String secret,
                             @Value("${integration.meta-verify-token:}") String token,
                             JdbcTemplate jdbc, ObjectMapper mapper) {
        this.secret = secret;
        this.token = token;
        this.jdbc = jdbc;
        this.mapper = mapper;
    }

    @GetMapping("/webhook")
    public ResponseEntity<String> verify(@RequestParam(value = "hub.mode", required = false) String mode,
                                         @RequestParam(value = "hub.verify_token", required = false) String provided,
                                         @RequestParam(value = "hub.challenge", required = false) String challenge) {
        if ("subscribe".equals(mode) && challenge != null && WebhookVerifier.verifyToken(token, provided)) {
            return ResponseEntity.ok(challenge);
        }
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body("Verification rejected");
    }

    @PostMapping("/webhook")
    public ResponseEntity<Map<String, Object>> accept(@RequestBody byte[] raw,
            @RequestHeader(value = "X-Hub-Signature-256", required = false) String signature) {
        if (!WebhookVerifier.valid(secret, raw, signature)) return ResponseEntity.status(401).body(Map.of("error", "Invalid signature"));
        try {
            JsonNode root = mapper.readTree(raw);
            int inserted = 0;
            if (root == null || !root.isObject()) return ResponseEntity.badRequest().body(Map.of("error", "Invalid event"));
            for (JsonNode entry : root.path("entry")) for (JsonNode change : entry.path("changes")) {
                JsonNode value = change.path("value");
                inserted += storeIds(value.path("messages"), "message");
                inserted += storeIds(value.path("statuses"), "status");
            }
            return ResponseEntity.ok(Map.of("accepted", true, "newEvents", inserted));
        } catch (Exception e) { return ResponseEntity.badRequest().body(Map.of("error", "Invalid event JSON")); }
    }

    private int storeIds(JsonNode nodes, String kind) {
        int count = 0;
        if (!nodes.isArray()) return count;
        for (JsonNode node : nodes) {
            String id = node.path("id").asText("");
            if (!id.isBlank()) count += jdbc.update(
                    "INSERT INTO inbound_events(event_hash,kind) VALUES(?,?) ON CONFLICT DO NOTHING",
                    Hashing.sha256(kind + ":" + id + ":" + ("status".equals(kind) ? node.path("status").asText("") : "")), kind);
        }
        return count;
    }
}
