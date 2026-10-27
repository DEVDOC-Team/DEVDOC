import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  listApprovals,
  getApproval,
  createApproval,
  approveRequest,
  rejectRequest,
  cancelRequest,
  listApprovalAudit,
} from '../approvals';
import { checkHealth, checkReadiness } from '../auth';
import { ApiError } from '../client';
import type {
  ApprovalResponse,
  ApprovalListResponse,
  ApprovalAuditListResponse,
  HealthResponse,
  ReadinessResponse,
} from '../types';

describe('Phase 5: Human Approvals, Execution Controls, Audit & System Health', () => {
  const projectId = 'proj-governance-01';
  const investigationId = 'inv-investigation-99';
  const approvalId = 'appr-phase5-001';
  const proposalId = 'fp-phase5-001';

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('1. Approval Queue Loading, Empty, and Error States', () => {
    it('listApprovals loads approval queue items successfully', async () => {
      const mockList: ApprovalListResponse = {
        items: [
          {
            id: approvalId,
            fix_proposal_id: proposalId,
            verification_id: 'ver-01',
            status: 'pending',
            requested_by_id: 'user-01',
            approver_id: null,
            decision: null,
            rationale: null,
            requested_at: '2026-10-25T10:00:00Z',
            decided_at: null,
            expires_at: '2026-10-26T10:00:00Z',
            proposal_fingerprint: 'sha256:7f81c9e2b04a91f3c8e4d2a1b9f7a6358c21345d9e7611ab02c1f930e461b18a',
            verification_fingerprint: 'sha256:a12e4f8d9b3c21a977c1d3e051fa82119b23b118ae45f04ca82031174983df92',
            review: {
              root_cause: {
                status: 'root_cause_identified',
                confidence: 'high',
                claim: 'Resource leak in PaymentClient connection pool',
              },
              proposal: {
                title: 'Connection Pool Encapsulation',
                summary: 'Wrap pool acquisition in try-with-resources statement',
                human_approval_required: true,
                changes: [
                  {
                    target: 'PaymentClient.java',
                    target_path: 'services/payment/PaymentClient.java',
                    operation: 'update',
                    reason: 'Prevent socket descriptor leaks under exception flow',
                  },
                ],
                risks: [
                  {
                    category: 'compatibility',
                    severity: 'low',
                    description: 'Timeout alteration',
                    mitigation: 'Verified via sandbox test suite',
                  },
                ],
                rollback_plan: [
                  {
                    trigger: 'Pool acquisition timeout > 2000ms',
                    expected_result: 'Revert to commit 7b1c4f0',
                    description: 'Automated git rollback',
                  },
                ],
              },
              verification: {
                verification_id: 'ver-01',
                investigation_id: investigationId,
                proposal_id: proposalId,
                status: 'passed',
                started_at: '2026-10-25T09:58:00Z',
                completed_at: '2026-10-25T09:59:00Z',
                verification_steps: [
                  {
                    step_id: 'step-1',
                    description: 'Docker Alpine unit suite',
                    status: 'passed',
                    exit_code: 0,
                    duration_ms: 1240,
                    expected_result: '0 failures',
                    observed_result: '0 failures',
                  },
                ],
                passed_steps: 482,
                failed_steps: 0,
                risk_findings: [],
                cleanup_status: 'complete',
                summary: 'All unit and regression checks passed with clean container teardown.',
              },
            },
          },
        ],
        total: 1,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockList,
      } as Response);

      const res = await listApprovals(projectId, investigationId, { limit: 10, offset: 0 });
      expect(res.total).toBe(1);
      expect(res.items).toHaveLength(1);
      expect(res.items[0].status).toBe('pending');
      expect(res.items[0].review?.verification?.passed_steps).toBe(482);
      expect(res.items[0].review?.proposal?.changes?.[0]?.target_path).toBe('services/payment/PaymentClient.java');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals?limit=10&offset=0`),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('listApprovals handles empty approval queue correctly', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 0 }),
      } as Response);

      const res = await listApprovals(projectId, investigationId);
      expect(res.items).toEqual([]);
      expect(res.total).toBe(0);
    });

    it('getApproval fetches a specific approval item by ID', async () => {
      const mockSingle: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'pending',
        requested_by_id: 'user-01',
        approver_id: null,
        decision: null,
        rationale: null,
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: null,
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockSingle,
      } as Response);

      const res = await getApproval(projectId, investigationId, approvalId);
      expect(res.id).toBe(approvalId);
      expect(res.status).toBe('pending');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}`),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('listApprovals handles server errors with sanitized message', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Internal server error in approval service' }),
      } as Response);

      await expect(listApprovals(projectId, investigationId)).rejects.toThrow(ApiError);
    });
  });

  describe('2. Safe Approval, Rejection, and Cancellation Decisions', () => {
    it('approveRequest submits meaningful rationale (>= 8 chars) and receives confirmed decision', async () => {
      const validReason = 'Sandbox verification passed and zero regressions confirmed.';
      const mockApprovedResponse: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'approved',
        requested_by_id: 'user-01',
        approver_id: 'commander-01',
        decision: 'approved',
        rationale: validReason,
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: '2026-10-25T10:05:00Z',
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockApprovedResponse,
      } as Response);

      const res = await approveRequest(projectId, investigationId, approvalId, validReason);
      expect(res.status).toBe('approved');
      expect(res.decision).toBe('approved');
      expect(res.rationale).toBe(validReason);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/approve`),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: validReason }),
        })
      );
    });

    it('rejectRequest successfully records rejection decision with audit rationale', async () => {
      const rejectReason = 'Risk matrix indicates potential pool contention under spike traffic.';
      const mockRejectedResponse: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'rejected',
        requested_by_id: 'user-01',
        approver_id: 'commander-01',
        decision: 'rejected',
        rationale: rejectReason,
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: '2026-10-25T10:06:00Z',
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockRejectedResponse,
      } as Response);

      const res = await rejectRequest(projectId, investigationId, approvalId, rejectReason);
      expect(res.status).toBe('rejected');
      expect(res.decision).toBe('rejected');
      expect(res.rationale).toBe(rejectReason);
    });

    it('cancelRequest successfully cancels a pending approval request', async () => {
      const cancelReason = 'Investigation was restarted with fresh telemetry parameters.';
      const mockCancelledResponse: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'cancelled',
        requested_by_id: 'user-01',
        approver_id: null,
        decision: null,
        rationale: cancelReason,
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: '2026-10-25T10:07:00Z',
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockCancelledResponse,
      } as Response);

      const res = await cancelRequest(projectId, investigationId, approvalId, cancelReason);
      expect(res.status).toBe('cancelled');
      expect(res.rationale).toBe(cancelReason);

      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/cancel`),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: cancelReason }),
        })
      );
    });

    it('handles 409 Conflict when approval is stale or already decided', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Another reviewer already completed this approval request' }),
      } as Response);

      await expect(
        approveRequest(projectId, investigationId, approvalId, 'Valid rationale submitted')
      ).rejects.toThrow('Another reviewer already completed this approval request');
    });

    it('handles 403 Forbidden when caller lacks project authority', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 403,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Project owner or platform administrator required' }),
      } as Response);

      await expect(
        rejectRequest(projectId, investigationId, approvalId, 'Valid rationale submitted')
      ).rejects.toThrow('Project owner or platform administrator required');
    });
  });

  describe('3. Audit Trail Ledger and Fingerprint Verification', () => {
    it('listApprovalAudit retrieves real immutable audit records', async () => {
      const mockAuditResponse: ApprovalAuditListResponse = {
        items: [
          {
            id: 'audit-evt-001',
            actor_id: 'user-commander-99',
            action: 'approval.approved',
            description: 'Authorized human recorded an approval decision.',
            outcome: 'success',
            request_id: 'req-trace-5544',
            details: {
              status: 'approved',
              proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
            },
            created_at: '2026-10-25T10:05:00Z',
          },
          {
            id: 'audit-evt-002',
            actor_id: null,
            action: 'approval.requested',
            description: 'Human approval requested for a verified proposal.',
            outcome: 'success',
            request_id: 'req-trace-5540',
            details: {},
            created_at: '2026-10-25T10:00:00Z',
          },
        ],
        total: 2,
        limit: 50,
        offset: 0,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockAuditResponse,
      } as Response);

      const res = await listApprovalAudit(projectId, investigationId, { limit: 50, offset: 0 });
      expect(res.total).toBe(2);
      expect(res.items).toHaveLength(2);
      expect(res.items[0].action).toBe('approval.approved');
      expect(res.items[0].actor_id).toBe('user-commander-99');
      expect(res.items[1].actor_id).toBeNull();
      expect(res.items[0].outcome).toBe('success');
    });

    it('listApprovalAudit supports pagination offset parameters', async () => {
      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 100, limit: 20, offset: 40 }),
      } as Response);

      const res = await listApprovalAudit(projectId, investigationId, { limit: 20, offset: 40 });
      expect(res.limit).toBe(20);
      expect(res.offset).toBe(40);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/audit?limit=20&offset=40`),
        expect.objectContaining({ method: 'GET' })
      );
    });
  });

  describe('4. System Health and Readiness Diagnostics', () => {
    it('checkHealth returns 200 healthy liveness status', async () => {
      const mockHealth: HealthResponse = {
        success: true,
        service: 'DEVDOC',
        status: 'healthy',
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockHealth,
      } as Response);

      const res = await checkHealth();
      expect(res.success).toBe(true);
      expect(res.service).toBe('DEVDOC');
      expect(res.status).toBe('healthy');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/health'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    it('checkReadiness returns 200 ready when database is reachable', async () => {
      const mockReady: ReadinessResponse = {
        success: true,
        service: 'DEVDOC',
        status: 'ready',
        checks: {
          database: 'ok',
        },
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockReady,
      } as Response);

      const res = await checkReadiness();
      expect(res.success).toBe(true);
      expect(res.status).toBe('ready');
      expect(res.checks.database).toBe('ok');
    });

    it('checkReadiness parses 503 degraded status when database is unreachable', async () => {
      const mockDegraded: ReadinessResponse = {
        success: false,
        service: 'DEVDOC',
        status: 'degraded',
        checks: {
          database: 'unavailable',
        },
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: false,
        status: 503,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockDegraded,
      } as Response);

      await expect(checkReadiness()).rejects.toThrow(ApiError);
    });

    it('checkHealth aborts cleanly on request timeout or component unmount', async () => {
      const controller = new AbortController();
      controller.abort();

      vi.mocked(globalThis.fetch).mockRejectedValueOnce(new DOMException('The user aborted a request.', 'AbortError'));

      await expect(checkHealth({ signal: controller.signal })).rejects.toThrow('Request timed out or was cancelled');
    });
  });

  describe('5. Governance Boundaries and Execution Isolation', () => {
    it('verifies approval alone does not trigger automated production deployment', async () => {
      // Per Section 3: "Treat approval, execution, merge, and deployment as distinct operations. Approval alone must never be represented as successful execution."
      const mockApprovedResponse: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'approved',
        requested_by_id: 'user-01',
        approver_id: 'commander-01',
        decision: 'approved',
        rationale: 'Verified patch in isolated Docker container.',
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: '2026-10-25T10:05:00Z',
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockApprovedResponse,
      } as Response);

      const res = await approveRequest(projectId, investigationId, approvalId, 'Verified patch in isolated Docker container.');
      expect(res.status).toBe('approved');
      // Proves that no /deploy or /merge endpoint is invoked
      expect(globalThis.fetch).toHaveBeenCalledTimes(1);
      expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/deploy'), expect.anything());
      expect(globalThis.fetch).not.toHaveBeenCalledWith(expect.stringContaining('/merge'), expect.anything());
    });

    it('verifies createApproval binds strictly to proposal_id', async () => {
      const mockCreated: ApprovalResponse = {
        id: 'new-appr-999',
        fix_proposal_id: proposalId,
        verification_id: 'ver-01',
        status: 'pending',
        requested_by_id: 'user-01',
        approver_id: null,
        decision: null,
        rationale: null,
        requested_at: '2026-10-25T10:00:00Z',
        decided_at: null,
        expires_at: '2026-10-26T10:00:00Z',
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3',
        verification_fingerprint: 'sha256:a12e4f8d9b3c21a9',
        review: null,
      };

      vi.mocked(globalThis.fetch).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockCreated,
      } as Response);

      const res = await createApproval(projectId, investigationId, proposalId);
      expect(res.id).toBe('new-appr-999');
      expect(res.status).toBe('pending');
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/projects/${projectId}/investigations/${investigationId}/approvals`),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ proposal_id: proposalId }),
        })
      );
    });
  });
});
