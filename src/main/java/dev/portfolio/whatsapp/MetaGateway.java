package dev.portfolio.whatsapp;

public interface MetaGateway {
    MetaResult sendText(String recipient, String text);
    record MetaResult(int status, int retryAfterSeconds, String messageId) {
        public boolean accepted() { return status >= 200 && status < 300; }
    }
}
