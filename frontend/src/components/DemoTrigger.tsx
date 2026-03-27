import React, { useState } from "react";

const API_BASE = import.meta.env.VITE_API_URL ?? "";

interface DemoTriggerProps {
  onIncidentCreated: (incidentId: string) => void;
}

interface Scenario {
  key: "scenario_a" | "scenario_b" | "scenario_c";
  label: string;
  description: string;
  severity: string;
  severityColor: string;
}

const SCENARIOS: Scenario[] = [
  {
    key: "scenario_a",
    label: "Scenario A",
    description: "DB Pool Timeout",
    severity: "P1",
    severityColor: "text-orange-400 border-orange-500/40 bg-orange-950/20",
  },
  {
    key: "scenario_b",
    label: "Scenario B",
    description: "OOM / No Runbook",
    severity: "P0",
    severityColor: "text-red-400 border-red-500/40 bg-red-950/20",
  },
  {
    key: "scenario_c",
    label: "Scenario C",
    description: "Auth DNS Failure",
    severity: "P1",
    severityColor: "text-orange-400 border-orange-500/40 bg-orange-950/20",
  },
];

export function DemoTrigger({ onIncidentCreated }: DemoTriggerProps) {
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function trigger(scenario: string) {
    setLoading(scenario);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/demo/trigger/${scenario}`, {
        method: "POST",
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      onIncidentCreated(data.incident_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-mono font-semibold uppercase tracking-widest text-[#6b6c7a] px-1 mb-2">
        demo scenarios
      </p>

      {SCENARIOS.map((s) => {
        const isLoading = loading === s.key;
        return (
          <button
            key={s.key}
            onClick={() => trigger(s.key)}
            disabled={loading !== null}
            className={`w-full flex items-center justify-between rounded-md border px-3 py-2 text-left transition-colors
              ${isLoading
                ? "border-cyan-500/40 bg-cyan-950/20 cursor-wait"
                : "border-[#2a2b35] bg-[#12131a] hover:border-cyan-500/40 hover:bg-[#1a1b23] cursor-pointer"
              }
              disabled:opacity-50`}
          >
            <div className="min-w-0">
              <p className="text-xs font-mono font-medium text-[#c9cad4]">{s.label}</p>
              <p className="text-[11px] font-mono text-[#6b6c7a]">{s.description}</p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0 ml-2">
              <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded border ${s.severityColor}`}>
                {s.severity}
              </span>
              {isLoading ? (
                <svg className="h-3.5 w-3.5 animate-spin text-cyan-400" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3v4a8 8 0 100 16v-4l-3 3 3 3v-4a8 8 0 01-8-8z" />
                </svg>
              ) : (
                <span className="text-[#3a3b45] text-xs">›</span>
              )}
            </div>
          </button>
        );
      })}

      {error && (
        <p className="text-[11px] font-mono text-red-400 px-1">error: {error}</p>
      )}
    </div>
  );
}
