package dev.portfolio.whatsapp;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
public class ApiController {
    private final ApiSecurity security;
    private final MessageService messages;
    private final DiagnosticStore diagnostics;
    private final DiagnosticAgent agent;
    public ApiController(ApiSecurity security, MessageService messages, DiagnosticStore diagnostics, DiagnosticAgent agent) {
        this.security = security; this.messages = messages; this.diagnostics = diagnostics; this.agent = agent;
    }
    public record SendRequest(@NotBlank @Pattern(regexp = "[0-9]{6,16}") String to,
                              @NotBlank @Size(max = 1024) String text) {}
    public record DiagnosisRequest(@NotBlank @Size(max = 400) String question) {}

    @PostMapping("/messages")
    public ResponseEntity<MessageService.SendResult> send(@RequestHeader(value="Authorization",required=false) String auth,
                @RequestHeader(value="Idempotency-Key",required=false) String idempotencyKey,
                @Valid @RequestBody SendRequest request) {
        security.require(auth);
        MessageService.SendResult result = messages.send(idempotencyKey, request.to(), request.text());
        HttpStatus status = switch(result.state()) {
            case "SENT" -> HttpStatus.OK;
            case "REJECTED" -> HttpStatus.UNPROCESSABLE_ENTITY;
            default -> HttpStatus.ACCEPTED;
        };
        return ResponseEntity.status(status).body(result);
    }
    @GetMapping("/diagnostics")
    public List<DiagnosticStore.Diagnostic> list(@RequestHeader(value="Authorization",required=false) String auth,
                                                  @RequestParam(defaultValue="10") int limit) {
        security.require(auth); return diagnostics.recent(limit);
    }
    @PostMapping("/diagnose")
    public Map<String,String> diagnose(@RequestHeader(value="Authorization",required=false) String auth,
                                       @Valid @RequestBody DiagnosisRequest request) {
        security.require(auth);
        try { return Map.of("analysis", agent.diagnose(request.question())); }
        catch (IllegalStateException e) { throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, e.getMessage()); }
    }
}
