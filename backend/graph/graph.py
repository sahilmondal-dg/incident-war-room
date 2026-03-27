from langgraph.graph import StateGraph, END

from graph.state import IncidentState
from graph.nodes.parse_alert import parse_alert_node
from graph.nodes.log_analyst import log_analyst_node
from graph.nodes.runbook import runbook_node
from graph.nodes.blast_radius import blast_radius_node
from graph.nodes.comms import comms_node
from graph.nodes.coordinator_arbiter import coordinator_arbiter_node
from graph.routing import fan_out_after_log, route_after_arbitration


async def _noop(state: dict) -> dict:
    """Terminal node — coordinator_arbiter already set all required fields."""
    return {}


builder = StateGraph(IncidentState)

builder.add_node("parse_alert", parse_alert_node)
builder.add_node("log_analyst", log_analyst_node)
builder.add_node("runbook", runbook_node)
builder.add_node("blast_radius", blast_radius_node)
builder.add_node("comms", comms_node)
builder.add_node("coordinator_arbiter", coordinator_arbiter_node)
builder.add_node("auto_resolve", _noop)
builder.add_node("escalate", _noop)

builder.set_entry_point("parse_alert")
builder.add_edge("parse_alert", "log_analyst")

builder.add_conditional_edges(
    "log_analyst",
    fan_out_after_log,
    ["runbook", "blast_radius", "comms"],
)

builder.add_edge("runbook", "coordinator_arbiter")
builder.add_edge("blast_radius", "coordinator_arbiter")
builder.add_edge("comms", "coordinator_arbiter")

builder.add_conditional_edges(
    "coordinator_arbiter",
    route_after_arbitration,
    {"auto_resolve": "auto_resolve", "escalate": "escalate", "loop": "log_analyst"},
)

builder.add_edge("auto_resolve", END)
builder.add_edge("escalate", END)

graph = builder.compile()

if __name__ == "__main__":
    print("Graph compile: OK")
