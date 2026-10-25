import React, { useState } from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Shield, FileCheck, Search, Download, CheckCircle2 } from 'lucide-react';

interface AuditRecord {
  id: string;
  timestamp: string;
  actor: string;
  actorType: 'AI_AGENT' | 'HUMAN' | 'GATEKEEPER';
  action: string;
  target: string;
  verdict: 'ALLOWED' | 'RESTRICTED' | 'VERIFIED' | 'SIGNED';
  hash: string;
  details: string;
}

const AUDIT_RECORDS: AuditRecord[] = [
  {
    id: 'AUD-9014',
    timestamp: '2026-10-25 06:41:18 UTC',
    actor: 'sarah.c@devdoc.internal',
    actorType: 'HUMAN',
    action: 'APPROVAL_SIGN_OFF',
    target: 'PR #142 (fix/connection-pool-ceiling)',
    verdict: 'SIGNED',
    hash: '0e4f8d...c1a9',
    details: 'Human peer reviewed sandbox test suite and signed zero-drop patch execution.'
  },
  {
    id: 'AUD-9013',
    timestamp: '2026-10-25 06:39:55 UTC',
    actor: 'sandbox-verifier',
    actorType: 'GATEKEEPER',
    action: 'RUN_TEST_CONTAINER',
    target: 'docker:devdoc-sandbox-worker-pool:latest',
    verdict: 'VERIFIED',
    hash: 'fa8211...9b23',
    details: 'Executed 12 automated unit and integration tests. 12 passed, 0 failures.'
  },
  {
    id: 'AUD-9012',
    timestamp: '2026-10-25 06:38:12 UTC',
    actor: 'nebius-nemotron-70b',
    actorType: 'AI_AGENT',
    action: 'GENERATE_PATCH',
    target: 'worker/pool.py:L142-L148',
    verdict: 'ALLOWED',
    hash: '77c1d3...e051',
    details: 'Proposed safe fallback default 20 -> 50 with try/finally release semantics.'
  },
  {
    id: 'AUD-9011',
    timestamp: '2026-10-25 06:35:40 UTC',
    actor: 'policy-guard',
    actorType: 'GATEKEEPER',
    action: 'CHECK_PRIVILEGE_BOUNDARY',
    target: 'db:connection-leak-investigation',
    verdict: 'ALLOWED',
    hash: 'b118ae...45f0',
    details: 'Read-only log & metrics inspection verified under SOC2 rule #DEVDOC-RO-01.'
  },
  {
    id: 'AUD-9010',
    timestamp: '2026-10-25 06:34:02 UTC',
    actor: 'github-agent',
    actorType: 'AI_AGENT',
    action: 'PULL_COMMIT_DIFF',
    target: 'commit 7b1c4f0',
    verdict: 'ALLOWED',
    hash: '4ca820...3117',
    details: 'Fetched diff for commit introducing MAX_CONNECTIONS=10.'
  }
];

export const AuditView: React.FC = () => {
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState<string>('ALL');

  const filtered = AUDIT_RECORDS.filter(record => {
    const matchesSearch = record.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      record.action.toLowerCase().includes(searchTerm.toLowerCase()) ||
      record.target.toLowerCase().includes(searchTerm.toLowerCase()) ||
      record.actor.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesType = filterType === 'ALL' || record.actorType === filterType;
    return matchesSearch && matchesType;
  });

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Cryptographic Audit Ledger
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Tamper-evident record of all AI actions, container sandbox executions, and human sign-offs.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="secondary" size="sm" icon={<Download size={14} />}>
            Export Audit Bundle
          </Button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', marginTop: '14px', marginBottom: '16px' }}>
        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Total Signed Events</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>1,842</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-ok)', marginTop: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={12} /> Merkle root verified
          </div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>AI Invocations</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-accent)', marginTop: '4px' }}>1,120</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>NVIDIA Nemotron 70B & 496 RAG runs</div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Human Interventions</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-fg)', marginTop: '4px' }}>24</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>100% two-person gate adherence</div>
        </Panel>

        <Panel sunken>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Policy Violations</div>
          <div style={{ fontSize: '24px', fontFamily: 'var(--font-display)', fontWeight: 600, color: 'var(--devdoc-ok)', marginTop: '4px' }}>0</div>
          <div style={{ fontSize: '11px', color: 'var(--devdoc-ok)', marginTop: '4px' }}>Zero-unapproved write attempts</div>
        </Panel>
      </div>

      <Panel
        title="Event Ledger"
        meta={
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                placeholder="Filter by hash, actor or action..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{
                  background: 'var(--devdoc-surface-sunken)',
                  border: '1px solid var(--devdoc-border)',
                  color: 'var(--devdoc-fg)',
                  borderRadius: 'var(--radius-sm)',
                  padding: '4px 8px 4px 26px',
                  fontSize: '11px',
                  width: '210px'
                }}
              />
              <Search size={12} style={{ position: 'absolute', left: '8px', top: '7px', color: 'var(--devdoc-fg-dim)' }} />
            </div>
            <select
              value={filterType}
              onChange={e => setFilterType(e.target.value)}
              style={{
                background: 'var(--devdoc-surface-sunken)',
                border: '1px solid var(--devdoc-border)',
                color: 'var(--devdoc-fg)',
                borderRadius: 'var(--radius-sm)',
                padding: '4px 8px',
                fontSize: '11px'
              }}
            >
              <option value="ALL">All Actors</option>
              <option value="AI_AGENT">AI Agents</option>
              <option value="HUMAN">Human Engineers</option>
              <option value="GATEKEEPER">Gatekeepers</option>
            </select>
          </div>
        }
      >
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--devdoc-border)', color: 'var(--devdoc-fg-muted)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                <th style={{ padding: '8px 12px' }}>Event ID</th>
                <th style={{ padding: '8px 12px' }}>Timestamp</th>
                <th style={{ padding: '8px 12px' }}>Actor</th>
                <th style={{ padding: '8px 12px' }}>Action</th>
                <th style={{ padding: '8px 12px' }}>Target</th>
                <th style={{ padding: '8px 12px' }}>Verdict</th>
                <th style={{ padding: '8px 12px' }}>SHA-256 Fingerprint</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(record => (
                <tr key={record.id} style={{ borderBottom: '1px solid var(--devdoc-border)', transition: 'background var(--transition-fast)' }} className="table-row-hover">
                  <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-accent)', fontWeight: 600 }}>
                    {record.id}
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
                    {record.action}
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--devdoc-fg-muted)' }}>
                    {record.target}
                  </td>
                  <td style={{ padding: '10px 12px' }}>
                    <Badge variant={record.verdict === 'ALLOWED' || record.verdict === 'VERIFIED' || record.verdict === 'SIGNED' ? 'ok' : 'warn'}>
                      {record.verdict}
                    </Badge>
                  </td>
                  <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-dim)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <FileCheck size={12} />
                      {record.hash}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
};
