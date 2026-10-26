from app.agent import RUNBOOK, call_tool, offline_report
from app.db import Ledger


def test_agent_tools_read_only_and_synthetic(settings):
    ledger = Ledger(settings.database_path)
    ledger.log("meta", "rate_limited", "130429", "Back off", 1)
    assert call_tool(ledger, "count_error_codes", {}) == [{"error_code": "130429", "total": 1}]
    assert call_tool(ledger, "get_recent_errors", {"limit": 10})[0]["error_code"] == "130429"
    assert "Throughput" in call_tool(ledger, "get_runbook", {"code": "130429"})["guidance"]
    assert call_tool(ledger, "execute_shell", {}) == {"error": "Tool not allowed"}
    assert "130429" in offline_report(ledger)


def test_runbook_includes_critical_errors():
    for code in ("130429", "131056", "190", "bad_signature", "unknown_outcome"):
        assert code in RUNBOOK


def test_actual_function_call_loop_is_bounded_and_read_only(settings):
    from types import SimpleNamespace
    from app.agent import diagnose
    import json
    ledger = Ledger(settings.database_path)
    ledger.log("meta", "rate_limited", "130429", "Back off", 1)
    calls = []

    class StubResponseClient:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                output = [
                    SimpleNamespace(type="function_call", name="get_recent_errors", arguments='{"limit":5}', call_id="c1"),
                    SimpleNamespace(type="function_call", name="count_error_codes", arguments='{}', call_id="c2"),
                ]
                return SimpleNamespace(output=output, output_text="")
            return SimpleNamespace(output=[], output_text="Rate limit detected. Use backoff and human review.")

    fake = SimpleNamespace(responses=StubResponseClient())
    report = diagnose(ledger, "test-model", client=fake)
    assert "Rate limit" in report
    assert len(calls) == 2
    assert calls[0]["store"] is False
    outputs = [i for i in calls[1]["input"] if isinstance(i, dict) and i.get("type") == "function_call_output"]
    assert len(outputs) == 2
    assert any(json.loads(o["output"])[0]["error_code"] == "130429" for o in outputs if o["call_id"] == "c1")
