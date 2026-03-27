import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from graph.nodes.log_analyst import log_analyst_node
from graph.nodes.runbook import runbook_node
from graph.nodes.blast_radius import blast_radius_node
from graph.nodes.comms import comms_node, revise_comms


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_alert():
    return {
        "alert_id": "test-001",
        "service_name": "auth-service",
        "severity": "P1",
        "error_type": "ConnectionTimeout",
        "log_snippet": "ERROR: connection timed out after 30s",
        "timestamp": "2026-03-26T00:00:00Z",
    }


def make_successful_log_finding():
    return {
        "agent_id": "log_analyst",
        "status": "success",
        "root_cause": "db_timeout",
        "confidence": 0.9,
        "justification": "Clear repeated timeout error in logs",
        "resolution_steps": ["Restart connection pool"],
        "evidence": ["ERROR: connection timed out after 30s"],
        "timestamp": "2026-03-26T00:00:00+00:00",
    }


def make_valid_log_analyst_json():
    return json.dumps({
        "agent_id": "log_analyst",
        "status": "success",
        "root_cause": "db_timeout",
        "confidence": 0.88,
        "justification": "Repeated DB timeout errors detected",
        "resolution_steps": ["Check DB connection pool", "Restart service"],
        "evidence": ["ERROR: connection timed out after 30s"],
        "timestamp": "",
    })


def make_valid_blast_radius_json():
    blast_detail = json.dumps({
        "affected_users": 1500,
        "regions": ["us-central1"],
        "downstream_services": ["payment-service"],
        "severity_tier": "high",
        "revenue_per_minute": 250.0,
    })
    return json.dumps({
        "agent_id": "blast_radius",
        "status": "success",
        "root_cause": None,
        "confidence": 0.82,
        "justification": "Metrics indicate significant user impact",
        "resolution_steps": [],
        "evidence": [blast_detail],
        "timestamp": "",
    })


def make_llm_response(content: str):
    mock_response = MagicMock()
    mock_response.content = content
    return mock_response


