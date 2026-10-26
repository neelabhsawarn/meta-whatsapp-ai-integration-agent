package dev.portfolio.whatsapp;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Optional;

@Repository
public class DiagnosticStore {
    private final JdbcTemplate jdbc;
    public DiagnosticStore(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public record Diagnostic(long id, String category, Integer httpStatus, String context, OffsetDateTime createdAt) {}

    public void record(String category, Integer httpStatus, String context) {
        // category and context are fixed application labels, never raw messages, numbers, or provider JSON.
        jdbc.update("INSERT INTO diagnostic_events(category, http_status, context) VALUES (?,?,?)",
                category, httpStatus, context);
    }
    public List<Diagnostic> recent(int limit) {
        return jdbc.query("SELECT id, category, http_status, context, created_at FROM diagnostic_events ORDER BY id DESC LIMIT ?",
                (rs, row) -> new Diagnostic(rs.getLong(1), rs.getString(2), (Integer) rs.getObject(3),
                        rs.getString(4), rs.getObject(5, OffsetDateTime.class)), Math.max(1, Math.min(50, limit)));
    }
    public Optional<Diagnostic> byId(long id) {
        return jdbc.query("SELECT id, category, http_status, context, created_at FROM diagnostic_events WHERE id=?",
                (rs, row) -> new Diagnostic(rs.getLong(1), rs.getString(2), (Integer) rs.getObject(3),
                        rs.getString(4), rs.getObject(5, OffsetDateTime.class)), id).stream().findFirst();
    }
}
