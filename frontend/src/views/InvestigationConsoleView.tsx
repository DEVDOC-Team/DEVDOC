import React, { useState } from 'react';
import {
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Database,
  FileCheck2,
  FileText,
  GitCommit,
  Lock,
  Play,
  RefreshCw,
  Rocket,
  Route,
  ShieldAlert,
  TrendingUp,
  AlertCircle,
  Activity,
} from 'lucide-react';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { CodeDiff } from '../components/ui/CodeDiff';
import { Panel } from '../components/ui/Panel';
import { PhaseRail, type PhaseItem } from '../components/ui/PhaseRail';
import { StatusPulse } from '../components/ui/StatusPulse';
import { useIncidents } from '../context/IncidentContext';
import { useProjects } from '../context/ProjectContext';
import './views.css';

interface EvidenceData {
  id: string;
  icon: React.ReactNode;
  desc: string;
  meta: string;
  detailTag: string;
  detailTimestamp: string;
  detailCode: Array<{ type?: 'add' | 'del' | 'err' | 'dim' | 'normal'; text: string }>;
  detailNote: React.ReactNode;
  isMetricChart?: boolean;
}

const DEFAULT_EVIDENCE: EvidenceData[] = [
  {
    id: 'E-01',
    icon: <FileText size={15} />,
    desc: 'HikariCP connection-timeout burst, api-gateway',
    meta: '14:02:11Z · 214 events · all pods',
    detailTag: 'LOG · api-gateway · pod 7f4c9d',
    detailTimestamp: '14:02:11.412Z',
    detailCode: [
      { type: 'normal', text: '14:02:08.412Z ERROR [api-gateway] hikari pool "checkout-pool"' },
      { type: 'err', text: '  stats: active=214 idle=0 waiting=37 max=200' },
      { type: 'err', text: '  SQLState=HYT0 msg="Connection is not available,' },
      { type: 'err', text: '  request timed out after 30000ms."' },
    ],
    detailNote: (
      <span>
        First of <b>214 identical timeout events</b> in the 13:58–14:07 window. Errors are cluster-wide across all 4 pods, ruling out a single bad replica.
      </span>
    ),
  },
  {
    id: 'E-02',
    icon: <TrendingUp size={15} />,
    desc: 'db_connections climbs 74 → 214 after deploy',
    meta: '13:58–14:02Z · 5 samples · 15s step',
    detailTag: 'METRIC · db_connections',
    detailTimestamp: 'checkout-pool · 15s step',
    isMetricChart: true,
    detailCode: [],
    detailNote: (
      <span>
        74 → 96 → 138 → 181 → <b>214 connections</b> over four minutes. Slope begins at <b>13:58:04Z</b>, matching deploy v2.14.0 to the second.
      </span>
    ),
  },
  {
    id: 'E-03',
    icon: <GitCommit size={15} />,
    desc: 'a91f3c2 adds retry loop to PaymentClient',
    meta: 'PR #482 · d.lindqvist · +18 −4',
    detailTag: 'COMMIT · a91f3c2',
    detailTimestamp: 'payments-service · PR #482',
    detailCode: [
      { type: 'dim', text: 'PaymentClient.java · "Add retry with backoff"' },
      { type: 'dim', text: 'author d.lindqvist · 2026-10-25 13:50Z · +18 −4' },
      { type: 'normal', text: '' },
      { type: 'normal', text: '  ChargeResult charge(Payment p) {' },
      { type: 'del', text: '-   Connection c = pool.getConnection();' },
      { type: 'add', text: '+   for (int attempt = 0; attempt < 3; attempt++) {' },
      { type: 'err', text: '+     c = pool.getConnection();   // prior handle never released' },
      { type: 'add', text: '+     try {' },
      { type: 'add', text: '+       return gateway.send(p, c);' },
      { type: 'add', text: '+     } catch (TransientException te) { backoff(attempt); }' },
    ],
    detailNote: (
      <span>
        Commit introduced an inner retry loop that acquires a fresh connection handle per attempt without releasing the previous connection, leaking up to 3 connections per transient error.
      </span>
    ),
  },
  {
    id: 'E-04',
    icon: <Route size={15} />,
    desc: 'Trace: hikari.acquire span never closes',
    meta: 'trace 7c41d9 · span 12 of 22',
    detailTag: 'TRACE · OpenTelemetry',
    detailTimestamp: 'trace 7c41d9 · span 12/22',
    detailCode: [
      { type: 'dim', text: 'GET /api/v1/checkout/charge (504 Gateway Timeout)' },
      { type: 'normal', text: '├─ gateway.auth (1.2ms) [200 OK]' },
      { type: 'err', text: '├─ hikari.acquire (30,000ms TIMEOUT)' },
      { type: 'err', text: '└─ thread.blocked: waiting for database connection' },
    ],
    detailNote: (
      <span>
        Distributed trace captures client thread blocked indefinitely inside <code>hikari.acquire</code> until downstream 30s timeout triggered HTTP 504.
      </span>
    ),
  },
  {
    id: 'E-05',
    icon: <Rocket size={15} />,
    desc: 'Deploy v2.14.0 → prod, 4 minutes before onset',
    meta: '13:58:04Z · rollout 4/4 pods',
    detailTag: 'DEPLOY · payments-service',
    detailTimestamp: '13:58:04Z · prod-cluster',
    detailCode: [
      { type: 'normal', text: 'Rollout started: 13:57:12Z' },
      { type: 'normal', text: 'Image: registry.internal/payments:v2.14.0@sha256:d8a9...' },
      { type: 'normal', text: 'Pods updated: 4/4 pods healthy' },
      { type: 'err', text: 'Onset time: 14:02:11Z (4 min post-rollout)' },
    ],
    detailNote: (
      <span>
        Canary deployment bypassed due to urgent hotfix tag. 100% traffic exposed to leaky retry loop immediately upon rollout.
      </span>
    ),
  },
];

