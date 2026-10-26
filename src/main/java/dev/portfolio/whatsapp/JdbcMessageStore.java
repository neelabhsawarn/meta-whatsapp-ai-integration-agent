package dev.portfolio.whatsapp;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import java.util.Optional;

@Repository
public class JdbcMessageStore implements MessageStore {
    private final JdbcTemplate jdbc;
    public JdbcMessageStore(JdbcTemplate jdbc) { this.jdbc = jdbc; }
    @Override public boolean reserve(String keyHash, String payloadHash) {
        return jdbc.update("""
                INSERT INTO outbound_messages(key_hash, payload_hash, state)
                VALUES (?, ?, 'PROCESSING') ON CONFLICT (key_hash) DO NOTHING
                """, keyHash, payloadHash) == 1;
    }
    @Override public Optional<Receipt> find(String keyHash) {
        return jdbc.query("SELECT payload_hash, state, provider_message_id FROM outbound_messages WHERE key_hash = ?",
                (rs, row) -> new Receipt(rs.getString(1), rs.getString(2), rs.getString(3)), keyHash)
                .stream().findFirst();
    }
    @Override public void finish(String keyHash, String state, String providerId) {
        jdbc.update("UPDATE outbound_messages SET state=?, provider_message_id=?, updated_at=now() WHERE key_hash=?",
                state, providerId, keyHash);
    }
}
