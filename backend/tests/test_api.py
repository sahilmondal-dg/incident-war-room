import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock, mock_open
from fastapi.testclient import TestClient

import store
import main
from main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_store():
    """Clear all in-memory store state before each test."""
    store.incidents.clear()
    store.sse_queues.clear()
    store.dedup_index.clear()
    store.dedup_timestamps.clear()
    yield


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _alert_payload(**overrides) -> dict:
    base = {
        "alert_id": "test-api-001",
        "service_name": "auth-service",
        "severity": "P1",
        "error_type": "ConnectionTimeout",
        "log_snippet": "ERROR: connection timed out after 30s",
        "timestamp": "2026-03-26T00:00:00Z",
    }
    return {**base, **overrides}


async def _noop_graph_task(incident_id: str, state: dict) -> None:
    """Background task replacement that immediately closes the SSE queue."""
    if incident_id in store.sse_queues:
        store.sse_queues[incident_id].put_nowait(None)


def _log_finding(confidence: float = 0.88, root_cause: str = "db_timeout") -> dict:
    return {
        "agent_id": "log_analyst",
        "status": "success",
        "root_cause": root_cause,
        "confidence": confidence,
        "justification": "Repeated timeout errors observed",
        "resolution_steps": ["Restart connection pool"],
        "evidence": ["ERROR: connection timed out"],
        "timestamp": "2026-03-26T00:00:00+00:00",
    }


# ---------------------------------------------------------------------------
# Basic endpoint tests
# ---------------------------------------------------------------------------

def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_webhook_missing_field(client):
    """Incomplete body must return HTTP 422."""
    incomplete = {
        "alert_id": "x",
        "service_name": "svc",
        # severity, error_type, log_snippet, timestamp missing
    }
    with patch("main.run_graph_task", new=_noop_graph_task):
        resp = client.post("/webhook/alert", json=incomplete)
    assert resp.status_code == 422


def test_webhook_valid(client):
    """Valid payload returns incident_id and stream_url."""
    with patch("main.run_graph_task", new=_noop_graph_task):
        resp = client.post("/webhook/alert", json=_alert_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert "incident_id" in body
    assert body["stream_url"] == f"/incidents/{body['incident_id']}/stream"
    assert body["deduplicated"] is False


def test_deduplication(client):
    """Second identical alert within dedup window returns same incident_id."""
    with patch("main.run_graph_task", new=_noop_graph_task):
        resp1 = client.post("/webhook/alert", json=_alert_payload())
        resp2 = client.post("/webhook/alert", json=_alert_payload())

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    body1, body2 = resp1.json(), resp2.json()
    assert body1["deduplicated"] is False
    assert body2["deduplicated"] is True
    assert body2["incident_id"] == body1["incident_id"]


def test_get_incident(client):
    """GET /incidents/{id} returns stored incident state after POST."""
    with patch("main.run_graph_task", new=_noop_graph_task):
        post_resp = client.post("/webhook/alert", json=_alert_payload())
    incident_id = post_resp.json()["incident_id"]

    get_resp = client.get(f"/incidents/{incident_id}")
    assert get_resp.status_code == 200
    state = get_resp.json()
    assert state["alert"]["service_name"] == "auth-service"
    assert state["alert"]["severity"] == "P1"


def test_get_incident_not_found(client):
    resp = client.get("/incidents/nonexistent-id")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Demo trigger
# ---------------------------------------------------------------------------

def test_demo_trigger_scenario_a(client):
    """POST /demo/trigger/scenario_a returns incident_id using fixture data."""
    fixture = _alert_payload(
        alert_id="scenario-a-001",
        service_name="db-service",
        severity="P1",
        error_type="ConnectionPoolExhausted",
        log_snippet="ERROR: connection pool exhausted after 30s",
    )
    with patch("builtins.open", mock_open(read_data=json.dumps(fixture))), \
         patch("main.run_graph_task", new=_noop_graph_task):
        resp = client.post("/demo/trigger/scenario_a")

    assert resp.status_code == 200
    body = resp.json()
    assert "incident_id" in body
    assert body["deduplicated"] is False


def test_demo_trigger_unknown_scenario(client):
    resp = client.get("/demo/trigger/scenario_z")
    assert resp.status_code in (404, 405)


# ---------------------------------------------------------------------------
# P2 routing (INV-055: P2/P3 → log_analyst only)
# ---------------------------------------------------------------------------

def test_severity_p2_routing(client):
    """
    INV-055: P2 alerts must only trigger log_analyst.
    The graph mock returns only a log_analyst output event,
    simulating correct P2 routing. Parallel agents (runbook_result,
    blast_radius, comms_drafts) must remain None in the final state.
    """
    log_result = _log_finding(confidence=0.85, root_cause="network")

    async def p2_astream_events(state, *, version="v2"):
        # Simulate P2 routing: only log_analyst output
        yield {
            "event": "on_chain_end",
            "name": "log_analyst",
            "data": {"output": {"log_analysis": log_result}},
        }

    mock_graph = MagicMock()
    mock_graph.astream_events = p2_astream_events

    with patch("main.graph", mock_graph):
        resp = client.post("/webhook/alert", json=_alert_payload(severity="P2"))

    assert resp.status_code == 200
    incident_id = resp.json()["incident_id"]

    state = store.get_incident(incident_id)
    assert state is not None
    assert state["log_analysis"] is not None
    assert state["log_analysis"]["agent_id"] == "log_analyst"
    # P2: parallel agents must not have been invoked
    assert state.get("runbook_result") is None
    assert state.get("blast_radius") is None
    assert state.get("comms_drafts") is None
