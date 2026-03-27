export type AgentId =
  | "parse_alert"
  | "log_analyst"
  | "runbook"
  | "blast_radius"
  | "comms"
  | "coordinator_arbiter"
  | "auto_resolve"
  | "escalate";

export type AgentStatus =
  | "idle"
  | "running"
  | "success"
  | "no_match"
  | "timeout"
  | "error"
  | "conflict";

export type FinalDecision = "auto_resolve" | "escalate" | "loop" | null;

export interface AgentFinding {
  agent_id: string;
  status: "success" | "no_match" | "timeout" | "error";
  root_cause: string | null;
  confidence: number;
  justification: string;
  resolution_steps: string[];
  evidence: string[];
  timestamp: string;
}

export interface CommsDraft {
  status_page: string;
  slack_message: string;
  revised: boolean;
}

export interface IncidentSummary {
  alert: {
    alert_id: string;
    service_name: string;
    severity: "P0" | "P1" | "P2" | "P3";
    error_type: string;
    log_snippet: string;
    timestamp: string;
  };
  log_analysis: AgentFinding | null;
  runbook_result: AgentFinding | null;
  blast_radius: AgentFinding | null;
  comms_drafts: CommsDraft | null;
  conflict_detected: boolean;
  conflict_reason: string | null;
  loop_count: number;
  final_decision: FinalDecision;
  incident_brief: string | null;
  resolution_plan: string | null;
}

// Discriminated union of all SSE event shapes emitted by the backend
export type StreamEvent =
  | {
      event: "node_start";
      node: AgentId;
      timestamp: string;
    }
  | {
      event: "node_complete";
      node: AgentId;
      timestamp: string;
      status?: AgentStatus;
      confidence?: number;
      final_decision?: FinalDecision;
      conflict_detected?: boolean;
    }
  | {
      event: "decision";
      decision: FinalDecision;
      timestamp: string;
    }
  | {
      event: "done";
      timestamp: string;
    };
