package dev.portfolio.whatsapp;

import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class ApiSecurityTest {
    @Test void permitsMatchingLocalBearer() { assertDoesNotThrow(() -> new ApiSecurity("private-key").require("Bearer private-key")); }
    @Test void deniesMissingOrWrongOrUnconfiguredKey() {
        assertThrows(ResponseStatusException.class, () -> new ApiSecurity("private-key").require(null));
        assertThrows(ResponseStatusException.class, () -> new ApiSecurity("private-key").require("Bearer wrong"));
        assertThrows(ResponseStatusException.class, () -> new ApiSecurity("").require("Bearer any"));
    }
}
