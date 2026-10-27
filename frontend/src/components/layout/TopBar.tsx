import React, { useEffect, useState } from "react";
import { Clock, User as UserIcon, LogOut, LogIn } from "lucide-react";
import { Badge } from "../ui/Badge";
import { StatusPulse } from "../ui/StatusPulse";
import { useAuth } from "../../context/AuthContext";
import { useProjects } from "../../context/ProjectContext";
import "./layout.css";

export interface TopBarProps {
  onNavigateSignIn?: () => void;
  breadcrumb?: string;
  incidentTitle?: string;
}

export const TopBar: React.FC<TopBarProps> = ({
  onNavigateSignIn,
  breadcrumb,
  incidentTitle = "Checkout API 5xx spike",
}) => {
  const { user, status, signOut } = useAuth();
  const { selectedProject } = useProjects();
  const [utcTime, setUtcTime] = useState<string>("");

  useEffect(() => {
    const update = () => {
      const now = new Date();
      setUtcTime(now.toTimeString().split(" ")[0] + "S");
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  const displayBreadcrumb =
    breadcrumb ||
    (selectedProject
      ? `PROD / ${selectedProject.slug} / ACTIVE`
      : "DEVDOC / Workspace");

  const displayName = user
    ? user.full_name || user.email.split("@")[0]
    : null;

  return (
    <header className="app-topbar" aria-label="Main header">
      <div className="topbar-left">
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
            {displayBreadcrumb}
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

        {status === "authenticated" && user ? (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span
              className="topbar-item"
              title={`Authenticated as ${user.email}`}
              style={{ display: "flex", alignItems: "center", gap: "6px" }}
            >
              <UserIcon size={14} color="var(--devdoc-accent)" />
              <span style={{ fontWeight: 600, color: "var(--devdoc-fg)" }}>
                {displayName}
              </span>
            </span>

            <button
              onClick={signOut}
              title="Sign Out"
              aria-label="Sign Out"
              style={{
                display: "inline-flex",
                alignItems: "center",
                color: "var(--devdoc-fg-muted)",
                padding: "4px",
                borderRadius: "var(--radius-sm)",
                transition: "color var(--transition-fast)",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--devdoc-status-bad)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--devdoc-fg-muted)")}
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <button
            onClick={onNavigateSignIn}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              background: "rgba(174, 184, 192, 0.1)",
              border: "1px solid rgba(174, 184, 192, 0.3)",
              color: "var(--devdoc-accent)",
              padding: "4px 10px",
              borderRadius: "var(--radius-sm)",
              fontSize: "11px",
              fontWeight: 600,
            }}
          >
            <LogIn size={13} />
            <span>Sign In</span>
          </button>
        )}

        <span className="topbar-item">
          <Clock size={14} color="var(--devdoc-fg-muted)" />
          <span>{utcTime || "14:26:41S"}</span>
        </span>

        <div className="topbar-live-tag">
          <StatusPulse status="ok" />
          <span>LIVE</span>
        </div>
      </div>
    </header>
  );
};
