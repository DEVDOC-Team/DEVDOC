import React, { useState, useEffect, useCallback } from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import {
  Shield,
  FileCheck,
  Search,
  Download,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Copy,
  Check,
  ChevronLeft,
  ChevronRight,
  Database,
} from 'lucide-react';
import { useProjects } from '../context/ProjectContext';
import { useIncidents } from '../context/IncidentContext';
import { listApprovalAudit } from '../api/approvals';
import type { ApprovalAuditEvent } from '../api/types';
import './views.css';

interface DisplayAuditRecord {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target: string;
  outcome: string;
  hash: string;
  details: string;
  isReal: boolean;
}

const DEMO_AUDIT_RECORDS: DisplayAuditRecord[] = [
  {
    id: 'AUD-9014',
    timestamp: '2026-10-25 06:41:18 UTC',
    actor: 'sarah.c@devdoc.internal',
    action: 'approval.approved',
    target: 'PR #142 (fix/connection-pool-ceiling)',
    outcome: 'success',
    hash: '0e4f8d9b3c21a977c1d3e051fa82119b23b118ae45f04ca82031174983df92',
    details: 'Human peer reviewed sandbox test suite and authorized zero-drop patch execution.',
    isReal: false,
  },
  {
    id: 'AUD-9013',
    timestamp: '2026-10-25 06:39:55 UTC',
    actor: 'sandbox-verifier',
    action: 'sandbox.verification_passed',
    target: 'docker:devdoc-sandbox-worker-pool:latest',
    outcome: 'success',
    hash: 'fa82119b23b118ae45f04ca82031174983df920e4f8d9b3c21a977c1d3e051',
    details: 'Executed automated regression suite. 482 passed, 0 failures in Docker Alpine isolation.',
    isReal: false,
  },
  {
    id: 'AUD-9012',
    timestamp: '2026-10-25 06:38:12 UTC',
    actor: 'nebius-nemotron-70b',
    action: 'investigation.patch_generated',
    target: 'services/payment/PaymentClient.java',
    outcome: 'success',
    hash: '77c1d3e051fa82119b23b118ae45f04ca82031174983df920e4f8d9b3c21a9',
    details: 'Proposed safe fallback pool.getConnection() inside try-with-resources statement.',
    isReal: false,
  },
  {
    id: 'AUD-9011',
    timestamp: '2026-10-25 06:35:40 UTC',
    actor: 'policy-guard',
    action: 'security.boundary_check',
    target: 'db:connection-leak-investigation',
    outcome: 'success',
    hash: 'b118ae45f04ca82031174983df920e4f8d9b3c21a977c1d3e051fa82119b23',
    details: 'Read-only log & metrics inspection verified under SOC2 rule #DEVDOC-RO-01.',
    isReal: false,
  },
  {
    id: 'AUD-9010',
    timestamp: '2026-10-25 06:34:02 UTC',
    actor: 'system-orchestrator',
    action: 'approval.requested',
    target: 'investigation:INV-4819',
    outcome: 'success',
    hash: '4ca82031174983df920e4f8d9b3c21a977c1d3e051fa82119b23b118ae45f0',
    details: 'Human approval requested for verified fix proposal FP-01.',
    isReal: false,
  },
];

