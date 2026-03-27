import React from "react";

interface ConfidenceBarProps {
  confidence: number | null;
  label: string;
}

function barColor(confidence: number | null): string {
  if (confidence === null) return "bg-red-500";
  if (confidence >= 0.75) return "bg-emerald-400";
  if (confidence >= 0.5) return "bg-amber-400";
  return "bg-red-500";
}

function textColor(confidence: number | null): string {
  if (confidence === null) return "text-red-400";
  if (confidence >= 0.75) return "text-emerald-400";
  if (confidence >= 0.5) return "text-amber-400";
  return "text-red-400";
}

export function ConfidenceBar({ confidence, label }: ConfidenceBarProps) {
  const widthPct = confidence !== null ? Math.min(Math.max(confidence * 100, 0), 100) : 0;

  return (
    <div className="w-full space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-xs text-[#6b6c7a] font-mono uppercase tracking-wider">{label}</span>
        <span className={`text-xs font-mono font-semibold ${textColor(confidence)}`}>
          {confidence !== null ? `${Math.round(confidence * 100)}%` : "—"}
        </span>
      </div>
      <div className="w-full h-1.5 rounded-full bg-[#2a2b35]">
        <div
          className={`h-1.5 rounded-full transition-all duration-500 ${barColor(confidence)}`}
          style={{ width: `${widthPct}%` }}
        />
      </div>
    </div>
  );
}
