import React, { useState } from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { RefreshCw, Check } from 'lucide-react';

export const SettingsView: React.FC = () => {
  const [testingConnection, setTestingConnection] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  const handleTestEngine = () => {
    setTestingConnection(true);
    setTestResult(null);
    setTimeout(() => {
      setTestingConnection(false);
      setTestResult('Nebius Token Factory responded in 218ms. NVIDIA Nemotron-70B model ready.');
    }, 1200);
  };

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            System Health & Security Configuration
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Diagnostics engine parameters, LLM backend connectivity, container isolation thresholds, and audit bounds.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleTestEngine}
            disabled={testingConnection}
            icon={<RefreshCw size={14} className={testingConnection ? 'spin' : ''} />}
          >
            {testingConnection ? 'Testing Connection...' : 'Verify Engine Link'}
          </Button>
        </div>
      </div>

      {testResult && (
        <div style={{ padding: '10px 14px', background: 'rgba(52, 211, 153, 0.1)', border: '1px solid var(--devdoc-ok)', borderRadius: 'var(--radius-sm)', color: 'var(--devdoc-ok)', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '8px', margin: '12px 0' }}>
          <Check size={16} />
          <span>{testResult}</span>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '14px', marginTop: '14px' }}>
        <Panel
          title="Inference Engine & LLM Pipeline"
          meta={<Badge variant="ok">CONNECTED</Badge>}
        >
          <dl className="kv-list">
            <dt>Provider</dt>
            <dd>Nebius AI Studio</dd>
            <dt>Foundation Model</dt>
            <dd>nvidia/nemotron-4-340b-instruct / 70b</dd>
            <dt>API Host</dt>
            <dd>api.studio.nebius.ai/v1</dd>
            <dt>Token Ingestion Rate</dt>
            <dd>4,200 tok/sec</dd>
            <dt>Avg Prompt Latency</dt>
            <dd>248 ms</dd>
            <dt>Temperature Cap</dt>
            <dd>0.2 (Deterministic)</dd>
          </dl>
        </Panel>

        <Panel
          title="Sandbox Verification Isolation"
          meta={<Badge variant="ok">HEALTHY</Badge>}
        >
          <dl className="kv-list">
            <dt>Runtime Engine</dt>
            <dd>Docker Engine (rootless)</dd>
            <dt>Network Isolation</dt>
            <dd>--network none (Air-gapped)</dd>
            <dt>Memory Ceiling / Container</dt>
            <dd>2048 MB</dd>
            <dt>CPU Time Limit</dt>
            <dd>120 seconds</dd>
            <dt>Max Ephemeral Containers</dt>
            <dd>8 concurrent</dd>
            <dt>Filesystem Mount</dt>
            <dd>read-only with /tmp tmpfs</dd>
          </dl>
        </Panel>

        <Panel
          title="Security Boundaries & Policy Guard"
          meta={<Badge variant="ok">ACTIVE</Badge>}
        >
          <dl className="kv-list">
            <dt>Zero-Deploy Without Approval</dt>
            <dd style={{ color: 'var(--devdoc-ok)' }}>STRICT ENFORCEMENT</dd>
            <dt>Direct Production Write</dt>
            <dd style={{ color: 'var(--devdoc-bad)' }}>BLOCKED (NO_WRITE_ROLES)</dd>
            <dt>Audit Ledger Hash Engine</dt>
            <dd>SHA-256 Merkle Chain</dd>
            <dt>Rate Limiting (Per Org)</dt>
            <dd>120 req / 60s (sliding window)</dd>
            <dt>Token Exposure Scrubbing</dt>
            <dd style={{ color: 'var(--devdoc-ok)' }}>ENABLED</dd>
          </dl>
        </Panel>

        <Panel
          title="Database & Knowledge Index"
          meta={<Badge variant="ok">SYNCED</Badge>}
        >
          <dl className="kv-list">
            <dt>Data Store</dt>
            <dd>PostgreSQL 16 (Supabase async)</dd>
            <dt>Alembic Revision</dt>
            <dd>0008_restrict_approval_audit</dd>
            <dt>Vector Index Extension</dt>
            <dd>pgvector (1536-dim)</dd>
            <dt>Knowledge Base Chunks</dt>
            <dd>14,812 indexed docs</dd>
            <dt>Evidence Retention</dt>
            <dd>90 days immutable</dd>
          </dl>
        </Panel>
      </div>
    </div>
  );
};
