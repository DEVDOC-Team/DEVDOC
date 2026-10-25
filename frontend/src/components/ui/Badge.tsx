import React from "react";
import "./ui.css";

export type BadgeVariant =
  | "env"
  | "sev1"
  | "sev2"
  | "ok"
  | "warn"
  | "accent"
  | "neutral"
  | "cyan";

export interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "neutral",
  className = "",
}) => {
  return (
    <span className={`badge badge-${variant} ${className}`.trim()}>
      {children}
    </span>
  );
};