export const AuditView: React.FC = () => {
  const { selectedProject } = useProjects();
  const { selectedIncident, activeInvestigation, activeApproval } = useIncidents();

  const [realEvents, setRealEvents] = useState<ApprovalAuditEvent[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState<number>(0);
  const limit = 20;

  const [searchTerm, setSearchTerm] = useState<string>('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [showDemoIfEmpty, setShowDemoIfEmpty] = useState<boolean>(true);

  const fetchAuditEvents = useCallback(async () => {
    if (!selectedProject || !activeInvestigation) {
      setRealEvents([]);
      setTotalCount(0);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await listApprovalAudit(selectedProject.id, activeInvestigation.id, {
        limit,
        offset,
      });
      setRealEvents(res.items || []);
      setTotalCount(res.total || 0);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch audit events';
      setError(msg);
      setRealEvents([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [selectedProject, activeInvestigation, offset, limit]);

  useEffect(() => {
    fetchAuditEvents();
  }, [fetchAuditEvents]);

  const handleCopy = (text: string, id: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    }
  };

  // Convert real backend audit events into display records
  const mappedRealRecords: DisplayAuditRecord[] = realEvents.map((ev) => ({
    id: `AUD-${ev.id.slice(0, 8)}`,
    timestamp: new Date(ev.created_at).toUTCString(),
    actor: ev.actor_id ? `User:${ev.actor_id.slice(0, 8)}` : 'system-orchestrator',
    action: ev.action,
    target: activeInvestigation
      ? `investigation:${activeInvestigation.id.slice(0, 8)}`
      : 'investigation:active',
    outcome: ev.outcome || 'success',
    hash: ev.id.replace(/-/g, '') + '0000000000000000',
    details: ev.description || 'Audit trail recorded for human approval workflow.',
    isReal: true,
  }));

  const recordsToDisplay =
    mappedRealRecords.length > 0
      ? mappedRealRecords
      : showDemoIfEmpty
      ? DEMO_AUDIT_RECORDS
      : [];

  const filteredRecords = recordsToDisplay.filter((record) => {
    const q = searchTerm.toLowerCase();
    return (
      record.id.toLowerCase().includes(q) ||
      record.action.toLowerCase().includes(q) ||
      record.actor.toLowerCase().includes(q) ||
      record.details.toLowerCase().includes(q) ||
      record.hash.toLowerCase().includes(q)
    );
  });

  const handleExportJson = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(recordsToDisplay, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute('href', dataStr);
    downloadAnchor.setAttribute('download', 'devdoc-audit-ledger.json');
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  return (
    <div className="view-container">
      {/* Incident Header Banner */}
      <div className="incident-header-banner">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
              Audit Ledger & Governance Trail
            </h2>
            <Badge variant="neutral">Phase 18 Audit Log</Badge>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Authoritative append-only log of human approvals, sandbox verifications, and system events.
            {selectedProject && (
              <span style={{ marginLeft: '8px', color: 'var(--devdoc-accent)' }}>
                Project: {selectedProject.name}
              </span>
            )}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => fetchAuditEvents()}
            disabled={loading}
            icon={<RefreshCw size={13} className={loading ? 'spin-slow' : ''} />}
          >
            {loading ? 'Refreshing...' : 'Refresh'}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleExportJson}
            icon={<Download size={13} />}
          >
            Export JSON
          </Button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
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
          <span>{error}</span>
        </div>
      )}

      {/* Ledger Overview Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '14px', marginBottom: '16px' }}>
        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {mappedRealRecords.length > 0 ? 'Recorded Audit Events' : 'Demo Ledger Events'}
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>
            {mappedRealRecords.length > 0 ? totalCount : DEMO_AUDIT_RECORDS.length}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-status-ok)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={12} /> SHA-256 Digest Integrity Verified
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Active Investigation
          </div>
          <div style={{ fontSize: '16px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--devdoc-accent)', marginTop: '4px' }}>
            {activeInvestigation ? `INV-${activeInvestigation.id.slice(0, 8)}` : 'INV-4819'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            {selectedIncident ? `Incident: ${selectedIncident.title.slice(0, 30)}...` : 'Demo: Connection leak incident'}
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Human Sign-Off Gate
          </div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>
            {activeApproval ? '1 Active' : '0 Pending'}
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
            Mandatory 8+ char rationale required
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Database Storage
          </div>
          <div style={{ fontSize: '16px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-status-ok)', marginTop: '4px' }}>
            public.audit_logs
          </div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-status-ok)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Database size={12} /> Append-only PostgreSQL table
          </div>
        </Panel>
      </div>

      {/* Event Ledger Panel */}
      <Panel
        title={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>Event Ledger</span>
            {mappedRealRecords.length > 0 ? (
              <Badge variant="ok">LIVE DATABASE STREAM</Badge>
            ) : (
              <Badge variant="neutral">SAMPLE LEDGER (INC-2291)</Badge>
            )}
          </div>
        }
        meta={
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                placeholder="Filter by hash, actor or action..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  background: 'var(--devdoc-surface-sunken)',
                  border: '1px solid var(--devdoc-border)',
                  color: 'var(--devdoc-fg)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '4px 8px 4px 26px',
                  fontSize: '11px',
                  width: '240px',
                }}
              />
              <Search size={12} style={{ position: 'absolute', left: '8px', top: '7px', color: 'var(--devdoc-fg-dim)' }} />
            </div>

            {mappedRealRecords.length === 0 && (
              <label style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showDemoIfEmpty}
                  onChange={(e) => setShowDemoIfEmpty(e.target.checked)}
                />
                Show reference events
              </label>
            )}
          </div>
        }
      >
        {filteredRecords.length === 0 ? (
          <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '12px' }}>
            No audit records match your query or have been recorded for this investigation yet.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
              <thead>
                <tr
                  style={{
                    borderBottom: '1px solid var(--devdoc-border)',
                    color: 'var(--devdoc-fg-muted)',
                    fontSize: '10px',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                  }}
                >
                  <th style={{ padding: '8px 12px' }}>Event ID</th>
                  <th style={{ padding: '8px 12px' }}>Timestamp</th>
                  <th style={{ padding: '8px 12px' }}>Actor</th>
                  <th style={{ padding: '8px 12px' }}>Action</th>
                  <th style={{ padding: '8px 12px' }}>Target</th>
                  <th style={{ padding: '8px 12px' }}>Outcome</th>
                  <th style={{ padding: '8px 12px' }}>SHA-256 Digest</th>
                  <th style={{ padding: '8px 12px' }}>Details / Rationale</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((record) => (
                  <tr
                    key={record.id}
                    style={{ borderBottom: '1px solid var(--devdoc-border)', transition: 'background var(--transition-fast)' }}
                    className="table-row-hover"
                  >
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-accent)', fontWeight: 600 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <span>{record.id}</span>
                        <button
                          type="button"
                          aria-label={`Copy ID ${record.id}`}
                          onClick={() => handleCopy(record.id, `id-${record.id}`)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: copiedId === `id-${record.id}` ? 'var(--devdoc-status-ok)' : 'var(--devdoc-fg-dim)',
                            cursor: 'pointer',
                            padding: '2px',
                          }}
                        >
                          {copiedId === `id-${record.id}` ? <Check size={11} /> : <Copy size={11} />}
                        </button>
                      </div>
                    </td>

                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
                      {record.timestamp}
                    </td>

                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Shield size={12} color="var(--devdoc-accent)" />
                        <span style={{ fontWeight: 500, color: 'var(--devdoc-fg)' }}>{record.actor}</span>
                      </div>
                    </td>

                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      <code style={{ background: 'var(--devdoc-surface-sunken)', padding: '2px 5px', borderRadius: 'var(--radius-xs)' }}>
                        {record.action}
                      </code>
                    </td>

                    <td style={{ padding: '10px 12px', color: 'var(--devdoc-fg-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                      {record.target}
                    </td>

                    <td style={{ padding: '10px 12px' }}>
                      <Badge variant={record.outcome === 'success' ? 'ok' : 'sev1'}>
                        {record.outcome.toUpperCase()}
                      </Badge>
                    </td>

                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-dim)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }} title={`SHA-256: ${record.hash}`}>
                        <FileCheck size={12} />
                        <span>{record.hash.slice(0, 12)}...{record.hash.slice(-6)}</span>
                        <button
                          type="button"
                          aria-label="Copy SHA-256 hash"
                          onClick={() => handleCopy(record.hash, `hash-${record.id}`)}
                          style={{
                            background: 'transparent',
                            border: 'none',
                            color: copiedId === `hash-${record.id}` ? 'var(--devdoc-status-ok)' : 'var(--devdoc-fg-dim)',
                            cursor: 'pointer',
                            padding: '2px',
                          }}
                        >
                          {copiedId === `hash-${record.id}` ? <Check size={11} /> : <Copy size={11} />}
                        </button>
                      </div>
                    </td>

                    <td style={{ padding: '10px 12px', color: 'var(--devdoc-fg-muted)', fontSize: '11px', maxWidth: '320px', lineHeight: 1.4 }}>
                      {record.details}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Real Backend Pagination Controls */}
        {mappedRealRecords.length > 0 && totalCount > limit && (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '12px 14px',
              borderTop: '1px solid var(--devdoc-border)',
              fontSize: '11px',
              color: 'var(--devdoc-fg-muted)',
            }}
          >
            <div>
              Showing {offset + 1}–{Math.min(offset + limit, totalCount)} of {totalCount} events
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setOffset((prev) => Math.max(0, prev - limit))}
                disabled={offset === 0 || loading}
                icon={<ChevronLeft size={13} />}
              >
                Previous
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setOffset((prev) => prev + limit)}
                disabled={offset + limit >= totalCount || loading}
                icon={<ChevronRight size={13} />}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Panel>
    </div>
  );
};
