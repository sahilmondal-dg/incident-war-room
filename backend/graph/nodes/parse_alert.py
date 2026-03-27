async def parse_alert_node(state: dict) -> dict:
    alert = {**state["alert"], "severity": state["alert"]["severity"].upper()}
    return {
        "alert": alert,
        "loop_count": 0,
        "conflict_detected": False,
        "conflict_reason": None,
        "log_analysis": None,
        "runbook_result": None,
        "blast_radius": None,
        "comms_drafts": None,
        "final_decision": None,
        "incident_brief": None,
        "resolution_plan": None,
    }
