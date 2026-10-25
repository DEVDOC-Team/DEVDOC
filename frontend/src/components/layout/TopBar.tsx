import React, { useEffect, useState } from "react";
import { Clock, Menu, User } from "lucide-react";
import { Badge } from "../ui/Badge";
import { StatusPulse } from "../ui/StatusPulse";
import "./layout.css";

export interface TopBarProps {
  onToggleMobile: () => void;
  breadcrumb?: string;
  incidentTitle?: string;
}

export const TopBar: React.FC<TopBarProps> = ({
  onToggleMobile,
  breadcrumb = "PROD / checkout-api / INC-2291",
  incidentTitle = "Checkout API 5xx spike",
}) => {
  const [utcTime, setUtcTime] = useState<string>("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setUtcTime(now.toTimeString().split(" ")[0] + "Z");
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="app-topbar" aria-label="Main header">
      <div className="topbar-left">
        <button
          className="mobile-nav-toggle btn-ghost"
          onClick={onToggleMobile}
          aria-label="Toggle navigation menu"
          style={{ padding: "6px", display: "inline-flex" }}
        >
          <Menu size={18} />
        </button>

        <div>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "10px",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--devdoc-fg-muted)",
            }}
          >
            {breadcrumb}
          </span>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "15px",
              fontWeight: 600,
              color: "var(--devdoc-fg)",
              lineHeight: 1.2,
            }}
          >
            {incidentTitle}
          </div>
        </div>
      </div>

      <div className="topbar-right">
        <Badge variant="env">PROD</Badge>

        <span className="topbar-item">
          <User size={14} color="var(--devdoc-fg-muted)" />
          <span>m.okafor</span>
        </span>

        <span className="topbar-item">
          <Clock size={14} color="var(--devdoc-fg-muted)" />
          <span>{utcTime || "14:26:41Z"}</span>
        </span>

        <div className="topbar-live-tag">
          <StatusPulse status="ok" />
          <span>LIVE</span>
        </div>
      </div>
    </header>
  );
};
