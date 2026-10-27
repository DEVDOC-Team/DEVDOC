import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listIncidents,
  getIncident,
  createIncident,
  transitionIncidentStatus,
} from '../incidents';
import {
  listInvestigations,
  runInvestigation,
  transitionInvestigationStatus,
} from '../investigations';
import {
  listApprovals,
  approveRequest,
  rejectRequest,
  listApprovalAudit,
} from '../approvals';
import { ApiError } from '../client';
import type { IncidentCreate } from '../types';

describe('Phase 3: Operational Dashboard, Incidents, Investigations & Approvals', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('Incidents API', () => {
    const projectId = 'proj-101';
    const incidentId = 'inc-202';

    it('listIncidents fetches with correct query params and pagination', async () => {
      const mockResponse = {
        items: [
          {
            id: 'inc-1',
            project_id: projectId,
            repository_id: null,
            reported_by_id: null,
            title: 'High 5xx error rate',
            description: null,
            severity: 'critical' as const,
            status: 'investigating' as const,
            source: 'alert' as const,
            external_reference: null,
            affected_users: 1420,
            detected_at: '2026-10-25T12:00:00Z',
            resolved_at: null,
            created_at: '2026-10-25T12:00:00Z',
            updated_at: '2026-10-25T12:05:00Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockResponse,
      } as Response);

      const res = await listIncidents(projectId, {
        status: 'investigating',
        severity: 'critical',
        limit: 20,
        offset: 0,
      });

      expect(res.items).toHaveLength(1);
      expect(res.items[0].title).toBe('High 5xx error rate');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/incidents`),
        expect.objectContaining({ method: 'GET' })
      );
      const calledUrl = (globalThis.fetch as any).mock.calls[0][0];
      expect(calledUrl).toContain('status=investigating');
      expect(calledUrl).toContain('severity=critical');
      expect(calledUrl).toContain('limit=20');
      expect(calledUrl).toContain('offset=0');
    });

    it('getIncident returns individual incident record', async () => {
      const mockIncident = {
        id: incidentId,
        project_id: projectId,
        repository_id: null,
        reported_by_id: null,
        title: 'Database connection pool exhaustion',
        description: null,
        severity: 'high' as const,
        status: 'investigating' as const,
        source: 'manual' as const,
        external_reference: null,
        affected_users: 850,
        detected_at: '2026-10-25T13:00:00Z',
        resolved_at: null,
        created_at: '2026-10-25T13:00:00Z',
        updated_at: '2026-10-25T13:10:00Z',
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockIncident,
      } as Response);

      const res = await getIncident(projectId, incidentId);
      expect(res.id).toBe(incidentId);
      expect(res.severity).toBe('high');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/incidents/${incidentId}`),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('createIncident sends correct JSON body to POST /projects/{p}/incidents', async () => {
      const newIncident: IncidentCreate = {
        title: 'Kafka Consumer Lag Spike',
        severity: 'high',
        description: 'Lag exceeding 50,000 offsets on checkout-events',
        affected_users: 250,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ id: 'inc-303', project_id: projectId, ...newIncident }),
      } as Response);

      const res = await createIncident(projectId, newIncident);
      expect(res.id).toBe('inc-303');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/incidents`),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(newIncident),
        })
      );
    });

    it('transitionIncidentStatus calls PATCH /projects/{p}/incidents/{i}/status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ id: incidentId, status: 'resolved' }),
      } as Response);

      const res = await transitionIncidentStatus(projectId, incidentId, { status: 'resolved' });
      expect(res.status).toBe('resolved');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/incidents/${incidentId}/status`),
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ status: 'resolved' }),
        })
      );
    });

    it('handles 403 Forbidden with typed ApiError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Not authorized for this project' }),
      } as Response);

      await expect(getIncident(projectId, 'inc-forbidden')).rejects.toThrow(ApiError);
    });

    it('handles 404 Not Found with typed ApiError', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Incident not found' }),
      } as Response);

      await expect(getIncident(projectId, 'inc-missing')).rejects.toThrow(ApiError);
    });
  });

  describe('Investigations & Orchestration API', () => {
    const projectId = 'proj-101';
    const incidentId = 'inc-202';
    const investigationId = 'inv-505';

    it('listInvestigations fetches investigations for an incident', async () => {
      const mockList = {
        items: [
          {
            id: investigationId,
            project_id: projectId,
            incident_id: incidentId,
            initiated_by_id: null,
            status: 'completed' as const,
            summary: 'Autonomous RCA Pipeline',
            tokens_used: 12000,
            estimated_cost_usd: 0.04,
            error_message: null,
            started_at: '2026-10-25T13:00:00Z',
            completed_at: '2026-10-25T13:05:00Z',
            created_at: '2026-10-25T13:00:00Z',
            updated_at: '2026-10-25T13:05:00Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockList,
      } as Response);

      const res = await listInvestigations(projectId, incidentId);
      expect(res.items).toHaveLength(1);
      expect(res.items[0].id).toBe(investigationId);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/incidents/${incidentId}/investigations`),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('runInvestigation executes POST to the verified run endpoint', async () => {
      const mockRunResult = {
        id: investigationId,
        project_id: projectId,
        incident_id: incidentId,
        initiated_by_id: null,
        status: 'completed' as const,
        summary: 'Investigation completed',
        tokens_used: 12500,
        estimated_cost_usd: 0.05,
        error_message: null,
        started_at: '2026-10-25T13:00:00Z',
        completed_at: '2026-10-25T13:05:00Z',
        created_at: '2026-10-25T13:00:00Z',
        updated_at: '2026-10-25T13:05:00Z',
        evidence_count: 5,
        has_root_cause_analysis: true,
        has_fix_proposal: true,
        approval_artifact_id: 'appr-777',
        approval_status: 'pending',
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockRunResult,
      } as Response);

      const res = await runInvestigation(projectId, incidentId, investigationId);
      expect(res.id).toBe(investigationId);
      expect(res.evidence_count).toBe(5);
      expect(res.has_root_cause_analysis).toBe(true);
      expect(res.has_fix_proposal).toBe(true);
      expect(res.approval_artifact_id).toBe('appr-777');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}/run`
        ),
        expect.objectContaining({ method: 'POST' })
      );
    });

    it('transitionInvestigationStatus patches investigation status', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ id: investigationId, status: 'running' }),
      } as Response);

      const res = await transitionInvestigationStatus(projectId, incidentId, investigationId, { status: 'running' });
      expect(res.status).toBe('running');
    });
  });

  describe('Approvals & Governed Gate API', () => {
    const projectId = 'proj-101';
    const investigationId = 'inv-505';
    const approvalId = 'appr-777';

    it('listApprovals returns pending approvals for an investigation', async () => {
      const mockApprovals = {
        items: [
          {
            id: approvalId,
            fix_proposal_id: 'fp-1',
            verification_id: 'ver-1',
            status: 'pending' as const,
            requested_by_id: 'user-orchestrator',
            approver_id: null,
            decision: null,
            rationale: null,
            requested_at: '2026-10-25T14:00:00Z',
            decided_at: null,
            expires_at: null,
            proposal_fingerprint: 'sha256:7f81c9e2b04a91f3...',
            verification_fingerprint: null,
            review: {
              root_cause: {
                claim: 'HikariCP connection leak in retry loop',
                confidence_score: 0.94,
                causal_chain: [{ step: 1, description: 'Deploy rolled out' }],
                failure_modes: ['pool_exhaustion'],
              },
              proposal: {
                title: 'Wrap connection in try-with-resources',
                explanation: 'Releases handle on failure',
                diff: '+ try (Connection c = pool.getConnection()) {',
                target_files: ['PaymentClient.java'],
              },
              verification: {
                verification_id: 'ver-1',
                investigation_id: investigationId,
                proposal_id: 'fp-1',
                status: 'passed',
                started_at: '2026-10-25T14:01:00Z',
                completed_at: '2026-10-25T14:03:00Z',
                verification_steps: [],
                passed_steps: 482,
                failed_steps: 0,
                risk_findings: [],
                cleanup_status: 'cleaned',
                summary: 'All sandbox tests passed',
              },
            },
          },
        ],
        total: 1,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockApprovals,
      } as Response);

      const res = await listApprovals(projectId, investigationId);
      expect(res.items).toHaveLength(1);
      expect(res.items[0].id).toBe(approvalId);
      expect(res.items[0].review?.proposal?.target_files?.[0]).toBe('PaymentClient.java');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals`),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('approveRequest posts decision rationale with min length compliance', async () => {
      const rationale = 'Verified patch in isolated Docker sandbox; regression suite passed.';

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: approvalId,
          status: 'approved',
          decision: 'approved',
          rationale,
        }),
      } as Response);

      const res = await approveRequest(projectId, investigationId, approvalId, rationale);
      expect(res.status).toBe('approved');
      expect(res.rationale).toBe(rationale);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/approve`
        ),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: rationale }),
        })
      );
    });

    it('rejectRequest posts rejection rationale to backend endpoint', async () => {
      const rejectReason = 'Risk of breaking legacy connection pooling contract.';

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: approvalId,
          status: 'rejected',
          decision: 'rejected',
          rationale: rejectReason,
        }),
      } as Response);

      const res = await rejectRequest(projectId, investigationId, approvalId, rejectReason);
      expect(res.status).toBe('rejected');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/reject`
        ),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: rejectReason }),
        })
      );
    });

    it('listApprovalAudit retrieves cryptographically verified audit records', async () => {
      const mockAuditEvents = {
        items: [
          {
            id: 'aud-1',
            actor_id: 'user-commander',
            action: 'APPROVED',
            details: { signature_hash: 'sha256:7f81c9e2b04a91f3...' },
            created_at: '2026-10-25T14:15:00Z',
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockAuditEvents,
      } as Response);

      const res = await listApprovalAudit(projectId, investigationId);
      expect(res.items).toHaveLength(1);
      expect(res.items[0].details.signature_hash).toContain('sha256:');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(
          `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/audit`
        ),
        expect.objectContaining({ method: 'GET' })
      );
    });
  });

  describe('Cancellation and Signal Propagation', () => {
    it('propagates AbortSignal to cancel in-flight requests', async () => {
      const controller = new AbortController();
      controller.abort();

      globalThis.fetch = vi.fn().mockImplementation((_url, options) => {
        if (options?.signal?.aborted) {
          const err = new Error('The operation was aborted.');
          err.name = 'AbortError';
          return Promise.reject(err);
        }
        return Promise.resolve({
          ok: true,
          status: 200,
          headers: new Headers({ 'content-type': 'application/json' }),
          json: async () => ({ items: [] }),
        });
      });

      await expect(listIncidents('p-1', {}, { signal: controller.signal })).rejects.toThrow();
    });
  });
});
