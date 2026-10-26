package dev.portfolio.whatsapp;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import java.util.Map;

@Component
public class HttpMetaGateway implements MetaGateway {
    private final RestClient client;
    private final ObjectMapper mapper;
    private final String token, phoneId, graphVersion;

    public HttpMetaGateway(RestClient.Builder builder, ObjectMapper mapper,
                           @Value("${integration.meta-base-url}") String url,
                           @Value("${integration.meta-access-token:}") String token,
                           @Value("${integration.meta-phone-number-id:}") String phoneId,
                           @Value("${integration.meta-graph-version:v23.0}") String graphVersion) {
        this.client = builder.baseUrl(url).build();
        this.mapper = mapper;
        this.token = token;
        this.phoneId = phoneId;
        this.graphVersion = graphVersion;
    }

    public MetaResult sendText(String recipient, String text) {
        if (token.isBlank() || phoneId.isBlank()) throw new IllegalStateException("Meta test credentials not configured");
        var payload = Map.of("messaging_product", "whatsapp", "to", recipient, "type", "text",
                "text", Map.of("body", text));
        return client.post().uri("/{version}/{phoneId}/messages", graphVersion, phoneId)
                .contentType(MediaType.APPLICATION_JSON)
                .header("Authorization", "Bearer " + token).body(payload)
                .exchange((request, response) -> {
                    int status = response.getStatusCode().value();
                    int retryAfter = 0;
                    String value = response.getHeaders().getFirst("Retry-After");
                    if (value != null) {
                        try { retryAfter = Math.min(60, Math.max(0, Integer.parseInt(value))); }
                        catch (NumberFormatException ignored) { /* HTTP-date not parsed; bounded default backoff */ }
                    }
                    String messageId = null;
                    if (status >= 200 && status < 300) {
                        try {
                            JsonNode json = mapper.readTree(response.getBody());
                            messageId = json.path("messages").path(0).path("id").asText(null);
                        } catch (Exception ignored) { /* a missing id is not a logging reason */ }
                    }
                    // Never persist or log the provider response body; it may include sensitive data.
                    return new MetaResult(status, retryAfter, messageId);
                });
    }
}
