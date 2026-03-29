from statistics import mean
from typing import Optional

from config import (
    AUTO_RESOLVE_THRESHOLD,
    CONFIDENCE_THRESHOLD,
    MAX_LOOPS,
    MEAN_FLOOR,
    SPREAD_THRESHOLD,
)
from graph.nodes.comms import revise_comms


def detect_conflict(
    log: dict, rb: dict, br: dict, severity: str
) -> tuple[bool, Optional[str]]:
    # Rule 1: confident log analyst but runbook found nothing
    if log["confidence"] >= CONFIDENCE_THRESHOLD and rb["status"] == "no_match":
        return True, (
            "Log Analyst confident ({:.2f}) in '{}' but Runbook returned no_match.".format(
                log["confidence"], log.get("root_cause", "unknown")
            )
        )

    # Rule 2: confidence spread between log and blast radius too wide
    if abs(log["confidence"] - br["confidence"]) > SPREAD_THRESHOLD:
        return True, (
            "Confidence spread too high: Log={:.2f}, BlastRadius={:.2f}.".format(
                log["confidence"], br["confidence"]
            )
        )

    # Rule 3: P0 incident with any agent error or timeout
    if severity == "P0" and any(
        f["status"] in ("error", "timeout") for f in [log, rb, br]
    ):
        return True, "P0 incident with agent error or timeout."

    # Rule 4: mean LLM confidence below floor (exclude vector-based runbook confidence)
    mean_conf = mean([log["confidence"], br["confidence"]])
    if mean_conf < MEAN_FLOOR:
        return True, "Mean confidence {:.2f} below floor {}.".format(
            mean_conf, MEAN_FLOOR
        )

    return False, None


def can_auto_resolve(log: dict, rb: dict, br: dict) -> bool:
    if rb["status"] != "success":
        return False
    if len(rb.get("resolution_steps", [])) == 0:
        return False
    # Use only LLM-based confidences — runbook confidence is vector-distance-based
    # and is already gated by the status == "success" check above.
    mean_conf = mean([log["confidence"], br["confidence"]])
    return mean_conf >= AUTO_RESOLVE_THRESHOLD


def build_incident_brief(state: dict, decision: str) -> str:
    alert = state["alert"]
    log = state.get("log_analysis") or {}
    rb = state.get("runbook_result") or {}
    br = state.get("blast_radius") or {}
    comms = state.get("comms_drafts") or {}
    conflict_reason = state.get("conflict_reason") or "None"
    loop_count = state.get("loop_count", 0)

    br_evidence = br.get("evidence", [])
    blast_summary = br_evidence[0] if br_evidence else "No blast radius data"

    return (
        "# Incident Brief\n\n"
        "## Alert Summary\n"
        "- **Service:** {service}\n"
        "- **Severity:** {severity}\n"
        "- **Error Type:** {error_type}\n"
        "- **Alert ID:** {alert_id}\n"
        "- **Timestamp:** {ts}\n\n"
        "## Decision\n"
        "**{decision}**\n\n"
        "## Conflict\n"
        "- **Detected:** {conflict_detected}\n"
        "- **Reason:** {conflict_reason}\n"
        "- **Loop Count:** {loop_count}\n\n"
        "## Log Analysis\n"
        "- **Status:** {log_status}\n"
        "- **Root Cause:** {log_root_cause}\n"
        "- **Confidence:** {log_confidence}\n"
        "- **Justification:** {log_justification}\n\n"
        "## Runbook\n"
        "- **Status:** {rb_status}\n"
        "- **Matched:** {rb_root_cause}\n\n"
        "## Blast Radius\n"
        "{blast_summary}\n\n"
        "## Communications\n"
        "- **Status Page:** {status_page}\n"
    ).format(
        service=alert.get("service_name", "unknown"),
        severity=alert.get("severity", "unknown"),
        error_type=alert.get("error_type", "unknown"),
        alert_id=alert.get("alert_id", "unknown"),
        ts=alert.get("timestamp", "unknown"),
        decision=decision,
        conflict_detected=state.get("conflict_detected", False),
        conflict_reason=conflict_reason,
        loop_count=loop_count,
        log_status=log.get("status", "unknown"),
        log_root_cause=log.get("root_cause", "unknown"),
        log_confidence=log.get("confidence", 0.0),
        log_justification=log.get("justification", ""),
        rb_status=rb.get("status", "unknown"),
        rb_root_cause=rb.get("root_cause", "none"),
        blast_summary=blast_summary,
        status_page=comms.get("status_page", "unavailable"),
    )


async def coordinator_arbiter_node(state: dict) -> dict:
    log = state["log_analysis"]
    rb = state["runbook_result"]
    br = state["blast_radius"]
    loop = state.get("loop_count", 0)
    severity = state["alert"]["severity"]

    conflict, reason = detect_conflict(log, rb, br, severity)

    # Path 1: conflict + loops remaining
    if conflict and loop < MAX_LOOPS:
        return {
            "conflict_detected": True,
            "conflict_reason": reason,
            "loop_count": loop + 1,
            "final_decision": "loop",
        }

    # Path 2: conflict + max loops exhausted
    if conflict and loop >= MAX_LOOPS:
        return {
            "conflict_detected": True,
            "conflict_reason": reason,
            "loop_count": loop,
            "final_decision": "escalate",
            "incident_brief": build_incident_brief(state, "escalate"),
        }

    # Path 3: no conflict + auto-resolve conditions met
    if can_auto_resolve(log, rb, br):
        revised = await revise_comms({**state, "final_decision": "auto_resolve"})
        return {
            "conflict_detected": False,
            "final_decision": "auto_resolve",
            "resolution_plan": "\n".join(
                f"{i + 1}. {s}" for i, s in enumerate(rb["resolution_steps"])
            ),
            "incident_brief": build_incident_brief(state, "auto_resolve"),
            "comms_drafts": revised["comms_drafts"],
        }

    # Path 4: no conflict + low confidence (INV-020)
    return {
        "conflict_detected": False,
        "final_decision": "escalate",
        "incident_brief": build_incident_brief(state, "escalate"),
    }
