import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentId, AgentStatus, FinalDecision, StreamEvent } from "../types/incident";

type AgentStatuses = Record<AgentId, AgentStatus>;

const INITIAL_STATUSES: AgentStatuses = {
  parse_alert: "idle",
  log_analyst: "idle",
  runbook: "idle",
  blast_radius: "idle",
  comms: "idle",
  coordinator_arbiter: "idle",
  auto_resolve: "idle",
  escalate: "idle",
};

interface IncidentStreamResult {
  events: StreamEvent[];
  agentStatuses: AgentStatuses;
  finalDecision: FinalDecision;
  isComplete: boolean;
}

export function useIncidentStream(incidentId: string | null): IncidentStreamResult {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatuses>({ ...INITIAL_STATUSES });
  const [finalDecision, setFinalDecision] = useState<FinalDecision>(null);
  const [isComplete, setIsComplete] = useState(false);

  const esRef = useRef<EventSource | null>(null);

  const handleEvent = useCallback((raw: StreamEvent) => {
    setEvents((prev) => [...prev, raw]);

    switch (raw.event) {
      case "node_start":
        setAgentStatuses((prev) => ({ ...prev, [raw.node]: "running" }));
        break;

      case "node_complete": {
        let status: AgentStatus;
        if (raw.conflict_detected) {
          status = "conflict";
        } else if (raw.status) {
          status = raw.status;
        } else {
          status = "success";
        }
        setAgentStatuses((prev) => ({ ...prev, [raw.node]: status }));
        break;
      }

      case "decision":
        setFinalDecision(raw.decision);
        break;

      case "done":
        setIsComplete(true);
        esRef.current?.close();
        esRef.current = null;
        break;
    }
  }, []);

  useEffect(() => {
    if (!incidentId) {
      setEvents([]);
      setAgentStatuses({ ...INITIAL_STATUSES });
      setFinalDecision(null);
      setIsComplete(false);
      return;
    }

    // Reset state for new incident
    setEvents([]);
    setAgentStatuses({ ...INITIAL_STATUSES });
    setFinalDecision(null);
    setIsComplete(false);

    const es = new EventSource(`/api/incidents/${incidentId}/stream`);
    esRef.current = es;

    es.onmessage = (msg: MessageEvent) => {
      try {
        const parsed: StreamEvent = JSON.parse(msg.data);
        handleEvent(parsed);
      } catch {
        // Ignore malformed events
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [incidentId, handleEvent]);

  return { events, agentStatuses, finalDecision, isComplete };
}
