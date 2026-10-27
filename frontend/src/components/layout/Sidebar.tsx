import React from "react";
import {
  Activity,
  AlertCircle,
  ClipboardCheck,
  History,
  LayoutDashboard,
  Settings,
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
            background: "rgba(16, 18, 20, 0.7)",
            backdropFilter: "blur(4px)",
            zIndex: 19,
          }}
          aria-hidden="true"
        />
      )}

      <aside className={`app-sidebar ${mobileOpen ? "mobile-open" : ""}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <img
              src="/assets/devdoc-logo.jpg"
              alt="DevDOC Logo"
              style={{
                width: 26,
                height: 26,
                borderRadius: 6,
                objectFit: "cover",
                flexShrink: 0,
                boxShadow: "0 0 8px rgba(245, 158, 11, 0.3)",
              }}
            />
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
            <AlertCircle size={16} />
            <span>Incidents Queue</span>
          </button>

          <span className="nav-section-label">Governance</span>

          <button
            className={`nav-item ${activeRoute === "approvals" ? "active" : ""}`}
            onClick={() => handleNavClick("approvals")}
          >
            <ClipboardCheck size={16} />
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
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="currentColor"
              focusable="false"
            >
              <path d="M15.698 7.287 8.712.302a1.03 1.03 0 0 0-1.457 0l-1.45 1.45 1.84 1.84a1.223 1.223 0 0 1 1.55 1.56l1.773 1.774a1.224 1.224 0 0 1 1.267 2.025 1.226 1.226 0 1 1-2.002-1.334L8.58 5.963v4.353a1.226 1.226 0 1 1-1.008-.036V5.887a1.223 1.223 0 0 1-.666-1.608L5.093 2.465l-4.79 4.79a1.03 1.03 0 0 0 0 1.457l6.986 6.986a1.03 1.03 0 0 0 1.457 0l6.953-6.953a1.031 1.031 0 0 0 0-1.457" />
            </svg>
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