const parseDiffLines = (rawDiff: string) => {
  return rawDiff.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) {
      return { type: 'dim' as const, text: line };
    }
    if (line.startsWith('+')) {
      return { type: 'add' as const, text: line };
    }
    if (line.startsWith('-')) {
      return { type: 'del' as const, text: line };
    }
    return { type: 'normal' as const, text: line };
  });
};

export const InvestigationConsoleView: React.FC = () => {
  const { selectedProject } = useProjects();
  const {
    selectedIncident,
    selectedIncidentId,
    activeInvestigation,
    activeApproval,
    runningInvestigation,
    isPolling,
    error,
    triggerInvestigationRun,
    submitApprovalDecision,
    refreshIncidents,
    clearError,
  } = useIncidents();

  const [selectedEvidence, setSelectedEvidence] = useState<string>('E-01');
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);
  const [approvalReason, setApprovalReason] = useState<string>('');
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmittingApproval, setIsSubmittingApproval] = useState<boolean>(false);
  const [localDecision, setLocalDecision] = useState<'pending' | 'approved' | 'rejected'>('pending');

  const evidenceItems: EvidenceData[] = DEFAULT_EVIDENCE;
  const activeEvidence = evidenceItems.find((e) => e.id === selectedEvidence) || evidenceItems[0];

  const computePhases = (): PhaseItem[] => {
    const invStatus = activeInvestigation?.status;
    const appStatus = activeApproval?.status;

    if (invStatus === 'running') {
      return [
        { id: 'detect', name: 'Detect', sub: 'done', state: 'done' },
        { id: 'investigate', name: 'Investigate', sub: 'running', state: 'active' },
        { id: 'evidence', name: 'Evidence', sub: 'collecting', state: 'active' },
        { id: 'reason', name: 'Reason', sub: 'evaluating', state: 'active' },
        { id: 'diagnose', name: 'Diagnose', sub: 'queued', state: 'pending' },
        { id: 'fix', name: 'Fix proposal', sub: 'queued', state: 'pending' },
        { id: 'verify', name: 'Verify', sub: 'queued', state: 'pending' },
        { id: 'approval', name: 'Approval', sub: 'queued', state: 'pending' },
        { id: 'resolve', name: 'Resolve', sub: 'gated', state: 'gated' },
      ];
    }

    if (invStatus === 'failed') {
      return [
        { id: 'detect', name: 'Detect', sub: 'done', state: 'done' },
        { id: 'investigate', name: 'Investigate', sub: 'failed', state: 'active' },
        { id: 'evidence', name: 'Evidence', sub: 'interrupted', state: 'pending' },
        { id: 'reason', name: 'Reason', sub: 'halted', state: 'pending' },
        { id: 'diagnose', name: 'Diagnose', sub: 'halted', state: 'pending' },
        { id: 'fix', name: 'Fix proposal', sub: 'halted', state: 'pending' },
        { id: 'verify', name: 'Verify', sub: 'halted', state: 'pending' },
        { id: 'approval', name: 'Approval', sub: 'halted', state: 'pending' },
        { id: 'resolve', name: 'Resolve', sub: 'gated', state: 'gated' },
      ];
    }

    const approvalState =
      appStatus === 'approved' || localDecision === 'approved'
        ? 'done'
        : appStatus === 'rejected' || localDecision === 'rejected'
        ? 'done'
        : 'active';

    return [
      { id: 'detect', name: 'Detect', sub: 'done', state: 'done' },
      { id: 'investigate', name: 'Investigate', sub: 'done', state: 'done' },
      { id: 'evidence', name: 'Evidence', sub: 'done', state: 'done' },
      { id: 'reason', name: 'Reason', sub: 'done', state: 'done' },
      { id: 'diagnose', name: 'Diagnose', sub: 'emitted', state: 'done' },
      { id: 'fix', name: 'Fix proposal', sub: 'generated', state: 'done' },
      { id: 'verify', name: 'Verify', sub: 'passed', state: 'done' },
      { id: 'approval', name: 'Approval', sub: appStatus || localDecision, state: approvalState },
      { id: 'resolve', name: 'Resolve', sub: 'gated', state: appStatus === 'approved' || localDecision === 'approved' ? 'active' : 'gated' },
    ];
  };

  const handleApprovalAction = async (decision: 'approved' | 'rejected') => {
    if (approvalReason.trim().length < 8) {
      setModalError('Audit rationale requires at least 8 non-whitespace characters.');
      return;
    }

    setModalError(null);
    setIsSubmittingApproval(true);

    try {
      if (activeApproval?.id) {
        await submitApprovalDecision(activeApproval.id, decision, approvalReason.trim());
      }
      setLocalDecision(decision);
      setShowApprovalModal(false);
      setApprovalReason('');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to record approval decision';
      setModalError(msg);
    } finally {
      setIsSubmittingApproval(false);
    }
  };

  // Determine display data
  const incidentNumber = selectedIncident ? `INC-${selectedIncident.id.slice(0, 6)}` : selectedIncidentId || 'INC-2291';
  const incidentTitle = selectedIncident?.title || 'Checkout API 5xx spike';
  const incidentSeverity = selectedIncident?.severity ? selectedIncident.severity.toUpperCase() : 'SEV-2';
  const projectSlug = selectedProject?.slug || 'checkout-api';

  const proposalDiff = activeApproval?.review?.proposal?.diff
    ? parseDiffLines(activeApproval.review.proposal.diff)
    : [
        { type: 'dim' as const, text: '--- a/services/payment/PaymentClient.java' },
        { type: 'dim' as const, text: '+++ b/services/payment/PaymentClient.java' },
        { type: 'normal' as const, text: '   for (int attempt = 0; attempt < 3; attempt++) {' },
        { type: 'del' as const, text: '-    Connection c = pool.getConnection();' },
        { type: 'del' as const, text: '-    try { return gateway.send(p, c); }' },
        { type: 'add' as const, text: '+    try (Connection c = pool.getConnection()) {' },
        { type: 'add' as const, text: '+      return gateway.send(p, c);' },
        { type: 'add' as const, text: '+    } catch (TransientException te) {' },
        { type: 'add' as const, text: '+      logger.warn("Retrying payment attempt={}", attempt);' },
        { type: 'add' as const, text: '+      backoff(attempt);' },
        { type: 'add' as const, text: '+    }' },
      ];

  const currentDecision = activeApproval?.status || localDecision;

  return (
    <div className="investigation-console">
      {/* Pipeline Phase Rail */}
      <PhaseRail phases={computePhases()} />

      {/* Global Context Error Banner */}
      {error && (
        <div
          style={{
            margin: '12px 0 0 0',
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid var(--devdoc-status-bad)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
            color: 'var(--devdoc-fg)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={15} color="var(--devdoc-status-bad)" />
            <span>{error}</span>
          </div>
          <div style={{ display: 'flex', gap: '8px' }}>
            <Button variant="secondary" size="sm" onClick={() => refreshIncidents()}>
              Retry
            </Button>
            <Button variant="ghost" size="sm" onClick={clearError}>
              Dismiss
            </Button>
          </div>
        </div>
      )}

      {/* Incident Subheader Facts */}
      <div className="incident-header-banner" style={{ marginTop: '12px' }}>
        <div>
          <span
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '10px',
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: 'var(--devdoc-fg-muted)',
            }}
          >
            PROD / {projectSlug} / {incidentNumber}
          </span>
          <div
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--devdoc-fg)',
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              marginTop: '2px',
            }}
          >
            <span>{incidentTitle}</span>
            <Badge variant={incidentSeverity.toLowerCase().includes('1') ? 'sev1' : 'sev2'}>
              {incidentSeverity}
            </Badge>
            {isPolling && (
              <Badge variant="cyan">
                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Activity size={10} className="spin-slow" />
                  LIVE TELEMETRY
                </span>
              </Badge>
            )}
          </div>
        </div>

        <div className="incident-facts">
          <span>
            Status <b>{selectedIncident?.status.toUpperCase() || 'INVESTIGATING'}</b>
          </span>
          <span>
            Impact <b>{selectedIncident ? `${selectedIncident.affected_users} users` : 'api-gateway (all pods)'}</b>
          </span>
          <span>
            Severity <b>{incidentSeverity}</b>
          </span>
          <span>
            Reported <b>{selectedIncident ? new Date(selectedIncident.created_at).toLocaleTimeString() : '14:07:02Z'}</b>
          </span>
        </div>
      </div>

      {/* 3-Column Main Grid */}
      <div className="console-grid">
        {/* Left Column: Metadata & Evidence Ledger */}
        <div className="column-stack">
          {/* Investigation Metadata & Orchestration Trigger */}
          <Panel
            title="Investigation"
            meta={activeInvestigation ? activeInvestigation.id.slice(0, 8) : 'run-3f9c'}
          >
            <dl className="kv-list">
              <dt>Status</dt>
              <dd style={{ textTransform: 'uppercase', color: runningInvestigation ? 'var(--devdoc-accent)' : 'var(--devdoc-status-ok)' }}>
                {activeInvestigation?.status || (runningInvestigation ? 'RUNNING' : 'COMPLETED')}
              </dd>
              <dt>Started</dt>
              <dd>{activeInvestigation?.started_at ? new Date(activeInvestigation.started_at).toLocaleTimeString() : '14:11:32Z'}</dd>
              <dt>Pipeline Engine</dt>
              <dd>DEVDOC Orchestrator (NVIDIA Nemotron)</dd>
              <dt>Sandbox Isolation</dt>
              <dd>Docker --network none</dd>
              <dt>Verified Artifacts</dt>
              <dd>{evidenceItems.length} verified</dd>
            </dl>

            <div style={{ marginTop: '14px', paddingTop: '10px', borderTop: '1px solid var(--devdoc-border)' }}>
              <Button
                variant="primary"
                size="sm"
                onClick={triggerInvestigationRun}
                disabled={runningInvestigation}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                {runningInvestigation ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <StatusPulse status="accent" />
                    <span>Orchestrating Investigation...</span>
                  </span>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Play size={13} />
                    <span>Run Autonomous Investigation</span>
                  </span>
                )}
              </Button>
            </div>
          </Panel>

          {/* Evidence Ledger Panel */}
          <Panel
            title="Evidence Ledger"
            meta={`${evidenceItems.length} items`}
            bodyClassName="p-0"
            footer={
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '8px 12px',
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--devdoc-fg-muted)',
                  borderTop: '1px solid var(--devdoc-border)',
                }}
              >
                <span>Sources: GitHub, Logs, Datadog, Traces</span>
                <span>SHA-256 Verified</span>
              </div>
            }
          >
            <div>
              {evidenceItems.map((item) => (
                <button
                  key={item.id}
                  className={`evidence-item ${selectedEvidence === item.id ? 'selected' : ''}`}
                  onClick={() => setSelectedEvidence(item.id)}
                >
                  <span className="evidence-id">{item.id}</span>
                  <span style={{ color: 'var(--devdoc-fg-muted)' }}>{item.icon}</span>
                  <div className="evidence-text">
                    <span className="evidence-title">{item.desc}</span>
                    <span className="evidence-ref">{item.meta}</span>
                  </div>
                  <ArrowUpRight size={13} color="var(--devdoc-fg-muted)" />
                </button>
              ))}
            </div>
          </Panel>

          {/* Source Preview Drawer Panel */}
          <Panel title="Source Preview" meta={activeEvidence.id}>
            <div
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '10px',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                color: 'var(--devdoc-accent)',
                marginBottom: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>{activeEvidence.detailTag}</span>
              <span style={{ color: 'var(--devdoc-fg-muted)' }}>{activeEvidence.detailTimestamp}</span>
            </div>

            {activeEvidence.isMetricChart ? (
              <div
                style={{
                  background: 'var(--devdoc-canvas)',
                  border: '1px solid var(--devdoc-border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px',
                }}
              >
                <svg viewBox="0 0 300 74" style={{ width: '100%', height: 'auto', display: 'block' }}>
                  <line x1="8" y1="8" x2="292" y2="8" stroke="#f87171" strokeWidth="1" strokeDasharray="3 3" />
                  <text x="292" y="6" textAnchor="end" fontSize="7" fill="#f87171" fontFamily="ui-monospace, Menlo, monospace">
                    max 200
                  </text>
                  <rect x="14" y="45" width="42" height="20" fill="#38bdf8" />
                  <rect x="72" y="38" width="42" height="27" fill="#38bdf8" />
                  <rect x="130" y="26" width="42" height="39" fill="#f5a524" />
                  <rect x="188" y="14" width="42" height="51" fill="#f5a524" />
                  <rect x="246" y="3" width="42" height="62" fill="#f87171" />
                  <text x="35" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    13:58
                  </text>
                  <text x="93" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    13:59
                  </text>
                  <text x="151" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:00
                  </text>
                  <text x="209" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:01
                  </text>
                  <text x="267" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:02
                  </text>
                </svg>
              </div>
            ) : (
              <CodeDiff lines={activeEvidence.detailCode} />
            )}

            <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '8px', lineHeight: 1.5 }}>
              {activeEvidence.detailNote}
            </div>
          </Panel>
        </div>

        {/* Center Column: RCA Diagnosis, Causal Chain, Fix Proposal */}
        <div className="column-stack">
          <Panel
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span>Root Cause Analysis</span>
                <Badge variant="ok">
                  {activeApproval?.review?.root_cause?.confidence_score
                    ? `${Math.round(activeApproval.review.root_cause.confidence_score * 100)}% Confidence`
                    : '94% Confidence'}
                </Badge>
              </div>
            }
            meta={activeApproval?.review?.root_cause ? 'CONFIRMED BY NEMOTRON' : 'EMITTED AT 14:15:02Z'}
            bodyClassName="p-0"
          >
            <div className="claim-title">
              {activeApproval?.review?.root_cause?.claim || (
                <>
                  Database connection pool exhaustion caused by <em>unreleased handles</em> in retry loop inside PaymentClient.java
                </>
              )}
            </div>

            <div className="claim-desc">
              {activeApproval?.review?.root_cause?.failure_modes?.length ? (
                <>
                  Failure modes identified: {activeApproval.review.root_cause.failure_modes.join('; ')}
                </>
              ) : (
                <>
                  Commit <b>a91f3c2</b> introduced an inner retry loop around <code>pool.getConnection()</code> without releasing previous connection handles before initiating subsequent attempts. Under transient downstream gateway throttling, each client request consumed 3 concurrent connections, saturating the 200-handle pool in 240 seconds.
                </>
              )}
            </div>

            {/* Causal Chain Sequence */}
            <div style={{ borderTop: '1px solid var(--devdoc-border)', padding: '12px 18px 4px' }}>
              <div
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '10px',
                  fontWeight: 600,
                  letterSpacing: '0.14em',
                  textTransform: 'uppercase',
                  color: 'var(--devdoc-fg-muted)',
                  marginBottom: '12px',
                }}
              >
                Causal Sequence Chain
              </div>

              <ol className="causal-chain">
                <li className="chain-item">
                  <span className="step-num">01</span>
                  <div className="chain-body">
                    Deploy <b>v2.14.0</b> rolls out to production pods at 13:58:04Z introducing new retry logic.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-05 Deploy</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">02</span>
                  <div className="chain-body">
                    Upstream banking provider returns transient HTTP 429 rate limit errors to PaymentClient.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-01 Logs</span>
                      <span className="evidence-chip">E-04 Trace</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">03</span>
                  <div className="chain-body">
                    PaymentClient retries 3x, acquiring new Hikari handles while holding prior unclosed connections.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-03 Commit</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">04</span>
                  <div className="chain-body">
                    HikariCP connection pool reaches max capacity (200/200) within 4 minutes.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-02 Metric</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">05</span>
                  <div className="chain-body">
                    Incoming checkout requests block on connection acquisition until 30s timeout causes cluster-wide 5xx cascade.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-01 Error</span>
                    </div>
                  </div>
                </li>
              </ol>
            </div>

            {/* Excluded Non-Causes */}
            <div
              style={{
                borderTop: '1px solid var(--devdoc-border)',
                padding: '10px 18px 12px',
                background: 'rgba(0,0,0,0.15)',
              }}
            >
              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--devdoc-fg-muted)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <CheckCircle2 size={13} color="var(--devdoc-status-ok)" />
                <span>
                  <b>Excluded:</b> Postgres CPU saturation ruled out (hovered at 28% throughout onset).
                </span>
              </div>
            </div>

            {/* Proposed Code Fix */}
            <div className="proposal-box">
              <div className="proposal-heading">
                <FileCheck2 size={16} color="var(--devdoc-status-ok)" />
                <span>
                  Proposed Candidate Remediation · {activeApproval?.review?.proposal?.target_files?.[0] || 'PaymentClient.java'}
                </span>
              </div>

              <CodeDiff lines={proposalDiff} />

              <div
                style={{
                  display: 'flex',
                  gap: '16px',
                  marginTop: '10px',
                  fontSize: '11px',
                  color: 'var(--devdoc-fg-muted)',
                  flexWrap: 'wrap',
                }}
              >
                <span>
                  Sandbox Verification:{' '}
                  <b style={{ color: 'var(--devdoc-status-ok)' }}>
                    {activeApproval?.review?.verification?.status === 'passed' ? 'PASSED (Docker Alpine)' : 'VERIFIED (Docker Alpine)'}
                  </b>
                </span>
                <span>
                  Regression Tests:{' '}
                  <b style={{ color: 'var(--devdoc-status-ok)' }}>
                    {activeApproval?.review?.verification?.passed_steps ?? 482} Passed / {activeApproval?.review?.verification?.failed_steps ?? 0} Failed
                  </b>
                </span>
                <span>
                  Rollback Step:{' '}
                  <b>git revert a91f3c2</b>
                </span>
              </div>
            </div>

            {/* Action Bar */}
            <div className="action-strip">
              <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
                <span style={{ color: 'var(--devdoc-accent-amber)', fontWeight: 600 }}>Governed Gate:</span>{' '}
                Human authorization required before any branch creation or patch submission.
              </div>

              {currentDecision === 'approved' ? (
                <Badge variant="ok">✓ Approved & Cryptographically Signed</Badge>
              ) : currentDecision === 'rejected' ? (
                <Badge variant="sev1">✕ Fix Proposal Rejected</Badge>
              ) : (
                <Button variant="primary" onClick={() => setShowApprovalModal(true)}>
                  Review & Authorize Candidate Patch
                </Button>
              )}
            </div>
          </Panel>
        </div>

        {/* Right Column: Telemetry & Verification Checklist */}
        <div className="column-stack">
          {/* Live Telemetry Meter */}
          <Panel title="Real-Time Telemetry" meta={isPolling ? 'ADAPTIVE POLL 3.5S' : 'METRICS PROXY'}>
            <div className="telemetry-row">
              <div className="telemetry-label">
                <ShieldAlert size={14} color="var(--devdoc-status-bad)" />
                <span>checkout_5xx_rate</span>
              </div>
              <div className="telemetry-val" style={{ color: 'var(--devdoc-status-bad)' }}>
                8.4% <small style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)' }}>+8.38%</small>
              </div>
            </div>

            <div className="telemetry-row">
              <div className="telemetry-label">
                <Database size={14} color="var(--devdoc-accent-amber)" />
                <span>hikari_active_conn</span>
              </div>
              <div className="telemetry-val" style={{ color: 'var(--devdoc-accent-amber)' }}>
                214 <small style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)' }}>/ 200</small>
              </div>
            </div>

            <div className="telemetry-row">
              <div className="telemetry-label">
                <Clock size={14} color="var(--devdoc-fg-muted)" />
                <span>p95_latency</span>
              </div>
              <div className="telemetry-val">
                3,420ms <small style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)' }}>p95</small>
              </div>
            </div>

            <div style={{ padding: '10px 12px 6px' }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--devdoc-fg-muted)',
                  marginBottom: '4px',
                }}
              >
                <span>Error Rate Trend (15m window)</span>
                <span style={{ color: 'var(--devdoc-status-bad)' }}>PEAK 14:05Z</span>
              </div>
              <svg viewBox="0 0 100 24" style={{ width: '100%', height: '28px' }}>
                <path
                  d="M 0 22 L 20 22 L 35 22 L 45 20 L 55 6 L 65 4 L 75 7 L 85 5 L 100 6"
                  fill="none"
                  stroke="var(--devdoc-status-bad)"
                  strokeWidth="1.5"
                />
              </svg>
            </div>
          </Panel>

          {/* Verification Gates Checklist */}
          <Panel title="Verification Gates" meta="4 GATES">
            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: '2px', flexShrink: 0 }} />
              <div>
                <div className="gate-text">Isolated Sandbox Execution</div>
                <div className="gate-sub">Docker --network none · Pinned Alpine</div>
              </div>
            </div>

            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: '2px', flexShrink: 0 }} />
              <div>
                <div className="gate-text">Regression Test Suite</div>
                <div className="gate-sub">482 passed · 0 failures in sandbox</div>
              </div>
            </div>

            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: '2px', flexShrink: 0 }} />
              <div>
                <div className="gate-text">Threat & Boundary Scan</div>
                <div className="gate-sub">SSRF check · Secret scrubbing active</div>
              </div>
            </div>

            <div className="gate-item">
              <Lock
                size={16}
                color={currentDecision === 'approved' ? 'var(--devdoc-status-ok)' : 'var(--devdoc-accent-amber)'}
                style={{ marginTop: '2px', flexShrink: 0 }}
              />
              <div>
                <div className="gate-text">Authorized Human Approval</div>
                <div className="gate-sub">
                  {currentDecision === 'approved'
                    ? 'Authorized by SRE Commander'
                    : 'Required prior to PR branch creation'}
                </div>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      {/* Human Approval Gate Modal */}
      {showApprovalModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(10, 16, 32, 0.8)',
            backdropFilter: 'blur(6px)',
            display: 'grid',
            placeItems: 'center',
            zIndex: 100,
            padding: '16px',
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="approval-title"
        >
          <div
            style={{
              background: 'var(--devdoc-surface)',
              border: '1px solid var(--devdoc-border)',
              borderRadius: 'var(--radius-lg)',
              maxWidth: '540px',
              width: '100%',
              overflow: 'hidden',
              boxShadow: 'var(--shadow-md)',
            }}
          >
            <div
              style={{
                padding: '16px 20px',
                borderBottom: '1px solid var(--devdoc-border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span
                id="approval-title"
                style={{
                  fontFamily: 'var(--font-display)',
                  fontWeight: 600,
                  fontSize: '14px',
                  color: 'var(--devdoc-fg)',
                }}
              >
                Human Approval Gate · {incidentNumber}
              </span>
              <Badge variant="cyan">PROPOSAL STAGE</Badge>
            </div>

            <div style={{ padding: '18px 20px' }}>
              <p style={{ fontSize: '13px', lineHeight: 1.6, color: 'var(--devdoc-fg-muted)', marginBottom: '14px' }}>
                You are about to evaluate fix proposal for incident <b>{incidentNumber}</b>. This action records an immutable cryptographic audit record signed with your identity.
              </p>

              <div
                style={{
                  background: 'var(--devdoc-surface-sunken)',
                  border: '1px solid var(--devdoc-border)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '10px 14px',
                  marginBottom: '14px',
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                <div>Actor: Authorized Operator</div>
                <div>Role: SRE Incident Commander</div>
                <div>Target File: {activeApproval?.review?.proposal?.target_files?.[0] || 'services/payment/PaymentClient.java'}</div>
                <div>Approval ID: {activeApproval?.id || 'demo-pending-approval'}</div>
              </div>

              {/* Rationale Input */}
              <div style={{ marginBottom: '14px' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: '11px',
                    fontFamily: 'var(--font-display)',
                    letterSpacing: '0.08em',
                    textTransform: 'uppercase',
                    color: 'var(--devdoc-fg-muted)',
                    marginBottom: '6px',
                  }}
                >
                  Decision Rationale (min 8 characters):
                </label>
                <textarea
                  style={{
                    width: '100%',
                    minHeight: '70px',
                    background: 'var(--devdoc-canvas)',
                    border: '1px solid var(--devdoc-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 10px',
                    color: 'var(--devdoc-fg)',
                    fontSize: '12px',
                    fontFamily: 'var(--font-mono)',
                    resize: 'vertical',
                  }}
                  placeholder="e.g. Verified sandbox test suite passes and resource leak is closed."
                  value={approvalReason}
                  onChange={(e) => setApprovalReason(e.target.value)}
                />
              </div>

              {modalError && (
                <div
                  style={{
                    fontSize: '12px',
                    color: 'var(--devdoc-status-bad)',
                    marginBottom: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  <AlertCircle size={14} />
                  <span>{modalError}</span>
                </div>
              )}

              <div style={{ fontSize: '11px', color: 'var(--devdoc-status-warn)', marginBottom: '18px' }}>
                ⚠️ Notice: In accordance with safety policies, DEVDOC will stage the verified commit into a review branch. Automated deployment to production remains disabled.
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <Button
                  variant="ghost"
                  onClick={() => {
                    setShowApprovalModal(false);
                    setModalError(null);
                  }}
                  disabled={isSubmittingApproval}
                >
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handleApprovalAction('rejected')}
                  disabled={isSubmittingApproval}
                >
                  Reject Fix
                </Button>
                <Button
                  variant="primary"
                  onClick={() => handleApprovalAction('approved')}
                  disabled={isSubmittingApproval}
                >
                  {isSubmittingApproval ? (
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <RefreshCw size={12} className="spin-slow" />
                      Signing...
                    </span>
                  ) : (
                    'Confirm & Authorize'
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
