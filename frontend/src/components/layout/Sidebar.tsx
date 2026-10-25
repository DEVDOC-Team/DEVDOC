import React from "react";
import {
  Activity,
  FileCheck2,
  GitBranch,
  History,
  LayoutDashboard,
  Settings,
  ShieldAlert,
} from "lucide-react";
import { StatusPulse } from "../ui/StatusPulse";
import "./layout.css";

export type NavRoute =
  | "overview"
  | "incidents"
  | "investigations"
  | "approvals"
  | "audit"
  | "projects"
  | "settings"
  | "signin";

export interface SidebarProps {
  activeRoute: NavRoute;
  onRouteChange: (route: NavRoute) => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeRoute,
  onRouteChange,
  mobileOpen,
  onCloseMobile,
}) => {
  const handleNavClick = (route: NavRoute) => {
    onRouteChange(route);
    onCloseMobile();
  };

  return (
    <>
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={onCloseMobile}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(10, 16, 32, 0.7)",
            backdropFilter: "blur(4px)",
            zIndex: 19,
          }}
          aria-hidden="true"
        />
      )}

      <aside className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <Activity size={20} color="var(--devdoc-accent)" />
            <span className="brand-text">DEVDOC</span>
            <span className="brand-sub">AUTONOMOUS</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          <span className="nav-section-label">Investigation</span>

          <button
            className={`nav-item ${activeRoute === "investigations" ? "active" : ""}`}
            onClick={() => handleNavClick("investigations")}
          >
            <Activity size={16} />
            <span>Investigation Console</span>
          </button>

          <button
            className={`nav-item ${activeRoute === "incidents" ? "active" : ""}`}
            onClick={() => handleNavClick("incidents")}
          >
            <ShieldAlert size={16} />
            <span>Incidents Queue</span>
          </button>

          <span className="nav-section-label">Governance</span>

          <button
            className={`nav-item ${activeRoute === "approvals" ? "active" : ""}`}
            onClick={() => handleNavClick("approvals")}
          >
            <FileCheck2 size={16} />
            <span>Approval Gate</span>
          </button>

          <button
            className={`nav-item ${activeRoute === "audit" ? "active" : ""}`}
            onClick={() => handleNavClick("audit")}
          >
            <History size={16} />
            <span>Immutable Audit Log</span>
          </button>

          <span className="nav-section-label">Platform</span>

          <button
            className={`nav-item ${activeRoute === "overview" ? "active" : ""}`}
            onClick={() => handleNavClick("overview")}
          >
            <LayoutDashboard size={16} />
            <span>System Overview</span>
          </button>

          <button
            className={`nav-item ${activeRoute === "projects" ? "active" : ""}`}
            onClick={() => handleNavClick("projects")}
          >
            <GitBranch size={16} />
            <span>Repositories</span>
          </button>

          <button
            className={`nav-item ${activeRoute === "settings" ? "active" : ""}`}
            onClick={() => handleNavClick("settings")}
          >
            <Settings size={16} />
            <span>Settings & Health</span>
          </button>
        </nav>

        <div className="sidebar-footer">
          <div className="engine-status-pill">
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <StatusPulse status="ok" />
              <span>Engine Status</span>
            </div>
            <span style={{ color: "var(--devdoc-status-ok)", fontWeight: 600 }}>READY</span>
          </div>
        </div>
      </aside>
    </>
  );
};
