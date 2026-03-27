import React, { useState } from "react";
import type { CommsDraft } from "../types/incident";

interface CommsPanelProps {
  commsDraft: CommsDraft | null;
}

type Tab = "status_page" | "slack";

export function CommsPanel({ commsDraft }: CommsPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>("status_page");

  if (!commsDraft) {
    return (
      <div className="flex items-center justify-center h-24 rounded-lg border border-dashed border-[#2a2b35] bg-[#12131a]">
        <p className="text-xs text-[#3a3b45] italic font-mono">$ awaiting communications draft…</p>
      </div>
    );
  }

  const content = activeTab === "status_page" ? commsDraft.status_page : commsDraft.slack_message;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        {/* Tabs */}
        <div className="flex gap-1 rounded-md bg-[#0b0c10] border border-[#2a2b35] p-0.5">
          {(["status_page", "slack"] as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 rounded text-xs font-mono transition-colors ${
                activeTab === tab
                  ? "bg-[#1a1b23] text-cyan-400"
                  : "text-[#6b6c7a] hover:text-[#c9cad4]"
              }`}
            >
              {tab === "status_page" ? "status_page" : "slack_msg"}
            </button>
          ))}
        </div>

        {commsDraft.revised && (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-emerald-900/40 text-emerald-400 border border-emerald-500/30">
            ✔ REVISED
          </span>
        )}
      </div>

      <textarea
        readOnly
        value={content}
        rows={6}
        className="w-full rounded-lg border border-[#2a2b35] bg-[#0b0c10] px-3 py-2.5 text-xs text-[#c9cad4] font-mono resize-none focus:outline-none focus:border-cyan-500/40"
      />
    </div>
  );
}
