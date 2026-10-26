package dev.portfolio.whatsapp;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class MessageServiceTest {
    MessageStore store;
    DiagnosticStore diagnostics;
    MetaGateway meta;
    MessageService service;
    @BeforeEach void setup() {
        store = mock(MessageStore.class);
        diagnostics = mock(DiagnosticStore.class);
        meta = mock(MetaGateway.class);
        service = new MessageService(store, meta, diagnostics, 2, 3000, millis -> {});
    }
    @Test void successfulSendReturnsReceipt() {
        when(store.reserve(anyString(), anyString())).thenReturn(true);
        when(meta.sendText("447700900001", "hello")).thenReturn(new MetaGateway.MetaResult(200,0,"wamid.123"));
        var result = service.send("key-1", "447700900001", "hello");
        assertEquals("SENT",result.state());
        assertEquals("wamid.123",result.providerMessageId());
        verify(meta,times(1)).sendText(anyString(),anyString());
    }
    @Test void duplicateReturnsStoredResultWithoutMetaCall() {
        when(store.reserve(anyString(), anyString())).thenReturn(false);
        String digest = Hashing.sha256("447700900001\nhello");
        when(store.find(anyString())).thenReturn(Optional.of(new MessageStore.Receipt(digest,"SENT","wamid.123")));
        assertTrue(service.send("repeat","447700900001","hello").duplicate());
        verifyNoInteractions(meta);
    }
    @Test void differentPayloadForSameKeyIsConflict() {
        when(store.reserve(anyString(), anyString())).thenReturn(false);
        when(store.find(anyString())).thenReturn(Optional.of(new MessageStore.Receipt("not-a-match","SENT",null)));
        assertThrows(ResponseStatusException.class, () -> service.send("repeat","447700900001","changed"));
        verifyNoInteractions(meta);
    }
    @Test void onlyRateLimitResponseIsRetried() {
        when(store.reserve(anyString(),anyString())).thenReturn(true);
        when(meta.sendText(anyString(),anyString())).thenReturn(
                new MetaGateway.MetaResult(429,0,null),new MetaGateway.MetaResult(200,0,"wamid.ok"));
        assertEquals("SENT",service.send("retry","447700900001","hello").state());
        verify(meta,times(2)).sendText(anyString(),anyString());
    }
    @Test void exhausted429RemainsRejected() {
        when(store.reserve(anyString(),anyString())).thenReturn(true);
        when(meta.sendText(anyString(),anyString())).thenReturn(new MetaGateway.MetaResult(429,0,null));
        assertEquals("REJECTED", service.send("limit","447700900001","hello").state());
        verify(meta,times(3)).sendText(anyString(),anyString());
        verify(diagnostics).record("RATE_LIMIT",429,"send_text");
    }
    @Test void ambiguousServerErrorIsNotRetried() {
        when(store.reserve(anyString(),anyString())).thenReturn(true);
        when(meta.sendText(anyString(),anyString())).thenReturn(new MetaGateway.MetaResult(502,0,null));
        assertEquals("UNKNOWN",service.send("ambiguous","447700900001","hello").state());
        verify(meta,times(1)).sendText(anyString(),anyString());
    }
    @Test void transportExceptionDoesNotRetry() {
        when(store.reserve(anyString(),anyString())).thenReturn(true);
        when(meta.sendText(anyString(),anyString())).thenThrow(new RuntimeException("DO NOT LOG TOKEN"));
        assertEquals("UNKNOWN",service.send("timeout","447700900001","hello").state());
        verify(meta,times(1)).sendText(anyString(),anyString());
        verify(diagnostics).record("TRANSPORT_OR_CONFIG",null,"send_text");
    }
    @Test void missingIdempotencyKeyNeverCallsProvider() {
        assertThrows(ResponseStatusException.class, () -> service.send("","447700900001","hello"));
        verifyNoInteractions(meta);
    }
}
