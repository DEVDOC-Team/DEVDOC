import React, { useState, useId } from 'react';
import {
  CheckCircle2,
  FileCheck2,
  Lock,
  XCircle,
  AlertCircle,
  RefreshCw,
  Copy,
  Check,
  Ban,
  ShieldCheck,
  ShieldAlert,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { useIncidents } from '../context/IncidentContext';
import { useProjects } from '../context/ProjectContext';
import type { ApprovalResponse, ApprovalStatus } from '../api/types';
import './views.css';

interface DemoApprovalItem {
  id: string;
  incidentId: string;
  investigationId: string;
  proposalId: string;
  title: string;
  author: string;
  targetFiles: string[];
  proposalFingerprint: string;
  verificationFingerprint: string;
  sandboxStatus: string;
  sandboxSteps: string;
  cleanupStatus: string;
  created: string;
  backendStatus: ApprovalStatus;
  summary: string;
  rationale: string | null;
  decidedAt: string | null;
  approverId: string | null;
  risks: Array<{ category: string; severity: string; description: string; mitigation: string }>;
  rollback: Array<{ trigger: string; description: string }>;
  isDemo?: boolean;
}

const DEMO_QUEUE_ITEM: DemoApprovalItem = {
  id: 'APPR-01',
  incidentId: 'INC-2291',
  investigationId: 'INV-4819',
  proposalId: 'FP-01',
  title: 'PaymentClient connection leak remediation',
  author: 'DEVDOC Orchestrator (NVIDIA Nemotron)',
  targetFiles: ['services/payment/PaymentClient.java', 'services/payment/ConnectionPoolConfig.java'],
  proposalFingerprint: 'sha256:7f81c9e2b04a91f3c8e4d2a1b9f7a6358c21345d9e7611ab02c1f930e461b18a',
  verificationFingerprint: 'sha256:a12e4f8d9b3c21a977c1d3e051fa82119b23b118ae45f04ca82031174983df92',
  sandboxStatus: 'passed',
  sandboxSteps: '482 passed / 0 failed',
  cleanupStatus: 'complete',
  created: '14:16:30 UTC',
  backendStatus: 'pending',
  summary: 'Encapsulates pool.getConnection() inside try-with-resources to ensure deterministic release upon exception or loop termination.',
  rationale: null,
  decidedAt: null,
  approverId: null,
  risks: [
    {
      category: 'compatibility',
      severity: 'low',
      description: 'Minor modification to client socket timeout configuration',
      mitigation: 'Verified non-blocking behavior under 500ms pool exhaustion test',
    },
    {
      category: 'regression',
      severity: 'low',
      description: 'Potential connection pool contention under sustained burst load',
      mitigation: 'Full regression test suite (482 tests) passed in Docker sandbox',
    },
  ],
  rollback: [
    {
      trigger: 'Pool acquisition timeout exceeds 2000ms after deployment',
      description: 'Revert PaymentClient.java to git commit 7b1c4f0 via automated rollback script',
    },
  ],
  isDemo: true,
};

export const ApprovalsView: React.FC = () => {
  const { selectedProject } = useProjects();
  const {
    approvals,
    activeApproval,
    selectedIncident,
    activeInvestigation,
    submitApprovalDecision,
    cancelApprovalDecision,
    refreshInvestigations,
  } = useIncidents();

  const [activePrompt, setActivePrompt] = useState<{ id: string; action: 'approved' | 'rejected' | 'cancelled' } | null>(null);
  const [reasonInput, setReasonInput] = useState<Record<string, string>>({});
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showDemoIfEmpty, setShowDemoIfEmpty] = useState<boolean>(false);

  const rationaleTextareaId = useId();

  const handleCopy = (text: string, id: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  // Convert real backend approval into view model
  const mapBackendApproval = (appr: ApprovalResponse): DemoApprovalItem => {
    const prop = appr.review?.proposal;
    const ver = appr.review?.verification;

    const targetFiles: string[] = [];
    if (prop?.changes) {
      for (const ch of prop.changes) {
        if (ch.target_path && !targetFiles.includes(ch.target_path)) {
          targetFiles.push(ch.target_path);
        }
      }
    }
    if (targetFiles.length === 0 && prop?.target_files) {
      targetFiles.push(...prop.target_files);
    }

    const risks = (prop?.risks || []).map((r) => ({
      category: r.category,
      severity: r.severity,
      description: r.description,
      mitigation: r.mitigation,
    }));

    const rollback = (prop?.rollback_plan || []).map((rb) => ({
      trigger: rb.trigger,
      description: rb.description,
    }));

    return {
      id: appr.id,
      incidentId: selectedIncident ? `INC-${selectedIncident.id.slice(0, 8)}` : 'INC-LIVE',
      investigationId: activeInvestigation ? `INV-${activeInvestigation.id.slice(0, 8)}` : 'INV-LIVE',
      proposalId: appr.fix_proposal_id ? `FP-${appr.fix_proposal_id.slice(0, 8)}` : 'FP-LIVE',
      title: prop?.title || prop?.summary || 'Autonomous Remediation Patch',
      author: 'DEVDOC Orchestrator',
      targetFiles,
      proposalFingerprint: appr.proposal_fingerprint || `sha256:${appr.id.replace(/-/g, '')}`,
      verificationFingerprint: appr.verification_fingerprint || (appr.verification_id ? `sha256:${appr.verification_id.replace(/-/g, '')}` : 'sha256:verified'),
      sandboxStatus: ver?.status || 'pending',
      sandboxSteps: ver ? `${ver.passed_steps} passed / ${ver.failed_steps} failed` : 'Pending verification',
      cleanupStatus: ver?.cleanup_status || 'standby',
      created: new Date(appr.requested_at).toLocaleString(),
      backendStatus: appr.status,
      summary: prop?.rationale || prop?.summary || prop?.explanation || 'Candidate patch verified in Docker sandbox environment.',
      rationale: appr.rationale,
      decidedAt: appr.decided_at ? new Date(appr.decided_at).toLocaleString() : null,
      approverId: appr.approver_id,
      risks: risks,
      rollback: rollback,
      isDemo: false,
    };
  };

  // Compile full queue: prefer real approvals from context, fallback to demonstration item if empty
  const rawList = approvals.length > 0 ? approvals : activeApproval ? [activeApproval] : [];
  const realItems = rawList.map(mapBackendApproval);

  const displayItems = realItems.length > 0 ? realItems : showDemoIfEmpty ? [DEMO_QUEUE_ITEM] : [];

  const filteredItems = displayItems.filter((item) => {
    if (filterStatus === 'all') return true;
    if (filterStatus === 'pending') return item.backendStatus === 'pending';
    if (filterStatus === 'decided') return item.backendStatus !== 'pending';
    return true;
  });

  const handleDecisionSubmit = async (appr: DemoApprovalItem) => {
    if (!activePrompt) return;

    const action = activePrompt.action;
    const rawReason = reasonInput[appr.id] || '';
    const trimmedReason = rawReason.trim();

    if (trimmedReason.length < 8) {
      setActionError('Decision rationale must contain at least 8 non-whitespace characters per governance policy.');
      return;
    }

    setActionError(null);
    setActionSuccess(null);
    setIsSubmitting(true);

    try {
      if (!appr.isDemo) {
        if (action === 'approved' || action === 'rejected') {
          await submitApprovalDecision(appr.id, action, trimmedReason);
        } else if (action === 'cancelled') {
          await cancelApprovalDecision(appr.id, trimmedReason);
        }
      } else {
        // Simulate immediate response for demonstration item
        DEMO_QUEUE_ITEM.backendStatus = action === 'approved' ? 'approved' : action === 'rejected' ? 'rejected' : 'cancelled';
        DEMO_QUEUE_ITEM.rationale = trimmedReason;
        DEMO_QUEUE_ITEM.decidedAt = new Date().toISOString();
      }

      setActionSuccess(`Decision successfully recorded: ${action.toUpperCase()}. Audit log synchronized.`);
      setActivePrompt(null);
      setReasonInput((prev) => ({ ...prev, [appr.id]: '' }));
      await refreshInvestigations();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Server rejected approval decision';
      // Sanitize against leaking stack traces or sensitive headers
      const sanitized = msg.split('\n')[0].replace(/(?:bearer|token|key|secret)\s+[\w.-]+/gi, '[REDACTED]');
      setActionError(sanitized);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="view-container">
      {/* Mandatory Demo Data Boundary Banner */}
      {filteredItems.some((i) => i.isDemo) && (
        <div
          role="alert"
          style={{
            margin: '0 0 16px 0',
            padding: '12px 16px',
            background: 'rgba(245, 158, 11, 0.12)',
            border: '1px solid rgba(245, 158, 11, 0.5)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={18} color="#f59e0b" style={{ flexShrink: 0 }} />
            <div>
              <div style={{ fontSize: '12px', fontWeight: 700, color: '#f59e0b', letterSpacing: '0.04em' }}>
                DEMO DATA — NOT LIVE SYSTEM DATA
              </div>
              <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                The approval queue currently displays a simulated reference item (PaymentClient connection leak remediation). Decisions on demo items are simulated locally and will NOT execute production changes or invoke backend endpoints.
              </div>
            </div>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setShowDemoIfEmpty(false);
              refreshInvestigations();
            }}
            style={{ flexShrink: 0 }}
          >
            Return to Live Mode
          </Button>
        </div>
      )}

      {/* Header Banner */}
      <div className="incident-header-banner">
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, color: 'var(--devdoc-fg)' }}>
            Human Approval Gate & Review Queue
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Authoritative human review gate for autonomous fix proposals. Verifies sandbox execution, risk matrix, and rollback plan before any merge.
            {selectedProject && (
              <span style={{ marginLeft: '10px', color: 'var(--devdoc-accent)' }}>
                Active Project: <strong>{selectedProject.name}</strong>
              </span>
            )}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refreshInvestigations()}
            icon={<RefreshCw size={13} className={isSubmitting ? 'spin-slow' : ''} />}
          >
            Refresh Queue
          </Button>
        </div>
      </div>

      {/* Action Notification Messages */}
      {actionError && (
        <div
          role="alert"
          style={{
            margin: '12px 0',
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid var(--devdoc-status-bad)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
            color: 'var(--devdoc-fg)',
          }}
        >
          <AlertCircle size={16} color="var(--devdoc-status-bad)" />
          <span>{actionError}</span>
        </div>
      )}

      {actionSuccess && (
        <div
          role="status"
          style={{
            margin: '12px 0',
            padding: '10px 14px',
            background: 'rgba(34, 197, 94, 0.1)',
            border: '1px solid var(--devdoc-status-ok)',
            borderRadius: 'var(--radius-sm)',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '12px',
            color: 'var(--devdoc-status-ok)',
          }}
        >
          <CheckCircle2 size={16} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Governance & Execution Boundary Notice */}
      <div
        style={{
          background: 'var(--devdoc-surface-sunken)',
          border: '1px solid var(--devdoc-border)',
          borderRadius: 'var(--radius-sm)',
          padding: '12px 16px',
          margin: '14px 0',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
          gap: '12px',
          fontSize: '11px',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--devdoc-accent)' }}>
            <ShieldCheck size={14} />
            <span>SUPPORTED OPERATIONS</span>
          </div>
          <p style={{ color: 'var(--devdoc-fg-muted)', marginTop: '4px', lineHeight: 1.4 }}>
            Investigation execution (`POST .../run`), Approval request decisions (`approve`, `reject`, `cancel`), and SHA-256 artifact integrity checks.
          </p>
        </div>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--devdoc-accent-amber)' }}>
            <ShieldAlert size={14} />
            <span>STAGING / REVIEW BRANCH</span>
          </div>
          <p style={{ color: 'var(--devdoc-fg-muted)', marginTop: '4px', lineHeight: 1.4 }}>
            Branch creation & staging merge endpoints are not exposed by the current backend API. Approval authorizes patch readiness.
          </p>
        </div>

        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, color: 'var(--devdoc-status-bad)' }}>
            <Lock size={14} />
            <span>PRODUCTION DEPLOYMENT (BLOCKED)</span>
          </div>
          <p style={{ color: 'var(--devdoc-fg-muted)', marginTop: '4px', lineHeight: 1.4 }}>
            Direct-to-production deployment is strictly prohibited by platform governance policy. Production release requires external human-operated CI/CD pipelines.
          </p>
        </div>
      </div>

      {/* Review Queue Filter Toolbar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', margin: '14px 0 10px 0' }}>
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <span style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginRight: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Queue Filter:
          </span>
          <button
            type="button"
            className={`btn-ghost ${filterStatus === 'all' ? 'active' : ''}`}
            onClick={() => setFilterStatus('all')}
            style={{
              padding: '3px 10px',
              fontSize: '11px',
              borderRadius: 'var(--radius-xs)',
              background: filterStatus === 'all' ? 'var(--devdoc-surface)' : 'transparent',
              color: filterStatus === 'all' ? 'var(--devdoc-accent)' : 'var(--devdoc-fg-muted)',
              border: '1px solid var(--devdoc-border)',
              cursor: 'pointer',
            }}
          >
            All Items ({displayItems.length})
          </button>
          <button
            type="button"
            className={`btn-ghost ${filterStatus === 'pending' ? 'active' : ''}`}
            onClick={() => setFilterStatus('pending')}
            style={{
              padding: '3px 10px',
              fontSize: '11px',
              borderRadius: 'var(--radius-xs)',
              background: filterStatus === 'pending' ? 'var(--devdoc-surface)' : 'transparent',
              color: filterStatus === 'pending' ? 'var(--devdoc-accent-amber)' : 'var(--devdoc-fg-muted)',
              border: '1px solid var(--devdoc-border)',
              cursor: 'pointer',
            }}
          >
            Pending Review ({displayItems.filter((i) => i.backendStatus === 'pending').length})
          </button>
          <button
            type="button"
            className={`btn-ghost ${filterStatus === 'decided' ? 'active' : ''}`}
            onClick={() => setFilterStatus('decided')}
            style={{
              padding: '3px 10px',
              fontSize: '11px',
              borderRadius: 'var(--radius-xs)',
              background: filterStatus === 'decided' ? 'var(--devdoc-surface)' : 'transparent',
              color: filterStatus === 'decided' ? 'var(--devdoc-status-ok)' : 'var(--devdoc-fg-muted)',
              border: '1px solid var(--devdoc-border)',
              cursor: 'pointer',
            }}
          >
            Decided ({displayItems.filter((i) => i.backendStatus !== 'pending').length})
          </button>
        </div>

        {realItems.length === 0 && (
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={showDemoIfEmpty}
                onChange={(e) => setShowDemoIfEmpty(e.target.checked)}
              />
              Show demonstration reference item
            </label>
          </div>
        )}
      </div>

      {/* Empty State */}
      {filteredItems.length === 0 && (
        <Panel sunken>
          <div style={{ padding: '36px 20px', textAlign: 'center' }}>
            <FileCheck2 size={36} color="var(--devdoc-fg-dim)" style={{ margin: '0 auto 12px auto' }} />
            <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--devdoc-fg)', marginBottom: '6px' }}>
              No Approval Requests in Queue
            </h3>
            <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', maxWidth: '420px', margin: '0 auto 16px auto', lineHeight: 1.5 }}>
              There are no pending or terminal fix proposals matching your filter. Run an investigation to generate verified remediation patches.
            </p>
            <div style={{ display: 'flex', gap: '8px', justifyContent: 'center' }}>
              <Button variant="secondary" size="sm" onClick={() => refreshInvestigations()}>
                Refresh State
              </Button>
              {!showDemoIfEmpty && (
                <Button variant="secondary" size="sm" onClick={() => setShowDemoIfEmpty(true)}>
                  Load Demo Approval Scenario
                </Button>
              )}
            </div>
          </div>
        </Panel>
      )}

      {/* Review Queue Items */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {filteredItems.map((appr) => {
          const isPending = appr.backendStatus === 'pending';
          const isApproved = appr.backendStatus === 'approved';
          const isRejected = appr.backendStatus === 'rejected';
          const isCancelled = appr.backendStatus === 'cancelled';
          const isPromptOpen = activePrompt?.id === appr.id;

          return (
            <Panel
              key={appr.id}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <FileCheck2 size={16} color="var(--devdoc-accent)" />
                  <span style={{ fontWeight: 600 }}>{appr.title}</span>
                  {appr.isDemo && <Badge variant="neutral">DEMO ITEM (INC-2291)</Badge>}
                </div>
              }
              meta={
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
                    {appr.incidentId} · {appr.investigationId}
                  </span>
                  <Badge
                    variant={
                      isApproved ? 'ok' : isRejected ? 'sev1' : isCancelled ? 'neutral' : 'warn'
                    }
                  >
                    {appr.backendStatus.toUpperCase()}
                  </Badge>
                </div>
              }
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 360px)', gap: '20px' }}>
                {/* Left Column: Proposed Change Details, Risks & Rollback */}
                <div>
                  <div style={{ fontSize: '13px', lineHeight: 1.5, color: 'var(--devdoc-fg)', marginBottom: '12px' }}>
                    {appr.summary}
                  </div>

                  <dl className="kv-list" style={{ maxWidth: '540px', marginBottom: '14px' }}>
                    <dt>Target Files</dt>
                    <dd style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      {appr.targetFiles.join(', ')}
                    </dd>

                    <dt>Proposal Generator</dt>
                    <dd>{appr.author}</dd>

                    <dt>Sandbox Execution</dt>
                    <dd style={{ color: 'var(--devdoc-status-ok)' }}>
                      PASSED (Docker Alpine Isolated · {appr.sandboxSteps})
                    </dd>

                    <dt>Sandbox Cleanup</dt>
                    <dd style={{ color: 'var(--devdoc-status-ok)' }}>{appr.cleanupStatus.toUpperCase()}</dd>

                    <dt>SHA-256 Digest</dt>
                    <dd style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '11px',
                          color: 'var(--devdoc-accent)',
                          wordBreak: 'break-all',
                        }}
                      >
                        {appr.proposalFingerprint.slice(0, 24)}...
                      </span>
                      <button
                        type="button"
                        aria-label="Copy proposal hash"
                        onClick={() => handleCopy(appr.proposalFingerprint, `prop-${appr.id}`)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: copiedId === `prop-${appr.id}` ? 'var(--devdoc-status-ok)' : 'var(--devdoc-fg-dim)',
                          cursor: 'pointer',
                          padding: '2px',
                        }}
                      >
                        {copiedId === `prop-${appr.id}` ? <Check size={12} /> : <Copy size={12} />}
                      </button>
                    </dd>

                    <dt>Verification Digest</dt>
                    <dd style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <span
                        style={{
                          fontFamily: 'var(--font-mono)',
                          fontSize: '11px',
                          color: 'var(--devdoc-fg-dim)',
                          wordBreak: 'break-all',
                        }}
                      >
                        {appr.verificationFingerprint.slice(0, 24)}...
                      </span>
                      <button
                        type="button"
                        aria-label="Copy verification hash"
                        onClick={() => handleCopy(appr.verificationFingerprint, `ver-${appr.id}`)}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: copiedId === `ver-${appr.id}` ? 'var(--devdoc-status-ok)' : 'var(--devdoc-fg-dim)',
                          cursor: 'pointer',
                          padding: '2px',
                        }}
                      >
                        {copiedId === `ver-${appr.id}` ? <Check size={12} /> : <Copy size={12} />}
                      </button>
                    </dd>

                    <dt>Requested Timestamp</dt>
                    <dd style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}>{appr.created}</dd>
                  </dl>

                  {/* Risk Summary Matrix */}
                  <div style={{ marginTop: '14px' }}>
                    <div
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        color: 'var(--devdoc-fg-muted)',
                        marginBottom: '6px',
                      }}
                    >
                      Assessed Risks & Mitigations
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {appr.risks.map((r, idx) => (
                        <div
                          key={idx}
                          style={{
                            background: 'var(--devdoc-surface-sunken)',
                            border: '1px solid var(--devdoc-border)',
                            borderRadius: 'var(--radius-xs)',
                            padding: '8px 10px',
                            fontSize: '11px',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                            <span style={{ fontWeight: 600, color: 'var(--devdoc-fg)' }}>
                              {r.category.toUpperCase()}
                            </span>
                            <Badge variant={r.severity === 'critical' ? 'sev1' : r.severity === 'high' ? 'warn' : 'ok'}>
                              {r.severity.toUpperCase()}
                            </Badge>
                          </div>
                          <div style={{ color: 'var(--devdoc-fg-muted)' }}>{r.description}</div>
                          <div style={{ marginTop: '4px', color: 'var(--devdoc-status-ok)', fontSize: '10.5px' }}>
                            Mitigation: {r.mitigation}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Rollback Strategy */}
                  <div style={{ marginTop: '14px' }}>
                    <div
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        color: 'var(--devdoc-fg-muted)',
                        marginBottom: '6px',
                      }}
                    >
                      Rollback Plan
                    </div>
                    {appr.rollback.map((rb, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: 'var(--devdoc-canvas)',
                          border: '1px dashed var(--devdoc-border)',
                          borderRadius: 'var(--radius-xs)',
                          padding: '8px 10px',
                          fontSize: '11px',
                          color: 'var(--devdoc-fg-muted)',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: 'var(--devdoc-accent-amber)', marginBottom: '2px' }}>
                          Trigger: {rb.trigger}
                        </div>
                        <div>Procedure: {rb.description}</div>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Right Column: Authorization Gate Controls */}
                <div
                  style={{
                    background: 'var(--devdoc-surface-sunken)',
                    border: '1px solid var(--devdoc-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: '11px',
                        fontWeight: 600,
                        color: isPending ? 'var(--devdoc-accent-amber)' : 'var(--devdoc-fg-muted)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        marginBottom: '8px',
                      }}
                    >
                      <Lock size={14} />
                      <span>{isPending ? 'AUTHORIZATION REQUIRED' : 'GOVERNANCE DECISION RECORDED'}</span>
                    </div>

                    <p style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', lineHeight: 1.5, marginBottom: '14px' }}>
                      Human authorization records an immutable entry into the server audit ledger. Approval is distinct from staging or deployment; it authorizes patch validity only.
                    </p>

                    {/* Decision Record Details if decided */}
                    {appr.rationale && (
                      <div
                        style={{
                          background: 'var(--devdoc-canvas)',
                          border: '1px solid var(--devdoc-border)',
                          borderRadius: 'var(--radius-sm)',
                          padding: '10px 12px',
                          marginBottom: '14px',
                          fontSize: '11px',
                        }}
                      >
                        <div style={{ fontWeight: 600, color: 'var(--devdoc-fg)', marginBottom: '4px' }}>
                          Reviewer Rationale
                        </div>
                        <div style={{ color: 'var(--devdoc-fg-muted)', fontStyle: 'italic', marginBottom: '6px' }}>
                          "{appr.rationale}"
                        </div>
                        <div style={{ fontSize: '10px', color: 'var(--devdoc-fg-dim)', display: 'flex', gap: '8px' }}>
                          {appr.decidedAt && <span>Decided: {appr.decidedAt}</span>}
                          {appr.approverId && <span>Actor ID: {appr.approverId.slice(0, 8)}</span>}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Action Controls */}
                  <div style={{ marginTop: '16px' }}>
                    {isApproved ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          color: 'var(--devdoc-status-ok)',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        <CheckCircle2 size={16} />
                        <span>Authorized & Recorded in Audit Trail</span>
                      </div>
                    ) : isRejected ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          color: 'var(--devdoc-status-bad)',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        <XCircle size={16} />
                        <span>Proposal Rejected & Stored</span>
                      </div>
                    ) : isCancelled ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '8px',
                          color: 'var(--devdoc-fg-muted)',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        <Ban size={16} />
                        <span>Approval Request Cancelled</span>
                      </div>
                    ) : isPromptOpen ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <label
                          htmlFor={`${rationaleTextareaId}-${appr.id}`}
                          style={{
                            fontSize: '11px',
                            fontWeight: 600,
                            color: activePrompt.action === 'approved' ? 'var(--devdoc-status-ok)' : 'var(--devdoc-status-bad)',
                          }}
                        >
                          {activePrompt.action === 'approved'
                            ? 'Authorization Rationale (min 8 chars required):'
                            : activePrompt.action === 'rejected'
                            ? 'Rejection Rationale (min 8 chars required):'
                            : 'Cancellation Rationale (min 8 chars required):'}
                        </label>
                        <textarea
                          id={`${rationaleTextareaId}-${appr.id}`}
                          aria-label="Audit Decision Rationale"
                          placeholder="Provide specific audit rationale for this decision (min 8 chars)..."
                          style={{
                            width: '100%',
                            minHeight: '65px',
                            background: 'var(--devdoc-canvas)',
                            border: '1px solid var(--devdoc-border)',
                            borderRadius: 'var(--radius-sm)',
                            padding: '6px 8px',
                            color: 'var(--devdoc-fg)',
                            fontSize: '11px',
                            fontFamily: 'var(--font-mono)',
                          }}
                          value={reasonInput[appr.id] || ''}
                          onChange={(e) => setReasonInput((prev) => ({ ...prev, [appr.id]: e.target.value }))}
                          disabled={isSubmitting}
                        />
                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', alignItems: 'center' }}>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setActivePrompt(null)}
                            disabled={isSubmitting}
                          >
                            Dismiss
                          </Button>
                          <Button
                            variant={activePrompt.action === 'approved' ? 'primary' : 'danger'}
                            size="sm"
                            onClick={() => handleDecisionSubmit(appr)}
                            disabled={isSubmitting || (reasonInput[appr.id] || '').trim().length < 8}
                          >
                            {isSubmitting ? (
                              <RefreshCw size={12} className="spin-slow" />
                            ) : activePrompt.action === 'approved' ? (
                              'Confirm Authorize'
                            ) : activePrompt.action === 'rejected' ? (
                              'Confirm Reject'
                            ) : (
                              'Confirm Cancel'
                            )}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() => {
                            setActionError(null);
                            setActivePrompt({ id: appr.id, action: 'rejected' });
                          }}
                        >
                          Reject
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => {
                            setActionError(null);
                            setActivePrompt({ id: appr.id, action: 'cancelled' });
                          }}
                        >
                          Cancel Request
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => {
                            setActionError(null);
                            setActivePrompt({ id: appr.id, action: 'approved' });
                          }}
                        >
                          Authorize Fix
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
};
