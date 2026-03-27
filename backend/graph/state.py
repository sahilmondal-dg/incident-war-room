from typing import Literal, Optional
from typing import TypedDict


class AgentFinding(TypedDict):
    agent_id: str
    status: Literal["success", "no_match", "timeout", "error"]
    root_cause: Optional[str]
    confidence: float
    justification: str
    resolution_steps: list[str]
    evidence: list[str]
    timestamp: str


class CommsDraft(TypedDict):
    status_page: str
    slack_message: str
    revised: bool


class AlertPayload(TypedDict):
    alert_id: str
    service_name: str
    severity: Literal["P0", "P1", "P2", "P3"]
    error_type: str
    log_snippet: str
    timestamp: str


class IncidentState(TypedDict):
    alert: AlertPayload
    log_analysis: Optional[AgentFinding]
    runbook_result: Optional[AgentFinding]
    blast_radius: Optional[AgentFinding]
    comms_drafts: Optional[CommsDraft]
    conflict_detected: bool
    conflict_reason: Optional[str]
    loop_count: int
    final_decision: Optional[Literal["auto_resolve", "escalate", "loop"]]
    incident_brief: Optional[str]
    resolution_plan: Optional[str]
