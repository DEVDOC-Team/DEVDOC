import React from "react";
import "../../styles/global.css";

export interface StatusPulseProps {
  status?: "ok" | "accent" | "warn" | "bad";
  className?: string;
}

export const StatusPulse: React.FC<StatusPulseProps> = ({
  status = "ok",
  className = "",
}) => {
  return <span className={`pulse-dot pulse-${status} ${className}`.trim()} aria-hidden="true" />;
};
