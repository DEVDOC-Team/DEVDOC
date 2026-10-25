import React from "react";
import { Check, Circle, Lock } from "lucide-react";
import { StatusPulse } from "./StatusPulse";
import "./ui.css";

export interface PhaseItem {
  id: string;
  name: string;
  sub: string;
  state: "done" | "active" | "pending" | "gated";
}

export interface PhaseRailProps {
  phases?: PhaseItem[];
  className?: string;
}

const DEFAULT_PHASES: PhaseItem[] = [
  { id: "detect", name: "Detect", sub: "done", state: "done" },
  { id: "investigate", name: "Investigate", sub: "done", state: "done" },
  { id: "evidence", name: "Evidence", sub: "done", state: "done" },
  { id: "reason", name: "Reason", sub: "done", state: "done" },
  { id: "diagnose", name: "Diagnose", sub: "emitted", state: "active" },
  { id: "fix", name: "Fix proposal", sub: "next", state: "pending" },
  { id: "verify", name: "Verify", sub: "opt-in", state: "pending" },
  { id: "approval", name: "Approval", sub: "human", state: "pending" },
  { id: "resolve", name: "Resolve", sub: "gated", state: "gated" },
];

export const PhaseRail: React.FC<PhaseRailProps> = ({
  phases = DEFAULT_PHASES,
  className = "",
}) => {
  return (
    <nav className={`phase-rail ${className}`.trim()} aria-label="Investigation pipeline stages">
      {phases.map((ph) => {
        let icon = <Circle size={14} />;
        if (ph.state === "done") {
          icon = <Check size={14} strokeWidth={2.5} />;
        } else if (ph.state === "active") {
          icon = <StatusPulse status="accent" />;
        } else if (ph.state === "gated") {
          icon = <Lock size={13} />;
        }

        return (
          <div key={ph.id} className={`phase-step ${ph.state}`}>
            {icon}
            <span className="phase-labels">
              {ph.name}
              <em>{ph.sub}</em>
            </span>
          </div>
        );
      })}
    </nav>
  );
};
