import React from "react";
import type { FinalDecision } from "../types/incident";

interface BriefPanelProps {
  incidentBrief: string | null;
  resolutionPlan: string | null;
  finalDecision: FinalDecision;
}

function parseResolutionSteps(plan: string): string[] {
  return plan
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function BriefPanel({ incidentBrief, resolutionPlan, finalDecision }: BriefPanelProps) {
  const hasContent = incidentBrief !== null || resolutionPlan !== null;

  if (!hasContent) {
    return (
      <div className="flex items-center justify-center h-24 rounded-lg border border-dashed border-[#2a2b35] bg-[#12131a]">
        <p className="text-xs text-[#3a3b45] italic font-mono">$ awaiting agent findings…</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">

      {/* Auto-resolve: numbered steps */}
      {finalDecision === "auto_resolve" && resolutionPlan && (
        <div className="rounded-lg border border-emerald-500/30 bg-emerald-950/20 p-4">
          <p className="text-xs font-mono font-semibold text-emerald-400 mb-3 uppercase tracking-wider">
            ✔ Resolution Steps
          </p>
          <ol className="space-y-2 list-none">
            {parseResolutionSteps(resolutionPlan).map((step, idx) => (
              <li key={idx} className="flex items-start gap-2.5 text-xs font-mono text-[#c9cad4]">
                <span className="flex-shrink-0 text-emerald-500 w-4 text-right">{idx + 1}.</span>
                <span>{step.replace(/^\d+\.\s*/, "")}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Escalate: red banner */}
      {finalDecision === "escalate" && (
        <div className="flex items-center gap-3 rounded-lg border border-red-500/40 bg-red-950/20 px-4 py-3">
          <span className="text-red-400 text-sm">⚠</span>
          <span className="text-xs font-mono font-semibold text-red-300">ESCALATED — paging on-call engineer</span>
        </div>
      )}

      {/* Incident brief */}
      {incidentBrief && (
        <div className="rounded-lg border border-[#2a2b35] bg-[#0b0c10] overflow-auto max-h-96">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-[#2a2b35]">
            <span className="text-[10px] font-mono text-[#6b6c7a] uppercase tracking-wider">incident brief</span>
          </div>
          <pre className="p-4 text-xs font-mono text-[#c9cad4] whitespace-pre-wrap break-words leading-relaxed">
            {incidentBrief}
          </pre>
        </div>
      )}

    </div>
  );
}
