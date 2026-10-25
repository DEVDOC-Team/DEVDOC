import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import {
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
  Server,
  Lock,
  ShieldCheck,
} from 'lucide-react';
import { checkHealth, checkReadiness } from '../api/auth';
import type { HealthResponse, ReadinessResponse } from '../api/types';
import './views.css';

interface ProbeResult<T> {
  data: T | null;
  status: 'healthy' | 'degraded' | 'unavailable' | 'loading' | 'idle';
  latencyMs: number | null;
  timestamp: string | null;
  error: string | null;
}

export const SettingsView: React.FC = () => {
  const [healthProbe, setHealthProbe] = useState<ProbeResult<HealthResponse>>({
    data: null,
    status: 'idle',
    latencyMs: null,
    timestamp: null,
    error: null,
  });

  const [readinessProbe, setReadinessProbe] = useState<ProbeResult<ReadinessResponse>>({
    data: null,
    status: 'idle',
    latencyMs: null,
    timestamp: null,
    error: null,
  });

  const [isProbing, setIsProbing] = useState<boolean>(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const runProbes = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsProbing(true);
    setHealthProbe((prev) => ({ ...prev, status: 'loading', error: null }));
    setReadinessProbe((prev) => ({ ...prev, status: 'loading', error: null }));

    // Probe 1: GET /api/v1/health (Liveness)
    const t0Health = performance.now();
    try {
      const healthData = await checkHealth({ signal: controller.signal });
      const elapsedHealth = Math.round(performance.now() - t0Health);
      setHealthProbe({
        data: healthData,
        status: healthData.status === 'healthy' ? 'healthy' : 'unavailable',
        latencyMs: elapsedHealth,
        timestamp: new Date().toLocaleTimeString(),
        error: null,
      });
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      const elapsedHealth = Math.round(performance.now() - t0Health);
      const msg = err instanceof Error ? err.message : 'Liveness probe failed';
      setHealthProbe({
        data: null,
        status: 'unavailable',
        latencyMs: elapsedHealth,
        timestamp: new Date().toLocaleTimeString(),
        error: msg.split('\n')[0],
      });
    }

    // Probe 2: GET /api/v1/ready (Readiness & Dependencies)
    const t0Ready = performance.now();
    try {
      const readyData = await checkReadiness({ signal: controller.signal });
      const elapsedReady = Math.round(performance.now() - t0Ready);
      setReadinessProbe({
        data: readyData,
        status: readyData.status === 'ready' ? 'healthy' : readyData.status === 'degraded' ? 'degraded' : 'unavailable',
        latencyMs: elapsedReady,
        timestamp: new Date().toLocaleTimeString(),
        error: null,
      });
    } catch (err: unknown) {
      if ((err as Error).name === 'AbortError') return;
      const elapsedReady = Math.round(performance.now() - t0Ready);
      const msg = err instanceof Error ? err.message : 'Readiness probe failed';
      setReadinessProbe({
        data: null,
        status: 'unavailable',
        latencyMs: elapsedReady,
        timestamp: new Date().toLocaleTimeString(),
        error: msg.split('\n')[0],
      });
    } finally {
      setIsProbing(false);
    }
  }, []);

  useEffect(() => {
    runProbes();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [runProbes]);

  return (
    <div className="view-container">
      {/* Banner */}
      <div className="incident-header-banner">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
              System Health & Readiness Diagnostics
            </h2>
            <Badge variant="neutral">Phase 18 Liveness & Readiness</Badge>
          </div>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Authoritative runtime probes, dependency health checks, container isolation parameters, and governance boundaries.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={runProbes}
            disabled={isProbing}
            icon={<RefreshCw size={13} className={isProbing ? 'spin-slow' : ''} />}
          >
            {isProbing ? 'Probing System...' : 'Re-probe Endpoints'}
          </Button>
        </div>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '14px', marginTop: '14px' }}>
        {/* Card 1: Application Process Liveness */}
        <Panel
          title={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Activity size={16} color="var(--devdoc-accent)" />
              <span>Application Process Liveness</span>
            </div>
          }
          meta={
            healthProbe.status === 'healthy' ? (
              <Badge variant="ok">HEALTHY (200 OK)</Badge>
            ) : healthProbe.status === 'loading' ? (
              <Badge variant="neutral">PROBING...</Badge>
            ) : (
              <Badge variant="sev1">UNAVAILABLE</Badge>
            )
          }
        >
          <div style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginBottom: '12px', lineHeight: 1.4 }}>
            Verifies the DEVDOC FastAPI application process is alive and receiving HTTP traffic. Does not depend on external services.
          </div>

          <dl className="kv-list">
            <dt>Probe Endpoint</dt>
            <dd style={{ fontFamily: 'var(--font-mono)' }}>GET /api/v1/health</dd>

            <dt>Runtime Service</dt>
            <dd>{healthProbe.data?.service || 'DEVDOC (FastAPI)'}</dd>

            <dt>Liveness Status</dt>
            <dd
              style={{
                color:
                  healthProbe.status === 'healthy'
                    ? 'var(--devdoc-status-ok)'
                    : 'var(--devdoc-status-bad)',
                fontWeight: 600,
              }}
            >
              {healthProbe.data?.status?.toUpperCase() || (healthProbe.error ? 'OFFLINE' : 'CHECKING')}
            </dd>

            <dt>Round-Trip Latency</dt>
            <dd style={{ fontFamily: 'var(--font-mono)' }}>
              {healthProbe.latencyMs !== null ? `${healthProbe.latencyMs} ms` : '—'}
            </dd>

            <dt>Last Checked</dt>
            <dd style={{ fontFamily: 'var(--font-mono)' }}>
              {healthProbe.timestamp || 'Initial probe in progress...'}
            </dd>

            <dt>Probe Protocol</dt>
            <dd>HTTP/1.1 (JSON unauthenticated)</dd>
          </dl>

          {healthProbe.error && (
            <div
              style={{
                marginTop: '12px',
                padding: '8px 10px',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid var(--devdoc-status-bad)',
                borderRadius: 'var(--radius-xs)',
                color: 'var(--devdoc-fg)',
                fontSize: '11px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <XCircle size={14} color="var(--devdoc-status-bad)" />
              <span>{healthProbe.error}</span>
            </div>
          )}
        </Panel>

        {/* Card 2: Dependency Readiness Probe */}
        <Panel
          title={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Server size={16} color="var(--devdoc-status-ok)" />
              <span>Dependency Readiness Probe</span>
            </div>
          }
          meta={
            readinessProbe.status === 'healthy' ? (
              <Badge variant="ok">READY (200 OK)</Badge>
            ) : readinessProbe.status === 'degraded' ? (
              <Badge variant="warn">DEGRADED (503)</Badge>
            ) : readinessProbe.status === 'loading' ? (
              <Badge variant="neutral">PROBING...</Badge>
            ) : (
              <Badge variant="sev1">UNAVAILABLE</Badge>
            )
          }
        >
          <div style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginBottom: '12px', lineHeight: 1.4 }}>
            Actively verifies connectivity to required infrastructure dependencies. Load balancers use this probe for traffic routing.
          </div>

          <dl className="kv-list">
            <dt>Probe Endpoint</dt>
            <dd style={{ fontFamily: 'var(--font-mono)' }}>GET /api/v1/ready</dd>

            <dt>Readiness State</dt>
            <dd
              style={{
                color:
                  readinessProbe.status === 'healthy'
                    ? 'var(--devdoc-status-ok)'
                    : readinessProbe.status === 'degraded'
                    ? 'var(--devdoc-accent-amber)'
                    : 'var(--devdoc-status-bad)',
                fontWeight: 600,
              }}
            >
              {readinessProbe.data?.status?.toUpperCase() || (readinessProbe.error ? 'OFFLINE' : 'CHECKING')}
            </dd>

            <dt>Database Connectivity</dt>
            <dd style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              {readinessProbe.data?.checks?.database === 'ok' ? (
                <>
                  <CheckCircle2 size={13} color="var(--devdoc-status-ok)" />
                  <span style={{ color: 'var(--devdoc-status-ok)', fontWeight: 600 }}>REACHABLE (SELECT 1)</span>
                </>
              ) : (
                <>
                  <AlertTriangle size={13} color="var(--devdoc-status-bad)" />
                  <span style={{ color: 'var(--devdoc-status-bad)', fontWeight: 600 }}>
                    {readinessProbe.data?.checks?.database || 'UNAVAILABLE'}
                  </span>
                </>
              )}
            </dd>

            <dt>Round-Trip Latency</dt>
            <dd style={{ fontFamily: 'var(--font-mono)' }}>
              {readinessProbe.latencyMs !== null ? `${readinessProbe.latencyMs} ms` : '—'}
            </dd>

            <dt>Data Layer</dt>
            <dd>PostgreSQL 16 (Async SQLAlchemy)</dd>

            <dt>Readiness Protocol</dt>
            <dd>HTTP/1.1 (503 on dependency failure)</dd>
          </dl>

          {readinessProbe.error && (
            <div
              style={{
                marginTop: '12px',
                padding: '8px 10px',
                background: 'rgba(239, 68, 68, 0.1)',
                border: '1px solid var(--devdoc-status-bad)',
                borderRadius: 'var(--radius-xs)',
                color: 'var(--devdoc-fg)',
                fontSize: '11px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <XCircle size={14} color="var(--devdoc-status-bad)" />
              <span>{readinessProbe.error}</span>
            </div>
          )}
        </Panel>

        {/* Card 3: Security & Governance Boundaries */}
        <Panel
          title={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Lock size={16} color="var(--devdoc-accent-amber)" />
              <span>Governance & Execution Boundary</span>
            </div>
          }
          meta={<Badge variant="ok">POLICY ENFORCED</Badge>}
        >
          <dl className="kv-list">
            <dt>Direct Production Write</dt>
            <dd style={{ color: 'var(--devdoc-status-bad)', fontWeight: 600 }}>BLOCKED (NO_WRITE_ROLES)</dd>

            <dt>Production Deployment</dt>
            <dd style={{ color: 'var(--devdoc-status-bad)', fontWeight: 600 }}>DISABLED (Human CI/CD Required)</dd>

            <dt>Human Sign-Off Gate</dt>
            <dd style={{ color: 'var(--devdoc-status-ok)', fontWeight: 600 }}>MANDATORY (Phase 18)</dd>

            <dt>Decision Rationale Rule</dt>
            <dd>Min 8 non-whitespace characters</dd>

            <dt>Digest Verification</dt>
            <dd>SHA-256 canonical JSON match</dd>

            <dt>Audit Trail Storage</dt>
            <dd style={{ color: 'var(--devdoc-status-ok)' }}>Append-only public.audit_logs</dd>

            <dt>Terminal Decisions</dt>
            <dd>Immutable (No decision replaying)</dd>
          </dl>
        </Panel>

        {/* Card 4: Container Sandbox Isolation */}
        <Panel
          title={
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShieldCheck size={16} color="var(--devdoc-status-ok)" />
              <span>Sandbox Isolation Safeguards</span>
            </div>
          }
          meta={<Badge variant="ok">ISOLATED</Badge>}
        >
          <dl className="kv-list">
            <dt>Execution Sandbox</dt>
            <dd>Docker Engine (rootless)</dd>

            <dt>Network Isolation</dt>
            <dd style={{ color: 'var(--devdoc-status-ok)' }}>--network none (Air-gapped)</dd>

            <dt>Max Container Memory</dt>
            <dd>2048 MB</dd>

            <dt>Execution Timeout</dt>
            <dd>120 seconds per run</dd>

            <dt>Filesystem Mounting</dt>
            <dd>Read-only with ephemeral /tmp</dd>

            <dt>Artifact Cleanup</dt>
            <dd style={{ color: 'var(--devdoc-status-ok)' }}>Guaranteed teardown on exit</dd>

            <dt>Patch Dry-Run</dt>
            <dd>Pre-flight verification required</dd>
          </dl>
        </Panel>
      </div>
    </div>
  );
};
