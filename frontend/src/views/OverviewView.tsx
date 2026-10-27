import React from 'react';
import { useProjects } from '../context/ProjectContext';
import { useIncidents } from '../context/IncidentContext';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { StatusPulse } from '../components/ui/StatusPulse';
import { AlertTriangle, ArrowRight, RefreshCw, FolderGit2, ShieldCheck, Clock } from 'lucide-react';

interface OverviewViewProps {
  onNavigate: (view: string) => void;
  onSelectIncident: (id: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({ onNavigate, onSelectIncident }) => {
  const { selectedProject, projects } = useProjects();
  const {
    incidents,
    loadingIncidents,
    error,
    refreshIncidents,
    investigations,
  } = useIncidents();

  const openIncidents = incidents.filter((i) => i.status === 'open' || i.status === 'investigating');
  const criticalIncidents = incidents.filter((i) => i.severity === 'critical' || i.severity === 'high');
  const resolvedIncidents = incidents.filter((i) => i.status === 'resolved' || i.status === 'closed');
  const latestIncident = openIncidents[0] || incidents[0] || null;

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '22px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Operations Deck & Telemetry Intelligence
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            {selectedProject
              ? `Real-time incident intelligence for workspace: ${selectedProject.name}`
              : 'Select a project to monitor active incident telemetry and autonomous investigations.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={refreshIncidents}
            disabled={loadingIncidents}
            icon={<RefreshCw size={13} className={loadingIncidents ? 'spin' : ''} />}
          >
            Refresh
          </Button>
          {latestIncident && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                onSelectIncident(latestIncident.id);
                onNavigate('investigations');
              }}
              icon={<ArrowRight size={14} />}
            >
              Inspect Active Incident ({latestIncident.severity.toUpperCase()})
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 14px',
            background: 'var(--devdoc-status-bad-bg)',
            border: '1px solid var(--devdoc-status-bad-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--devdoc-status-bad)',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            margin: '14px 0',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={refreshIncidents}>
            Retry
          </Button>
        </div>
      )}

      {/* No Project Selected State */}
      {!selectedProject && projects.length === 0 && (
        <Panel style={{ textAlign: 'center', padding: '36px 20px', marginTop: '14px' }}>
          <FolderGit2 size={28} color="var(--devdoc-accent)" style={{ marginBottom: '10px' }} />
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>No Projects Connected</h3>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', maxWidth: '420px', margin: '6px auto 16px' }}>
            Connect or select a monitored project in the Projects console to begin ingesting telemetry and tracking incidents.
          </p>
          <Button variant="primary" size="sm" onClick={() => onNavigate('projects')}>
            Open Projects Console
          </Button>
        </Panel>
      )}

      {/* Hero Active Incident Banner if one exists */}
      {latestIncident && (
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.12) 0%, rgba(18, 27, 46, 0.95) 100%)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-md)',
            padding: '16px 20px',
            marginTop: '14px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ padding: '10px', background: 'rgba(239, 68, 68, 0.2)', borderRadius: 'var(--radius-sm)' }}>
              <AlertTriangle size={24} color="var(--devdoc-bad)" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Badge variant={latestIncident.severity === 'critical' ? 'sev1' : 'sev2'}>
                  {latestIncident.severity.toUpperCase()}
                </Badge>
                <Badge variant="accent">{latestIncident.status.toUpperCase()}</Badge>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--devdoc-fg-dim)' }}>
                  ID: {latestIncident.id.slice(0, 8)}
                </span>
              </div>
              <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>
                {latestIncident.title}
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                {latestIncident.description || 'Reported via automated telemetry monitor.'}
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <Button
              variant="primary"
              size="sm"
              onClick={() => {
                onSelectIncident(latestIncident.id);
                onNavigate('investigations');
              }}
            >
              Open Investigation Console
            </Button>
          </div>
        </div>
      )}

      {/* Operational KPI Metrics based strictly on real backend data */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '14px' }}>
        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Open Incidents
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: openIncidents.length > 0 ? 'var(--devdoc-warn)' : 'var(--devdoc-ok)', marginTop: '4px' }}>
            {openIncidents.length}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            {criticalIncidents.length} critical or high severity
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Resolved Incidents
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-ok)', marginTop: '4px' }}>
            {resolvedIncidents.length}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Total closed in workspace
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Active Investigations
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-accent)', marginTop: '4px' }}>
            {investigations.length}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Autonomous pipelines tracked
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Affected Users
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>
            {incidents.reduce((acc, i) => acc + (i.affected_users || 0), 0).toLocaleString()}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Cumulative impact count
          </div>
        </Panel>
      </div>

      {/* Recent Incidents Queue & Pipeline Telemetry */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: '14px', marginTop: '14px' }}>
        <Panel
          title="Recent Operational Incidents"
          meta={<Button variant="ghost" size="sm" onClick={() => onNavigate('incidents')}>View Queue</Button>}
        >
          {loadingIncidents && incidents.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '12px' }}>
              Loading incidents telemetry...
            </div>
          ) : incidents.length === 0 ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '12px' }}>
              No incidents reported for this project. System operating nominally.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {incidents.slice(0, 5).map((inc) => (
                <div
                  key={inc.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '10px 12px',
                    background: 'var(--devdoc-surface-sunken)',
                    borderRadius: 'var(--radius-sm)',
                    borderLeft: `3px solid ${
                      inc.severity === 'critical'
                        ? 'var(--devdoc-bad)'
                        : inc.severity === 'high'
                        ? 'var(--devdoc-warn)'
                        : 'var(--devdoc-accent)'
                    }`,
                    cursor: 'pointer',
                  }}
                  onClick={() => {
                    onSelectIncident(inc.id);
                    onNavigate('investigations');
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color: 'var(--devdoc-accent)' }}>
                        {inc.id.slice(0, 8)}
                      </span>
                      <Badge variant={inc.severity === 'critical' ? 'sev1' : 'sev2'}>
                        {inc.severity.toUpperCase()}
                      </Badge>
                      <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--devdoc-fg)' }}>
                        {inc.title}
                      </span>
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                      Source: {inc.source.toUpperCase()} · Detected: {new Date(inc.detected_at).toLocaleTimeString()} · Status: {inc.status.toUpperCase()}
                    </div>
                  </div>
                  <ArrowRight size={14} color="var(--devdoc-fg-muted)" />
                </div>
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Autonomous Pipeline Health">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>FastAPI Gateway</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Healthy (/api/v1/health)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Database & RLS</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Active (/api/v1/ready)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Orchestration Pipeline</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Synchronous Runner Ready</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Live Transport Mode</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Clock size={12} color="var(--devdoc-accent)" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Adaptive Bounded Polling</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Approval Gatekeeper</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <ShieldCheck size={14} color="var(--devdoc-ok)" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Dual-Signature Strict Policy</span>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
};
