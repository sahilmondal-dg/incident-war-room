import React from "react";
import type { StreamEvent } from "../types/incident";

interface TimelineViewProps {
  events: StreamEvent[];
}

function isConflictOrLoop(event: StreamEvent): boolean {
  if (event.event === "node_complete" && event.conflict_detected) return true;
  if (event.event === "decision" && event.decision === "loop") return true;
  return false;
}

function eventPrefix(event: StreamEvent): string {
  switch (event.event) {
    case "node_start":    return "►";
    case "node_complete": return event.conflict_detected ? "✖" : "✔";
    case "decision":      return "◆";
    case "done":          return "■";
    default:              return "·";
  }
}

function eventLabel(event: StreamEvent): string {
  switch (event.event) {
    case "node_start":
      return `${event.node} started`;
    case "node_complete": {
      const status = event.conflict_detected ? "CONFLICT" : (event.status ?? "complete");
      const conf = event.confidence !== undefined ? ` [${Math.round(event.confidence * 100)}%]` : "";
      return `${event.node} → ${status}${conf}`;
    }
    case "decision":
      return `decision: ${event.decision ?? "unknown"}`;
    case "done":
      return "pipeline complete";
  }
}

function prefixColor(event: StreamEvent): string {
  if (isConflictOrLoop(event)) return "text-red-400";
  if (event.event === "decision") {
    if (event.decision === "auto_resolve") return "text-emerald-400";
    if (event.decision === "escalate") return "text-red-400";
    return "text-amber-400";
  }
  if (event.event === "node_start") return "text-[#6b6c7a]";
  if (event.event === "done") return "text-cyan-400";
  if (event.event === "node_complete") {
    if (event.status === "error" || event.status === "timeout") return "text-red-400";
    if (event.status === "no_match") return "text-orange-400";
    return "text-emerald-400";
  }
  return "text-[#6b6c7a]";
}

function labelColor(event: StreamEvent): string {
  if (isConflictOrLoop(event)) return "text-red-300 font-bold";
  if (event.event === "decision") {
    if (event.decision === "auto_resolve") return "text-emerald-300 font-semibold";
    if (event.decision === "escalate") return "text-red-300 font-semibold";
    return "text-amber-300 font-semibold";
  }
  if (event.event === "node_start") return "text-[#6b6c7a]";
  if (event.event === "done") return "text-cyan-300";
  if (event.event === "node_complete") {
    if (event.status === "error" || event.status === "timeout") return "text-red-300";
    if (event.status === "no_match") return "text-orange-300";
    return "text-[#c9cad4]";
  }
  return "text-[#6b6c7a]";
}

function formatTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return ts;
  }
}

export function TimelineView({ events }: TimelineViewProps) {
  if (events.length === 0) {
    return (
      <div className="text-xs text-[#3a3b45] italic font-mono px-1 py-2">
        $ waiting for events…
      </div>
    );
  }

  return (
    <ol className="space-y-0.5 font-mono text-xs">
      {events.map((event, idx) => (
        <li key={idx} className="flex items-start gap-2 py-1 px-1 hover:bg-[#1a1b23] rounded transition-colors">
          <span className={`flex-shrink-0 w-3 mt-px ${prefixColor(event)}`}>
            {eventPrefix(event)}
          </span>
          <span className={`flex-1 ${labelColor(event)}`}>
            {eventLabel(event)}
          </span>
          {"timestamp" in event && event.timestamp && (
            <span className="flex-shrink-0 text-[10px] text-[#3a3b45]">
              {formatTime(event.timestamp)}
            </span>
          )}
        </li>
      ))}
    </ol>
  );
}
