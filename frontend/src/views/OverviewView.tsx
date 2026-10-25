import React from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { StatusPulse } from '../components/ui/StatusPulse';
import { AlertTriangle, ArrowRight } from 'lucide-react';

interface OverviewViewProps {
  onNavigate: (view: string) => void;
  onSelectIncident: (id: string) => void;
}

export const OverviewView: React.FC<OverviewViewProps> = ({ onNavigate, onSelectIncident }) => {
  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '22px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Operations Deck & Investigation Intelligence
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Autonomous AI DevOps telemetry, multi-agent evidence correlation, and gatekeeper controls.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              onSelectIncident('INC-2291');
              onNavigate('investigations');
            }}
            icon={<ArrowRight size={14} />}
          >
            Open Active Investigation (INC-2291)
          </Button>
        </div>
      </div>

      {/* Hero Active Incident Banner */}
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
          gap: '12px'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ padding: '10px', background: 'rgba(239, 68, 68, 0.2)', borderRadius: 'var(--radius-sm)' }}>
            <AlertTriangle size={24} color="var(--devdoc-bad)" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Badge variant="sev1">SEV-1</Badge>
              <Badge variant="accent">INVESTIGATION ACTIVE</Badge>
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--devdoc-fg-dim)' }}>INC-2291</span>
            </div>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>
              Worker pool exhaustion: 504 Gateway Timeout during batch invoice processing
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
              Root cause identified: Connection leak in connection pool exhaustion under 4.2k rps. Fix candidate generated and verified in Docker sandbox.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => onNavigate('approvals')}
          >
            Review 1 Pending Approval
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              onSelectIncident('INC-2291');
              onNavigate('investigations');
            }}
          >
            Inspect Diagnosis Console
          </Button>
        </div>
      </div>

      {/* KPI Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '14px' }}>
        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>MTTR (Mean Time to Remediation)</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-accent)', marginTop: '4px' }}>4m 12s</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-ok)', marginTop: '4px' }}>-88% vs baseline (35m)</div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Sandbox Test Pass Rate</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-ok)', marginTop: '4px' }}>100%</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>12/12 container suites verified</div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Evidence Correlation Ratio</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>96.8%</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-accent)', marginTop: '4px' }}>4 multi-modal evidence sources linked</div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Autonomous Policy Invariants</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>0 Breaches</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-ok)', marginTop: '4px' }}>Immutable audit ledger secured</div>
        </Panel>
      </div>

      {/* Split Cards: Recent Investigations & Engine Health */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: '14px', marginTop: '14px' }}>
        <Panel
          title="Recent Automated Investigations"
          meta={<Button variant="ghost" size="sm" onClick={() => onNavigate('incidents')}>View All</Button>}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 12px',
                background: 'var(--devdoc-surface-sunken)',
                borderRadius: 'var(--radius-sm)',
                borderLeft: '3px solid var(--devdoc-bad)',
                cursor: 'pointer'
              }}
              onClick={() => {
                onSelectIncident('INC-2291');
                onNavigate('investigations');
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color: 'var(--devdoc-accent)' }}>INC-2291</span>
                  <Badge variant="sev1">SEV-1</Badge>
                  <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--devdoc-fg)' }}>Worker pool exhaustion</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                  PostgreSQL connection leak · 5 evidence items · Candidate patch waiting approval
                </div>
              </div>
              <ArrowRight size={14} color="var(--devdoc-fg-muted)" />
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 12px',
                background: 'var(--devdoc-surface-sunken)',
                borderRadius: 'var(--radius-sm)',
                borderLeft: '3px solid var(--devdoc-warn)'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color: 'var(--devdoc-accent)' }}>INC-2290</span>
                  <Badge variant="sev2">SEV-2</Badge>
                  <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--devdoc-fg)' }}>Nebius Token Refresh Latency Spike</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                  Auto-mitigated via token cache warm pool · Resolved 4h ago
                </div>
              </div>
              <Badge variant="ok">RESOLVED</Badge>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                padding: '10px 12px',
                background: 'var(--devdoc-surface-sunken)',
                borderRadius: 'var(--radius-sm)',
                borderLeft: '3px solid var(--devdoc-ok)'
              }}
            >
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', fontWeight: 600, color: 'var(--devdoc-accent)' }}>INC-2284</span>
                  <Badge variant="neutral">SEV-3</Badge>
                  <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--devdoc-fg)' }}>Supabase Auth SSL Handshake Transient</span>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                  DNS resolution jitter · Auto-remediated with backoff retry · Resolved 3d ago
                </div>
              </div>
              <Badge variant="ok">RESOLVED</Badge>
            </div>
          </div>
        </Panel>

        <Panel title="Autonomous Pipeline Status">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>GitHub Webhook Receiver</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Online (0.2ms latency)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Log Ingestion Daemon</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Streaming (4.2k ev/s)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Nebius Nemotron LLM</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Ready (248ms avg)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Docker Sandbox Runner</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Idle (0 active containers)</span>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '12px' }}>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>Audit Signer Engine</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <StatusPulse status="ok" />
                <span style={{ color: 'var(--devdoc-fg)' }}>Secured (SHA-256)</span>
              </div>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
};
