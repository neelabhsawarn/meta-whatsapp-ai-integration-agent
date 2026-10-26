package dev.portfolio.whatsapp;

import java.util.Optional;

public interface MessageStore {
    boolean reserve(String keyHash, String payloadHash);
    Optional<Receipt> find(String keyHash);
    void finish(String keyHash, String state, String providerId);
    record Receipt(String payloadHash, String state, String providerMessageId) {}
}
