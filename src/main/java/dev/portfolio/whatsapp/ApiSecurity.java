package dev.portfolio.whatsapp;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
public class ApiSecurity {
    private final String key;
    public ApiSecurity(@Value("${integration.api-key:}") String key) { this.key = key; }
    public void require(String auth) {
        if (key.isBlank() || auth == null || !auth.startsWith("Bearer ") ||
                !MessageDigest.isEqual(key.getBytes(StandardCharsets.UTF_8),
                        auth.substring(7).getBytes(StandardCharsets.UTF_8))) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED, "Invalid local API token");
        }
    }
}
