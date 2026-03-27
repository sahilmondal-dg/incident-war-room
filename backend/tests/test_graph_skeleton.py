import pytest
from graph.graph import graph
from graph.state import IncidentState, AlertPayload


def build_test_state() -> IncidentState:
    alert: AlertPayload = {
        "alert_id": "test-001",
        "service_name": "auth-service",
        "severity": "P1",
        "error_type": "ConnectionTimeout",
        "log_snippet": "ERROR: connection timed out after 30s",
        "timestamp": "2026-03-26T00:00:00Z",
    }
    return IncidentState(
        alert=alert,
        log_analysis=None,
        runbook_result=None,
        blast_radius=None,
        comms_drafts=None,
        conflict_detected=False,
        conflict_reason=None,
        loop_count=0,
        final_decision=None,
        incident_brief=None,
        resolution_plan=None,
    )


@pytest.mark.asyncio
async def test_graph_reaches_terminal_state():
    result = await graph.ainvoke(build_test_state())
    assert result["final_decision"] in ("auto_resolve", "escalate")


@pytest.mark.asyncio
async def test_log_analysis_populated():
    result = await graph.ainvoke(build_test_state())
    assert result["log_analysis"] is not None
    assert result["log_analysis"]["agent_id"] == "log_analyst"


@pytest.mark.asyncio
async def test_all_parallel_agents_populated():
    result = await graph.ainvoke(build_test_state())
    assert result["runbook_result"] is not None
    assert result["blast_radius"] is not None
    assert result["comms_drafts"] is not None


@pytest.mark.asyncio
async def test_loop_never_in_terminal():
    result = await graph.ainvoke(build_test_state())
    assert result["final_decision"] != "loop"
