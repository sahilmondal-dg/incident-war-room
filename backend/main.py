# Run with --workers 1 only. See ARCHITECTURE.md §10.
import json
import os
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from graph.graph import graph
from graph.state import IncidentState
from sse import map_langgraph_event, publish
from store import (
    check_dedup,
    create_incident,
    get_all_incidents,
    get_incident,
    register_dedup,
    sse_queues,
    update_incident,
)

app = FastAPI(title="Incident War Room")

_FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "alerts")

_DEMO_SCENARIO_MAP = {
    "scenario_a": "scenario_a_db_pool",
    "scenario_b": "scenario_b_oom",
    "scenario_c": "scenario_c_auth_dns",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------

class AlertPayloadRequest(BaseModel):
    alert_id: str
    service_name: str
    severity: Literal["P0", "P1", "P2", "P3"]
    error_type: str
    log_snippet: str
    timestamp: str


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event() -> None:
    try:
        from tools.vectorstore import seed
        seed()
    except Exception as exc:
        print(f"[startup] Vectorstore seed skipped: {exc}")


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

async def run_graph_task(incident_id: str, state: dict) -> None:
    async for event in graph.astream_events(state, version="v2"):
        sse_event = map_langgraph_event(event)
        if sse_event:
            await publish(incident_id, sse_event)

        if event.get("event") == "on_chain_end":
            output = event.get("data", {}).get("output")
            if isinstance(output, dict):
                update_incident(incident_id, output)

    final_state = get_incident(incident_id) or {}
    await publish(
        incident_id,
        {
            "event": "decision",
            "decision": final_state.get("final_decision"),
            "timestamp": _now_iso(),
        },
    )
    await publish(incident_id, {"event": "done", "timestamp": _now_iso()})
    sse_queues[incident_id].put_nowait(None)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/webhook/alert")
async def webhook_alert(
    payload: AlertPayloadRequest, background_tasks: BackgroundTasks
) -> dict:
    dedup_id = check_dedup(payload.service_name, payload.error_type)
    if dedup_id:
        return {
            "incident_id": dedup_id,
            "deduplicated": True,
            "stream_url": f"/incidents/{dedup_id}/stream",
        }

    incident_id = str(uuid4())

    state: IncidentState = {
        "alert": {
            "alert_id": payload.alert_id,
            "service_name": payload.service_name,
            "severity": payload.severity,
            "error_type": payload.error_type,
            "log_snippet": payload.log_snippet,
            "timestamp": payload.timestamp,
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

    create_incident(incident_id, state)
    register_dedup(payload.service_name, payload.error_type, incident_id)
    background_tasks.add_task(run_graph_task, incident_id, state)

    return {
        "incident_id": incident_id,
        "stream_url": f"/incidents/{incident_id}/stream",
        "deduplicated": False,
    }


@app.get("/incidents")
async def list_incidents() -> list:
    return get_all_incidents()


@app.get("/incidents/{incident_id}")
async def get_incident_route(incident_id: str) -> dict:
    state = get_incident(incident_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return state


@app.get("/incidents/{incident_id}/stream")
async def stream_incident(incident_id: str) -> EventSourceResponse:
    if incident_id not in sse_queues:
        raise HTTPException(status_code=404, detail="Incident not found")

    queue = sse_queues[incident_id]

    async def event_generator():
        while True:
            event = await queue.get()
            if event is None:
                break
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@app.post("/demo/trigger/{scenario}")
async def demo_trigger(scenario: str, background_tasks: BackgroundTasks) -> dict:
    if scenario not in _DEMO_SCENARIO_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Valid: {list(_DEMO_SCENARIO_MAP)}",
        )

    fixture_name = _DEMO_SCENARIO_MAP[scenario]
    fixture_path = os.path.join(_FIXTURES_DIR, f"{fixture_name}.json")

    try:
        with open(fixture_path, "r") as f:
            raw = json.load(f)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail=f"Fixture file not found: {fixture_path}"
        )

    payload = AlertPayloadRequest(**raw)
    return await webhook_alert(payload, background_tasks)
