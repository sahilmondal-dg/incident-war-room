from datetime import datetime, timezone

import store

_KNOWN_NODES = {
    "parse_alert",
    "log_analyst",
    "runbook",
    "blast_radius",
    "comms",
    "coordinator_arbiter",
    "auto_resolve",
    "escalate",
}

# Maps node name to the state key it writes its AgentFinding into
_NODE_OUTPUT_KEY: dict[str, str] = {
    "log_analyst": "log_analysis",
    "runbook": "runbook_result",
    "blast_radius": "blast_radius",
    "comms": "comms_drafts",
    "coordinator_arbiter": None,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def publish(incident_id: str, event: dict) -> None:
    queue = store.sse_queues.get(incident_id)
    if queue is not None:
        queue.put_nowait(event)


def map_langgraph_event(raw: dict) -> dict | None:
    event_type = raw.get("event")
    name = raw.get("name")

    if name not in _KNOWN_NODES:
        return None

    if event_type == "on_chain_start":
        return {
            "event": "node_start",
            "node": name,
            "timestamp": _now_iso(),
        }

    if event_type == "on_chain_end":
        mapped: dict = {
            "event": "node_complete",
            "node": name,
            "timestamp": _now_iso(),
        }

        output_key = _NODE_OUTPUT_KEY.get(name)
        if output_key:
            output = raw.get("data", {}).get("output") or {}
            finding = output.get(output_key)
            if isinstance(finding, dict):
                if "confidence" in finding:
                    mapped["confidence"] = finding["confidence"]
                if "status" in finding:
                    mapped["status"] = finding["status"]
        elif name == "coordinator_arbiter":
            output = raw.get("data", {}).get("output") or {}
            if "final_decision" in output:
                mapped["final_decision"] = output["final_decision"]
            if "conflict_detected" in output:
                mapped["conflict_detected"] = output["conflict_detected"]

        return mapped

    return None
