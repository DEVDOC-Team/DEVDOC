import React, { useEffect, useState } from "react";
import { Clock, User as UserIcon, LogOut, LogIn, Mail } from "lucide-react";
import { Badge } from "../ui/Badge";
import { StatusPulse } from "../ui/StatusPulse";
import { useAuth } from "../../context/AuthContext";
import { useProjects } from "../../context/ProjectContext";
import "./layout.css";

const GoogleProviderIcon: React.FC<{ size?: number }> = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
  </svg>
);

const GitHubProviderIcon: React.FC<{ size?: number }> = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
    <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
  </svg>
);

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
  const { user, status, signOut, authProvider } = useAuth();
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
  const normalizedProfileProvider = user?.provider?.toLowerCase();
  const signInProvider =
    authProvider ??
    (normalizedProfileProvider === "google" || normalizedProfileProvider === "github" || normalizedProfileProvider === "email"
      ? normalizedProfileProvider
      : null);
  const providerLabel = signInProvider === "github"
    ? "GitHub"
    : signInProvider === "google"
      ? "Google"
      : signInProvider === "email"
        ? "Email"
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
              title={providerLabel ? `Authenticated as ${user.email} via ${providerLabel}` : `Authenticated as ${user.email}`}
              style={{ display: "flex", alignItems: "center", gap: "6px" }}
            >
              <UserIcon size={14} color="var(--devdoc-accent)" />
              {signInProvider === "github" && (
                <span title="Signed in with GitHub" aria-label="Signed in with GitHub" style={{ display: "inline-flex", color: "var(--devdoc-fg-muted)" }}>
                  <GitHubProviderIcon />
                </span>
              )}
              {signInProvider === "google" && (
                <span title="Signed in with Google" aria-label="Signed in with Google" style={{ display: "inline-flex" }}>
                  <GoogleProviderIcon />
                </span>
              )}
              {signInProvider === "email" && (
                <span title="Signed in with email" aria-label="Signed in with email" style={{ display: "inline-flex", color: "var(--devdoc-fg-muted)" }}>
                  <Mail size={14} />
                </span>
              )}
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
