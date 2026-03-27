import json
import pytest
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock, MagicMock

from graph.graph import graph


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _llm_response(content: str) -> MagicMock:
    r = MagicMock()
    r.content = content
    return r


def _log_json(confidence: float, root_cause: str) -> str:
    return json.dumps({
        "agent_id": "log_analyst",
        "status": "success",
        "root_cause": root_cause,
        "confidence": confidence,
        "justification": f"Strong {root_cause} signal detected in logs",
        "resolution_steps": [f"Investigate {root_cause}"],
        "evidence": [f"ERROR: {root_cause} error observed"],
        "timestamp": "",
    })


def _blast_json(confidence: float) -> str:
    blast_detail = json.dumps({
        "affected_users": 800,
        "regions": ["us-central1"],
        "downstream_services": ["payment-service"],
        "severity_tier": "high",
        "revenue_per_minute": 150.0,
    })
    return json.dumps({
        "agent_id": "blast_radius",
        "status": "success",
        "root_cause": None,
        "confidence": confidence,
        "justification": "Metrics indicate user impact",
        "resolution_steps": [],
        "evidence": [blast_detail],
        "timestamp": "",
    })


def _steps_json() -> str:
    return json.dumps(["Step 1: Check DB connection pool", "Step 2: Restart service"])


def _comms_json() -> str:
    return json.dumps({
        "status_page": "We are investigating elevated error rates.",
        "slack_message": "[P1] Incident in progress. Investigation underway.",
    })


# ---------------------------------------------------------------------------
# Mock context managers
# ---------------------------------------------------------------------------

@contextmanager
def auto_resolve_mocks():
    """
    log: confidence=0.91, root_cause=db_timeout (status=success)
    runbook vectorstore: Document score=0.88 → status=success, resolution_steps non-empty
    blast_radius: confidence=0.85
    Spread = |0.91-0.85| = 0.06 < 0.4 — no conflict
    Mean = (0.91+0.88+0.85)/3 = 0.88 >= 0.75 — auto_resolve
    """
    mock_doc = MagicMock()
    mock_doc.page_content = "DB Pool Recovery runbook: restart connection pool."
    mock_doc.metadata = {"title": "DB Pool Recovery"}

    with patch("graph.nodes.log_analyst.llm") as log_llm, \
         patch("graph.nodes.runbook.llm") as rb_llm, \
         patch("graph.nodes.runbook.vectorstore") as rb_vs, \
         patch("graph.nodes.blast_radius.llm") as br_llm, \
         patch("graph.nodes.blast_radius.load_metrics") as load_metrics, \
         patch("graph.nodes.comms.llm") as comms_llm:

        log_llm.ainvoke = AsyncMock(
            return_value=_llm_response(_log_json(confidence=0.91, root_cause="db_timeout"))
        )
        rb_vs.similarity_search_with_score.return_value = [(mock_doc, 0.45)]
        rb_llm.ainvoke = AsyncMock(return_value=_llm_response(_steps_json()))
        br_llm.ainvoke = AsyncMock(
            return_value=_llm_response(_blast_json(confidence=0.85))
        )
        load_metrics.return_value = {
            "error_rate": 0.15,
            "active_users": 800,
            "revenue_per_minute": 150.0,
            "regions": ["us-central1"],
            "downstream_services": ["payment-service"],
        }
        comms_llm.ainvoke = AsyncMock(return_value=_llm_response(_comms_json()))
        yield


@contextmanager
def conflict_escalate_mocks():
    """
    log: confidence=0.82, root_cause=oom (status=success)
    runbook vectorstore: empty results → status=no_match, confidence=0.0
    blast_radius: confidence=0.85
    Rule 1 fires: log.conf=0.82 >= 0.7 AND rb.status=no_match → conflict every pass
    Loops MAX_LOOPS (2) times, then escalates with loop_count=2
    """
    with patch("graph.nodes.log_analyst.llm") as log_llm, \
         patch("graph.nodes.runbook.vectorstore") as rb_vs, \
         patch("graph.nodes.blast_radius.llm") as br_llm, \
         patch("graph.nodes.blast_radius.load_metrics") as load_metrics, \
         patch("graph.nodes.comms.llm") as comms_llm:

        log_llm.ainvoke = AsyncMock(
            return_value=_llm_response(_log_json(confidence=0.82, root_cause="oom"))
        )
        rb_vs.similarity_search_with_score.return_value = []
        br_llm.ainvoke = AsyncMock(
            return_value=_llm_response(_blast_json(confidence=0.85))
        )
        load_metrics.return_value = {
            "error_rate": 0.3,
            "active_users": 1200,
            "revenue_per_minute": 200.0,
            "regions": ["us-central1"],
            "downstream_services": [],
        }
        comms_llm.ainvoke = AsyncMock(return_value=_llm_response(_comms_json()))
        yield


def _make_state() -> dict:
    return {
        "alert": {
            "alert_id": "int-test-001",
            "service_name": "auth-service",
            "severity": "P1",
            "error_type": "ConnectionTimeout",
            "log_snippet": "ERROR: connection timed out after 30s",
            "timestamp": "2026-03-26T00:00:00Z",
        },
        "log_analysis": None,
        "runbook_result": None,
        "blast_radius": None,
        "comms_drafts": None,
        "conflict_detected": False,
        "conflict_reason": None,
        "loop_count": 0,
        "final_decision": None,
        "incident_brief": None,
        "resolution_plan": None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_scenario_auto_resolve():
    with auto_resolve_mocks():
        result = await graph.ainvoke(_make_state())

    assert result["final_decision"] == "auto_resolve"
    assert result["loop_count"] == 0
    assert result["resolution_plan"] is not None
    assert result["incident_brief"] is not None


@pytest.mark.asyncio
async def test_scenario_conflict_escalate():
    with conflict_escalate_mocks():
        result = await graph.ainvoke(_make_state())

    assert result["final_decision"] == "escalate"
    assert result["conflict_detected"] is True
    assert result["conflict_reason"] is not None
    assert result["loop_count"] == 2


@pytest.mark.asyncio
async def test_loop_never_terminal():
    with auto_resolve_mocks():
        result_ar = await graph.ainvoke(_make_state())

    with conflict_escalate_mocks():
        result_ce = await graph.ainvoke(_make_state())

    assert result_ar["final_decision"] != "loop"
    assert result_ce["final_decision"] != "loop"


@pytest.mark.asyncio
async def test_incident_brief_always_set():
    with auto_resolve_mocks():
        result_ar = await graph.ainvoke(_make_state())

    with conflict_escalate_mocks():
        result_ce = await graph.ainvoke(_make_state())

    assert result_ar["incident_brief"] is not None
    assert len(result_ar["incident_brief"]) > 0
    assert result_ce["incident_brief"] is not None
    assert len(result_ce["incident_brief"]) > 0
