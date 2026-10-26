package dev.portfolio.whatsapp;

import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.testcontainers.postgresql.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.flywaydb.core.Flyway;
import static org.junit.jupiter.api.Assertions.*;

@Testcontainers(disabledWithoutDocker = true)
class DiagnosticStoreTest {
    @Container static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("integration_test").withUsername("test").withPassword("test");
    @Test void migrationAndSanitizedDiagnosisQueriesWork() {
        DriverManagerDataSource data = new DriverManagerDataSource(postgres.getJdbcUrl(), postgres.getUsername(),postgres.getPassword());
        Flyway.configure().dataSource(data).locations("classpath:db/migration").load().migrate();
        DiagnosticStore store = new DiagnosticStore(new JdbcTemplate(data));
        store.record("RATE_LIMIT",429,"send_text");
        var rows = store.recent(5);
        assertEquals("RATE_LIMIT", rows.get(0).category());
        assertEquals(429, rows.get(0).httpStatus());
        assertTrue(store.byId(rows.get(0).id()).isPresent());
    }
}
