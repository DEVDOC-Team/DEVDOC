import React from "react";
import { ArrowUpRight, Filter, ShieldAlert } from "lucide-react";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Panel } from "../components/ui/Panel";
import "./views.css";

export interface IncidentsViewProps {
  onSelectIncident: (id: string) => void;
}

export const IncidentsView: React.FC<IncidentsViewProps> = ({ onSelectIncident }) => {
  const incidents = [
    {
      id: "INC-2291",
      title: "Checkout API 5xx spike",
      service: "checkout-api",
      env: "PROD",
      severity: "SEV-2" as const,
      status: "INVESTIGATING",
      time: "14:07:02Z",
      duration: "00:19:41",
      active: true,
    },
    {
      id: "INC-2289",
      title: "Redis rate limiter connection timeout burst",
      service: "api-gateway",
      env: "PROD",
      severity: "SEV-2" as const,
      status: "RESOLVED",
      time: "Yesterday 08:30Z",
      duration: "00:12:05",
      active: false,
    },
    {
      id: "INC-2284",
      title: "Kafka consumer lag exceeding SLA on payment-events",
      service: "event-pipeline",
      env: "STAGING",
      severity: "SEV-1" as const,
      status: "RESOLVED",
      time: "24 Oct 16:15Z",
      duration: "00:45:20",
      active: false,
    },
  ];

  return (
    <div className="incidents-view">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <h1 style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, color: "var(--devdoc-fg)" }}>
            Incidents Queue
          </h1>
          <p style={{ fontSize: "12px", color: "var(--devdoc-fg-muted)", marginTop: "2px" }}>
            Operational incidents under active monitoring and autonomous investigation.
          </p>
        </div>

        <div style={{ display: "flex", gap: "8px" }}>
          <Button variant="secondary" size="sm" icon={<Filter size={14} />}>
            Filter (All)
          </Button>
          <Button variant="primary" size="sm">
            Declare Incident
          </Button>
        </div>
      </div>

      <Panel title="Active & Recent Incidents" meta={`${incidents.length} total`} bodyClassName="p-0">
        <div style={{ display: "flex", flexDirection: "column" }}>
          {incidents.map((inc) => (
            <div
              key={inc.id}
              onClick={() => inc.active && onSelectIncident(inc.id)}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 16px",
                borderBottom: "1px solid var(--devdoc-border)",
                cursor: inc.active ? "pointer" : "default",
                background: inc.active ? "rgba(56, 189, 248, 0.03)" : "transparent",
                transition: "background var(--transition-fast)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
                <ShieldAlert size={18} color={inc.severity === "SEV-1" ? "var(--devdoc-status-bad)" : "var(--devdoc-accent-amber)"} />
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: "12px", color: "var(--devdoc-accent)" }}>
                      {inc.id}
                    </span>
                    <span style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "14px", color: "var(--devdoc-fg)" }}>
                      {inc.title}
                    </span>
                    <Badge variant={inc.severity === "SEV-1" ? "sev1" : "sev2"}>{inc.severity}</Badge>
                    <Badge variant="env">{inc.env}</Badge>
                  </div>

                  <div style={{ fontSize: "11px", color: "var(--devdoc-fg-muted)", marginTop: "4px", display: "flex", gap: "16px" }}>
                    <span>Service: <b>{inc.service}</b></span>
                    <span>Declared: {inc.time}</span>
                    <span>Duration: {inc.duration}</span>
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                {inc.active ? (
                  <Badge variant="cyan">INVESTIGATING</Badge>
                ) : (
                  <Badge variant="ok">RESOLVED</Badge>
                )}
                {inc.active && <ArrowUpRight size={16} color="var(--devdoc-accent)" />}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
};
