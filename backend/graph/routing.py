from langgraph.constants import Send


def fan_out_after_log(state: dict) -> list[Send]:
    return [
        Send("runbook", {"log_finding": state["log_analysis"]}),
        Send("blast_radius", {"alert": state["alert"]}),
        Send("comms", {"alert": state["alert"]}),
    ]


def route_after_arbitration(state: dict) -> str:
    decision = state["final_decision"]
    if decision == "auto_resolve":
        return "auto_resolve"
    if decision == "escalate":
        return "escalate"
    if decision == "loop":
        return "loop"
    raise ValueError(f"Invalid final_decision: {decision}")