# ---------------------------------------------------------------------------
# log_analyst tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_log_analyst_timeout():
    state = {"alert": make_alert(), "loop_count": 0, "runbook_result": None}
    with patch("graph.nodes.log_analyst.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await log_analyst_node(state)
    finding = result["log_analysis"]
    assert finding["status"] == "timeout"
    assert finding["confidence"] == 0.0


@pytest.mark.asyncio
async def test_log_analyst_invalid_json():
    state = {"alert": make_alert(), "loop_count": 0, "runbook_result": None}
    with patch("graph.nodes.log_analyst.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=make_llm_response("not json"))
        result = await log_analyst_node(state)
    finding = result["log_analysis"]
    assert finding["status"] == "error"


@pytest.mark.asyncio
async def test_log_analyst_loop_context():
    state = {
        "alert": make_alert(),
        "loop_count": 1,
        "runbook_result": {
            "agent_id": "runbook",
            "status": "no_match",
            "root_cause": None,
            "confidence": 0.0,
            "justification": "No runbook found",
            "resolution_steps": [],
            "evidence": [],
            "timestamp": "2026-03-26T00:00:00+00:00",
        },
    }
    captured_prompt = {}
    with patch("graph.nodes.log_analyst.llm") as mock_llm:
        async def capture(prompt, **kwargs):
            captured_prompt["value"] = prompt
            return make_llm_response(make_valid_log_analyst_json())
        mock_llm.ainvoke = capture
        await log_analyst_node(state)
    assert "PRIOR RUNBOOK SEARCH" in captured_prompt["value"]


@pytest.mark.asyncio
async def test_log_analyst_no_loop_context():
    state = {"alert": make_alert(), "loop_count": 0, "runbook_result": None}
    captured_prompt = {}
    with patch("graph.nodes.log_analyst.llm") as mock_llm:
        async def capture(prompt, **kwargs):
            captured_prompt["value"] = prompt
            return make_llm_response(make_valid_log_analyst_json())
        mock_llm.ainvoke = capture
        await log_analyst_node(state)
    assert "PRIOR RUNBOOK SEARCH" not in captured_prompt["value"]


# ---------------------------------------------------------------------------
# runbook tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_runbook_no_match():
    state = {"log_analysis": make_successful_log_finding()}
    with patch("graph.nodes.runbook.vectorstore") as mock_vs:
        mock_vs.similarity_search_with_score.return_value = []
        result = await runbook_node(state)
    assert result["runbook_result"]["status"] == "no_match"


@pytest.mark.asyncio
async def test_runbook_skipped():
    error_finding = {**make_successful_log_finding(), "status": "error"}
    state = {"log_analysis": error_finding}
    with patch("graph.nodes.runbook.vectorstore") as mock_vs:
        result = await runbook_node(state)
        mock_vs.similarity_search_with_score.assert_not_called()
    assert result["runbook_result"]["status"] == "no_match"


@pytest.mark.asyncio
async def test_runbook_success():
    state = {"log_analysis": make_successful_log_finding()}
    mock_doc = MagicMock()
    mock_doc.page_content = "Runbook: restart the DB connection pool.\nStep 1: Check pool.\nStep 2: Restart."
    mock_doc.metadata = {"title": "DB Connection Pool Runbook"}

    steps_json = json.dumps(["Step 1: Check pool", "Step 2: Restart service"])

    with patch("graph.nodes.runbook.vectorstore") as mock_vs, \
         patch("graph.nodes.runbook.llm") as mock_llm:
        mock_vs.similarity_search_with_score.return_value = [(mock_doc, 0.4)]
        mock_llm.ainvoke = AsyncMock(return_value=make_llm_response(steps_json))
        result = await runbook_node(state)

    finding = result["runbook_result"]
    assert finding["status"] == "success"
    assert len(finding["resolution_steps"]) > 0


@pytest.mark.asyncio
async def test_runbook_timeout():
    state = {"log_analysis": make_successful_log_finding()}
    mock_doc = MagicMock()
    mock_doc.page_content = "Some runbook content"
    mock_doc.metadata = {"title": "Runbook"}

    with patch("graph.nodes.runbook.vectorstore") as mock_vs, \
         patch("graph.nodes.runbook.llm") as mock_llm:
        mock_vs.similarity_search_with_score.return_value = [(mock_doc, 0.4)]
        mock_llm.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await runbook_node(state)

    assert result["runbook_result"]["status"] == "timeout"


# ---------------------------------------------------------------------------
# blast_radius tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blast_radius_timeout():
    state = {"alert": make_alert()}
    with patch("graph.nodes.blast_radius.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(side_effect=asyncio.TimeoutError())
        result = await blast_radius_node(state)
    assert result["blast_radius"]["status"] == "timeout"
    assert result["blast_radius"]["confidence"] == 0.0


@pytest.mark.asyncio
async def test_blast_radius_success():
    state = {"alert": make_alert()}
    with patch("graph.nodes.blast_radius.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(
            return_value=make_llm_response(make_valid_blast_radius_json())
        )
        result = await blast_radius_node(state)

    finding = result["blast_radius"]
    assert finding["status"] == "success"
    assert len(finding["evidence"]) > 0
    # evidence[0] must be a valid JSON string with the required blast radius keys
    blast_detail = json.loads(finding["evidence"][0])
    assert "affected_users" in blast_detail
    assert "regions" in blast_detail
    assert "downstream_services" in blast_detail
    assert "severity_tier" in blast_detail
    assert "revenue_per_minute" in blast_detail


# ---------------------------------------------------------------------------
# comms tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_comms_initial():
    state = {"alert": make_alert()}
    comms_response = json.dumps({
        "status_page": "We are investigating elevated error rates on auth-service.",
        "slack_message": "[P1] auth-service is experiencing ConnectionTimeout. Investigation underway.",
    })
    with patch("graph.nodes.comms.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=make_llm_response(comms_response))
        result = await comms_node(state)

    draft = result["comms_drafts"]
    assert draft["revised"] is False
    assert draft["status_page"] != ""
    assert draft["slack_message"] != ""


@pytest.mark.asyncio
async def test_comms_revised():
    blast_detail = json.dumps({
        "affected_users": 1000,
        "regions": ["us-central1"],
        "downstream_services": [],
        "severity_tier": "high",
        "revenue_per_minute": 100.0,
    })
    state = {
        "alert": make_alert(),
        "log_analysis": {**make_successful_log_finding(), "root_cause": "db_timeout"},
        "blast_radius": {
            "agent_id": "blast_radius",
            "status": "success",
            "root_cause": None,
            "confidence": 0.8,
            "justification": "Impact confirmed",
            "resolution_steps": [],
            "evidence": [blast_detail],
            "timestamp": "2026-03-26T00:00:00+00:00",
        },
        "comms_drafts": {
            "status_page": "Investigating elevated errors.",
            "slack_message": "P1 incident in progress.",
            "revised": False,
        },
        "final_decision": "escalate",
    }
    revised_response = json.dumps({
        "status_page": "Root cause identified: db_timeout. Team is actively working on resolution.",
        "slack_message": "[P1] auth-service root cause: db_timeout. Escalating to on-call.",
    })
    with patch("graph.nodes.comms.llm") as mock_llm:
        mock_llm.ainvoke = AsyncMock(return_value=make_llm_response(revised_response))
        result = await revise_comms(state)

    draft = result["comms_drafts"]
    assert draft["revised"] is True
    assert draft["status_page"] != ""
    assert draft["slack_message"] != ""
