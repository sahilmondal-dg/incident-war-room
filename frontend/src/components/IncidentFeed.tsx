import React, { useCallback, useEffect, useState } from "react";
import type { FinalDecision, IncidentSummary } from "../types/incident";

const API_BASE = import.meta.env.VITE_API_URL ?? "";
const POLL_MS = 3000;

interface IncidentFeedProps {
  onSelectIncident: (incidentId: string) => void;
  selectedId: string | null;
}

function severityColor(severity: string): string {
  switch (severity) {
    case "P0": return "text-red-400 border-red-500/40";
    case "P1": return "text-orange-400 border-orange-500/40";
    case "P2": return "text-amber-400 border-amber-500/40";
    default:   return "text-[#6b6c7a] border-[#2a2b35]";
  }
}

function decisionDot(decision: FinalDecision): string {
  switch (decision) {
    case "auto_resolve": return "bg-emerald-400";
    case "escalate":     return "bg-red-500";
    case "loop":         return "bg-amber-400 animate-pulse";
    default:             return "bg-[#3a3b45]";
  }
}

function decisionLabel(decision: FinalDecision): string {
  switch (decision) {
    case "auto_resolve": return "resolved";
    case "escalate":     return "escalated";
    case "loop":         return "looping…";
    default:             return "in progress";
  }
}

function decisionTextColor(decision: FinalDecision): string {
  switch (decision) {
    case "auto_resolve": return "text-emerald-400";
    case "escalate":     return "text-red-400";
    case "loop":         return "text-amber-400";
    default:             return "text-[#6b6c7a]";
  }
}

export function IncidentFeed({ onSelectIncident, selectedId }: IncidentFeedProps) {
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [fetchError, setFetchError] = useState(false);

  const fetchIncidents = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/incidents`);
      if (!resp.ok) throw new Error();
      const data: IncidentSummary[] = await resp.json();
      setIncidents([...data].reverse());
      setFetchError(false);
    } catch {
      setFetchError(true);
    }
  }, []);

  useEffect(() => {
    fetchIncidents();
    const id = setInterval(fetchIncidents, POLL_MS);
    return () => clearInterval(id);
  }, [fetchIncidents]);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between px-1 mb-2">
        <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a]">
          incidents
        </p>
        {fetchError && (
          <span className="text-[10px] font-mono text-red-400">offline</span>
        )}
      </div>

      {incidents.length === 0 && !fetchError && (
        <p className="text-xs text-[#3a3b45] italic font-mono px-1">no incidents yet.</p>
      )}

      <ul className="space-y-1">
        {incidents.map((inc) => {
          const rowId: string = (inc as any).incident_id ?? inc.alert?.alert_id ?? "";
          const isSelected = rowId === selectedId;

          return (
            <li key={rowId}>
              <button
                onClick={() => onSelectIncident(rowId)}
                className={`w-full rounded-md border px-3 py-2 text-left transition-colors
                  ${isSelected
                    ? "border-cyan-500/50 bg-cyan-950/20"
                    : "border-[#2a2b35] bg-[#12131a] hover:border-[#3a3b45] hover:bg-[#1a1b23]"
                  }`}
              >
                <div className="flex items-center gap-2 mb-0.5">
                  <span className={`text-[10px] font-mono font-bold border rounded px-1 py-0.5 ${severityColor(inc.alert?.severity)}`}>
                    {inc.alert?.severity ?? "?"}
                  </span>
                  <span className="text-xs font-mono font-medium text-[#c9cad4] truncate">
                    {inc.alert?.service_name ?? "unknown"}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-mono text-[#6b6c7a] truncate">
                    {inc.alert?.error_type ?? ""}
                  </span>
                  <div className="flex items-center gap-1.5 flex-shrink-0">
                    <span className={`h-1.5 w-1.5 rounded-full ${decisionDot(inc.final_decision)}`} />
                    <span className={`text-[10px] font-mono ${decisionTextColor(inc.final_decision)}`}>
                      {decisionLabel(inc.final_decision)}
                    </span>
                  </div>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
