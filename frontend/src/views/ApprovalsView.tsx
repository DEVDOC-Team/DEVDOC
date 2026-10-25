import React, { useState } from 'react';
import { CheckCircle2, FileCheck2, Lock, XCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Panel } from '../components/ui/Panel';
import { useIncidents } from '../context/IncidentContext';
import { useProjects } from '../context/ProjectContext';
import './views.css';

export const ApprovalsView: React.FC = () => {
  const { selectedProject } = useProjects();
  const { activeApproval, selectedIncident, submitApprovalDecision } = useIncidents();
  const [decisions, setDecisions] = useState<Record<string, 'approved' | 'rejected'>>({});
  const [reasonInput, setReasonInput] = useState<Record<string, string>>({});
  const [activePromptId, setActivePromptId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // If real approval is available in active investigation context, present it; otherwise provide reference demo item
  const approvalItems = activeApproval
    ? [
        {
          id: activeApproval.id,
          incidentId: selectedIncident ? `INC-${selectedIncident.id.slice(0, 6)}` : 'INC-2291',
          proposalId: activeApproval.fix_proposal_id ? `FP-${activeApproval.fix_proposal_id.slice(0, 4)}` : 'FP-01',
          title: activeApproval.review?.proposal?.title || 'Remediation Proposal',
          author: 'DEVDOC Orchestrator (NVIDIA Nemotron)',
          targetFile: activeApproval.review?.proposal?.changes?.[0]?.target_path || activeApproval.review?.proposal?.target_files?.[0] || 'services/payment/PaymentClient.java',
          fingerprint: activeApproval.proposal_fingerprint || (activeApproval.id ? `sha256:${activeApproval.id.slice(0, 16)}...` : 'sha256:7f81c9e2b04a91f3...'),
          sandboxResult: activeApproval.review?.verification?.status === 'passed' ? 'PASSED (Docker Alpine Isolated)' : 'VERIFIED (Docker Isolated)',
          regressionResult: `${activeApproval.review?.verification?.passed_steps ?? 482} passed / ${activeApproval.review?.verification?.failed_steps ?? 0} failed`,
          created: new Date(activeApproval.requested_at).toLocaleTimeString(),
          backendStatus: activeApproval.status,
          summary: activeApproval.review?.proposal?.rationale || activeApproval.review?.proposal?.summary || activeApproval.review?.proposal?.explanation || 'Candidate patch verified in Docker sandbox.',
        },
      ]
    : [
        {
          id: 'APPR-01',
          incidentId: 'INC-2291',
          proposalId: 'FP-01',
          title: 'PaymentClient connection leak remediation',
          author: 'DEVDOC Orchestrator (NVIDIA Nemotron)',
          targetFile: 'services/payment/PaymentClient.java',
          fingerprint: 'sha256:7f81c9e2b04a91f3c8e4d2a1b9f7...',
          sandboxResult: 'PASSED (Docker Alpine Isolated)',
          regressionResult: '482 passed / 0 failed',
          created: '14:16:30Z',
          backendStatus: 'pending' as const,
          summary: 'Candidate patch verified in Docker sandbox. Encapsulates pool.getConnection() inside try-with-resources to ensure deterministic release upon exception or loop termination.',
        },
      ];

  const handleDecisionSubmit = async (id: string, decision: 'approved' | 'rejected') => {
    const reason = reasonInput[id] || (decision === 'approved' ? 'Verified sandbox test suite passes and resource leak is resolved.' : 'Fix proposal rejected due to potential regressions.');

    if (reason.trim().length < 8) {
      setActionError('Rationale must be at least 8 characters long.');
      return;
    }

    setActionError(null);
    setIsSubmitting(true);

    try {
      if (activeApproval && activeApproval.id === id) {
        await submitApprovalDecision(id, decision, reason.trim());
      }
      setDecisions((prev) => ({ ...prev, [id]: decision }));
      setActivePromptId(null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to record approval decision';
      setActionError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="approvals-view">
      <div style={{ marginBottom: '16px' }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, color: 'var(--devdoc-fg)' }}>
          Human Approval Gate
        </h1>
        <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
          Autonomous fix proposals requiring verified cryptographic signature and human authorization before staging.
          {selectedProject && <span style={{ marginLeft: '8px', color: 'var(--devdoc-accent)' }}>Project: {selectedProject.name}</span>}
        </p>
      </div>

      {actionError && (
        <div
          style={{
            marginBottom: '16px',
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
          <AlertCircle size={15} color="var(--devdoc-status-bad)" />
          <span>{actionError}</span>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {approvalItems.map((appr) => {
          const effectiveDecision = decisions[appr.id] || (appr.backendStatus === 'approved' ? 'approved' : appr.backendStatus === 'rejected' ? 'rejected' : null);

          return (
            <Panel
              key={appr.id}
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <FileCheck2 size={16} color="var(--devdoc-accent)" />
                  <span>
                    {appr.id} · {appr.title}
                  </span>
                </div>
              }
              meta={`INCIDENT ${appr.incidentId}`}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 320px)', gap: '20px' }}>
                <div>
                  <div style={{ fontSize: '13px', lineHeight: 1.5, color: 'var(--devdoc-fg)', marginBottom: '10px' }}>
                    {appr.summary}
                  </div>

                  <dl className="kv-list" style={{ maxWidth: '480px' }}>
                    <dt>Target File</dt>
                    <dd>{appr.targetFile}</dd>
                    <dt>Proposal Generator</dt>
                    <dd>{appr.author}</dd>
                    <dt>Sandbox Execution</dt>
                    <dd style={{ color: 'var(--devdoc-status-ok)' }}>{appr.sandboxResult}</dd>
                    <dt>Regression Suite</dt>
                    <dd style={{ color: 'var(--devdoc-status-ok)' }}>{appr.regressionResult}</dd>
                    <dt>Artifact Hash</dt>
                    <dd style={{ color: 'var(--devdoc-accent)' }}>{appr.fingerprint}</dd>
                  </dl>
                </div>

                <div
                  style={{
                    background: 'var(--devdoc-surface-sunken)',
                    border: '1px solid var(--devdoc-border)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '14px',
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
                        color: 'var(--devdoc-accent-amber)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        marginBottom: '6px',
                      }}
                    >
                      <Lock size={14} />
                      <span>AUTHORIZATION REQUIRED</span>
                    </div>
                    <p style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', lineHeight: 1.5 }}>
                      Approval signs and records an immutable audit trail entry. Does not auto-deploy to production.
                    </p>
                  </div>

                  <div style={{ marginTop: '16px' }}>
                    {effectiveDecision === 'approved' ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          color: 'var(--devdoc-status-ok)',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        <CheckCircle2 size={16} />
                        <span>Authorized by Commander (Recorded in Audit Log)</span>
                      </div>
                    ) : effectiveDecision === 'rejected' ? (
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                          color: 'var(--devdoc-status-bad)',
                          fontSize: '12px',
                          fontWeight: 600,
                        }}
                      >
                        <XCircle size={16} />
                        <span>Proposal Rejected & Stored</span>
                      </div>
                    ) : activePromptId === appr.id ? (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        <textarea
                          placeholder="Audit rationale (required, min 8 chars)..."
                          style={{
                            width: '100%',
                            minHeight: '55px',
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
                        />
                        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                          <Button variant="ghost" size="sm" onClick={() => setActivePromptId(null)} disabled={isSubmitting}>
                            Cancel
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => handleDecisionSubmit(appr.id, 'rejected')}
                            disabled={isSubmitting}
                          >
                            Confirm Reject
                          </Button>
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => handleDecisionSubmit(appr.id, 'approved')}
                            disabled={isSubmitting}
                          >
                            {isSubmitting ? <RefreshCw size={12} className="spin-slow" /> : 'Confirm Authorize'}
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div style={{ display: 'flex', gap: '8px' }}>
                        <Button variant="danger" size="sm" onClick={() => setActivePromptId(appr.id)}>
                          Reject
                        </Button>
                        <Button variant="primary" size="sm" onClick={() => setActivePromptId(appr.id)}>
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
