import React, { useEffect, useState } from "react";
import { AgentStatusPanel } from "./components/AgentStatusPanel";
import { BriefPanel } from "./components/BriefPanel";
import { CommsPanel } from "./components/CommsPanel";
import { DemoTrigger } from "./components/DemoTrigger";
import { IncidentFeed } from "./components/IncidentFeed";
import { TimelineView } from "./components/TimelineView";
import { useIncidentStream } from "./hooks/useIncidentStream";
import type { CommsDraft, IncidentSummary } from "./types/incident";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, string> = {
    P0: "text-red-400 border-red-500/50 bg-red-950/30",
    P1: "text-orange-400 border-orange-500/50 bg-orange-950/30",
    P2: "text-amber-400 border-amber-500/50 bg-amber-950/30",
  };
  const cls = colors[severity] ?? "text-[#6b6c7a] border-[#2a2b35] bg-[#12131a]";
  return (
    <span className={`inline-flex px-2 py-0.5 rounded border text-xs font-mono font-bold ${cls}`}>
      {severity}
    </span>
  );
}

function DecisionBanner({ decision }: { decision: string | null }) {
  if (!decision) return null;
  if (decision === "auto_resolve") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-emerald-500/40 bg-emerald-950/20 text-xs font-mono font-semibold text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
        AUTO-RESOLVED
      </span>
    );
  }
  if (decision === "escalate") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-red-500/40 bg-red-950/20 text-xs font-mono font-semibold text-red-400">
        <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
        ESCALATED
      </span>
    );
  }
  if (decision === "loop") {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-amber-500/40 bg-amber-950/20 text-xs font-mono font-semibold text-amber-400">
        <span className="h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" />
        LOOPING
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded border border-[#2a2b35] text-xs font-mono text-[#6b6c7a]">
      <span className="h-1.5 w-1.5 rounded-full bg-[#3a3b45] animate-pulse" />
      IN PROGRESS
    </span>
  );
}

export default function App() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [incidentState, setIncidentState] = useState<IncidentSummary | null>(null);

  const { events, agentStatuses, finalDecision, isComplete } = useIncidentStream(selectedId);

  useEffect(() => {
    if (!selectedId) {
      setIncidentState(null);
      return;
    }
    async function fetchState() {
      try {
        const resp = await fetch(`${API_BASE}/api/incidents/${selectedId}`);
        if (resp.ok) {
          const data: IncidentSummary = await resp.json();
          setIncidentState(data);
        }
      } catch {
        // Ignore — incident may not be created yet
      }
    }
    fetchState();
  }, [selectedId, isComplete]);

  function handleIncidentCreated(incidentId: string) {
    setSelectedId(incidentId);
    setIncidentState(null);
  }

  const findings: Record<string, any> = {
    log_analyst:         incidentState?.log_analysis  ?? null,
    runbook:             incidentState?.runbook_result ?? null,
    blast_radius:        incidentState?.blast_radius   ?? null,
    comms:               incidentState?.comms_drafts   ?? null,
    coordinator_arbiter: null,
  };

  const commsDraft = (incidentState?.comms_drafts as CommsDraft | null) ?? null;
  const activeDecision = finalDecision ?? incidentState?.final_decision ?? null;

  return (
    <div className="flex h-screen bg-[#0b0c10] overflow-hidden text-[#c9cad4]">

      {/* ── Left sidebar ─────────────────────────────────────────────── */}
      <aside className="w-[260px] flex-shrink-0 flex flex-col gap-6 overflow-y-auto border-r border-[#1e1f28] bg-[#0e0f17] p-4">
        {/* Wordmark */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-cyan-400 text-xs font-mono">▲</span>
            <h1 className="text-sm font-mono font-semibold text-[#e0e0e0] tracking-wide">
              Incident War Room
            </h1>
          </div>
          <p className="text-[10px] font-mono text-[#3a3b45] pl-4">multi-agent triage system</p>
        </div>

        <DemoTrigger onIncidentCreated={handleIncidentCreated} />

        <div className="border-t border-[#1e1f28] pt-4">
          <IncidentFeed
            onSelectIncident={setSelectedId}
            selectedId={selectedId}
          />
        </div>
      </aside>

      {/* ── Main content ─────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto p-5">
        {!selectedId ? (
          <div className="flex h-full items-center justify-center">
            <div className="text-center space-y-2">
              <p className="text-sm font-mono text-[#3a3b45]">
                $ select or trigger an incident to begin
              </p>
              <p className="text-xs font-mono text-[#2a2b35]">
                POST /api/webhook/alert
              </p>
            </div>
          </div>
        ) : (
          <div className="max-w-5xl mx-auto space-y-4">

            {/* Alert header bar */}
            {incidentState?.alert && (
              <div className="rounded-lg border border-[#1e1f28] bg-[#0e0f17] px-4 py-3 flex items-center gap-3 flex-wrap">
                <SeverityBadge severity={incidentState.alert.severity} />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-mono font-semibold text-[#e0e0e0] truncate">
                    {incidentState.alert.service_name}
                    <span className="text-[#6b6c7a] mx-1">·</span>
                    {incidentState.alert.error_type}
                  </p>
                  <p className="text-[10px] font-mono text-[#3a3b45]">{incidentState.alert.alert_id}</p>
                </div>
                <DecisionBanner decision={activeDecision} />
                {incidentState.conflict_detected && (
                  <span className="text-[10px] font-mono text-red-400 border border-red-500/40 px-2 py-0.5 rounded">
                    CONFLICT · loop {incidentState.loop_count}
                  </span>
                )}
              </div>
            )}

            {/* Agent panel + Timeline */}
            <div className="grid grid-cols-2 gap-4">
              <section>
                <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a] mb-2">
                  agent status
                </p>
                <AgentStatusPanel agentStatuses={agentStatuses} findings={findings} />
              </section>

              <section>
                <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a] mb-2">
                  activity log
                </p>
                <div className="rounded-lg border border-[#1e1f28] bg-[#0b0c10] p-3 max-h-[340px] overflow-y-auto">
                  <TimelineView events={events} />
                </div>
              </section>
            </div>

            {/* Incident brief */}
            <section>
              <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a] mb-2">
                incident brief
              </p>
              <BriefPanel
                incidentBrief={incidentState?.incident_brief ?? null}
                resolutionPlan={incidentState?.resolution_plan ?? null}
                finalDecision={activeDecision}
              />
            </section>

            {/* Comms panel */}
            <section>
              <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a] mb-2">
                communications draft
              </p>
              <div className="rounded-lg border border-[#1e1f28] bg-[#0e0f17] p-4">
                <CommsPanel commsDraft={commsDraft} />
              </div>
            </section>

          </div>
        )}
      </main>
    </div>
  );
}
