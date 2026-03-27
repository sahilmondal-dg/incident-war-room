import React from "react";
import type { AgentStatus } from "../types/incident";
import { ConfidenceBar } from "./ConfidenceBar";

interface AgentStatusPanelProps {
  agentStatuses: Record<string, AgentStatus>;
  findings: Record<string, any>;
}

interface AgentConfig {
  id: string;
  label: string;
  icon: string;
}

const PARALLEL_AGENTS: AgentConfig[] = [
  { id: "log_analyst",  label: "Log Analyst",   icon: "⬡" },
  { id: "runbook",      label: "Runbook",        icon: "⬡" },
  { id: "blast_radius", label: "Blast Radius",   icon: "⬡" },
  { id: "comms",        label: "Comms",          icon: "⬡" },
];

const COORDINATOR: AgentConfig = { id: "coordinator_arbiter", label: "Coordinator / Arbiter", icon: "⬡" };

function statusDot(status: AgentStatus): string {
  switch (status) {
    case "running":  return "bg-amber-400 animate-pulse shadow-[0_0_6px_theme(colors.amber.400)]";
    case "success":  return "bg-emerald-400 shadow-[0_0_6px_theme(colors.emerald.400)]";
    case "no_match": return "bg-orange-400";
    case "error":
    case "timeout":  return "bg-red-500";
    case "conflict": return "bg-red-500 animate-pulse";
    default:         return "bg-[#2a2b35]";
  }
}

function statusLabel(status: AgentStatus): string {
  switch (status) {
    case "idle":      return "IDLE";
    case "running":   return "RUNNING";
    case "success":   return "SUCCESS";
    case "no_match":  return "NO MATCH";
    case "error":     return "ERROR";
    case "timeout":   return "TIMEOUT";
    case "conflict":  return "CONFLICT";
    default:          return status.toUpperCase();
  }
}

function statusTextColor(status: AgentStatus): string {
  switch (status) {
    case "running":  return "text-amber-400";
    case "success":  return "text-emerald-400";
    case "no_match": return "text-orange-400";
    case "error":
    case "timeout":  return "text-red-400";
    case "conflict": return "text-red-400";
    default:         return "text-[#6b6c7a]";
  }
}

function tileBorder(status: AgentStatus): string {
  switch (status) {
    case "running":  return "border-amber-500/40";
    case "success":  return "border-emerald-500/40";
    case "no_match": return "border-orange-500/40";
    case "error":
    case "timeout":  return "border-red-500/40";
    case "conflict": return "border-red-500 border-2";
    default:         return "border-[#2a2b35]";
  }
}

function AgentTile({ id, label, agentStatuses, findings }: AgentConfig & AgentStatusPanelProps) {
  const status: AgentStatus = agentStatuses[id] ?? "idle";
  const finding = findings[id];
  const confidence: number | null =
    finding && typeof finding.confidence === "number" ? finding.confidence : null;

  // Short justification — first 90 chars
  const justification: string | null =
    finding?.justification
      ? String(finding.justification).slice(0, 90) + (finding.justification.length > 90 ? "…" : "")
      : null;

  const rootCause: string | null = finding?.root_cause ?? null;

  return (
    <div className={`flex flex-col gap-2.5 rounded-lg border bg-[#12131a] p-3.5 transition-colors ${tileBorder(status)}`}>
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className={`h-2 w-2 flex-shrink-0 rounded-full ${statusDot(status)}`} />
          <span className="text-xs font-semibold text-[#c9cad4] truncate font-mono">{label}</span>
        </div>
        <span className={`text-[10px] font-mono font-bold tracking-widest flex-shrink-0 ${statusTextColor(status)}`}>
          {statusLabel(status)}
        </span>
      </div>

      {/* Confidence bar */}
      {confidence !== null && (
        <ConfidenceBar confidence={confidence} label="confidence" />
      )}

      {/* Root cause */}
      {rootCause && (
        <p className="text-xs font-mono text-cyan-400 truncate">
          <span className="text-[#6b6c7a]">cause: </span>{rootCause}
        </p>
      )}

      {/* Justification snippet */}
      {justification && (
        <p className="text-[11px] text-[#6b6c7a] leading-relaxed line-clamp-2 font-mono">
          {justification}
        </p>
      )}

      {/* Idle placeholder */}
      {status === "idle" && !finding && (
        <p className="text-[11px] text-[#3a3b45] font-mono italic">awaiting…</p>
      )}
    </div>
  );
}

export function AgentStatusPanel({ agentStatuses, findings }: AgentStatusPanelProps) {
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        {PARALLEL_AGENTS.map((agent) => (
          <AgentTile
            key={agent.id}
            {...agent}
            agentStatuses={agentStatuses}
            findings={findings}
          />
        ))}
      </div>
      <AgentTile
        {...COORDINATOR}
        agentStatuses={agentStatuses}
        findings={findings}
      />
    </div>
  );
}
