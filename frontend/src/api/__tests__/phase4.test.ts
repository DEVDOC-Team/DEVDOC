import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  listApprovals,
  getApproval,
  approveRequest,
  rejectRequest,
} from '../approvals';
import { runInvestigation } from '../investigations';
import { listIncidents } from '../incidents';
import { ApiError } from '../client';
import type {
  ApprovalResponse,
  RootCauseAnalysis,
  FixProposal,
  VerificationReview,
} from '../types';

describe('Phase 4: AI Diagnosis, Root-Cause Analysis & Remediation Workspace', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  const projectId = 'proj-phase4';
  const incidentId = 'inc-phase4';
  const investigationId = 'inv-phase4';
  const approvalId = 'appr-phase4';

  describe('RCA Diagnosis Contracts and Epistemic Separation', () => {
    it('returns structured RCA with observed facts, hypothesis claims, and confidence', async () => {
      const mockRCA: RootCauseAnalysis = {
        analysis_id: 'ana-101',
        investigation_id: investigationId,
        execution_id: 'exec-101',
        status: 'root_cause_identified',
        confidence: 'high',
        selected_root_cause: {
          candidate_id: 'cand-1',
          classification: 'hypothesis',
          statement: 'HikariCP connection pool exhausted by inner retry leak in PaymentClient.java',
          category: 'resource_exhaustion',
          confidence: 'high',
          rank: 1,
          supporting_evidence: [
            {
              evidence_id: 'ev-1',
              classification: 'fact',
              source: 'api-gateway',
              evidence_type: 'log',
              timestamp: '2026-10-25T14:02:11Z',
              title: 'HikariCP timeout burst',
              summary: 'Active=200/200 connection acquisition timed out after 30s',
            },
          ],
          contradicting_evidence: [],
          contributing_factors: [
            {
              statement: 'Upstream gateway returned HTTP 429 rate limits triggering client retries',
              evidence_references: [],
            },
          ],
          triggering_events: [],
          observed_symptoms: [],
          uncertainty: 'None observed on replica pods',
          rationale: 'Connection handle never released before subsequent attempt in loop',
          ranking_basis: 'Direct correlation with deploy timestamp and error logs',
        },
        candidates: [],
        observed_facts: [
          {
            evidence_id: 'ev-1',
            classification: 'fact',
            source: 'api-gateway',
            evidence_type: 'log',
            timestamp: '2026-10-25T14:02:11Z',
            title: 'HikariCP timeout burst',
            summary: 'Active=200/200 connection acquisition timed out after 30s',
          },
        ],
        reasoning_summary: 'Deployment v2.14.0 introduced unreleased connections under transient errors.',
        uncertainties: [],
        missing_information: [],
        analyzed_at: '2026-10-25T14:15:00Z',
      };

      const mockProposal: FixProposal = {
        proposal_id: 'fp-101',
        investigation_id: investigationId,
        root_cause_reference: 'cand-1',
        status: 'proposed',
        summary: 'Wrap connection in try-with-resources block',
        rationale: 'Ensures deterministic handle release upon exception or loop exit',
        affected_components: ['payments-service'],
        change_type: 'code_change',
        changes: [
          {
            target: 'PaymentClient.java',
            target_path: 'services/payment/PaymentClient.java',
            operation: 'modify',
            proposed_diff: '--- a/PaymentClient.java\n+++ b/PaymentClient.java\n@@ -10 +10 @@\n- Connection c = pool.getConnection();\n+ try (Connection c = pool.getConnection()) {',
            patch_status: 'PROPOSED / UNVERIFIED',
            reason: 'Fix handle leak',
            tests_required: ['PaymentClientTest'],
          },
        ],
        risks: [
          {
            category: 'regression',
            severity: 'low',
            description: 'Timeout behavior may change under extreme load',
            mitigation: 'Verified against 482 sandbox regression tests',
          },
        ],
        rollback_plan: [
          {
            description: 'git revert commit',
            trigger: 'Error rate persists > 1%',
            expected_result: 'Pool returns to baseline 74 connections',
          },
        ],
        human_approval_required: true,
      };

      const mockVerification: VerificationReview = {
        verification_id: 'ver-101',
        investigation_id: investigationId,
        proposal_id: 'fp-101',
        status: 'passed',
        started_at: '2026-10-25T14:16:00Z',
        completed_at: '2026-10-25T14:18:00Z',
        verification_steps: [
          {
            step_id: 'step-1',
            description: 'Run unit test suite in isolated Docker container',
            status: 'passed',
            exit_code: 0,
            duration_ms: 1045,
            expected_result: 'All unit tests pass',
            observed_result: '482 passed, 0 failed',
          },
        ],
        passed_steps: 482,
        failed_steps: 0,
        risk_findings: [],
        cleanup_status: 'cleaned',
        summary: 'Sandbox execution passed all tests',
      };

      const mockApproval: ApprovalResponse = {
        id: approvalId,
        fix_proposal_id: 'fp-101',
        verification_id: 'ver-101',
        status: 'pending',
        requested_by_id: 'user-orch',
        approver_id: null,
        decision: null,
        rationale: null,
        requested_at: '2026-10-25T14:19:00Z',
        decided_at: null,
        expires_at: null,
        proposal_fingerprint: 'sha256:7f81c9e2b04a91f3...',
        verification_fingerprint: 'sha256:3a91b8e2...',
        review: {
          root_cause: mockRCA,
          proposal: mockProposal,
          verification: mockVerification,
        },
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [mockApproval], total: 1 }),
      } as Response);

      const res = await listApprovals(projectId, investigationId);
      expect(res.items).toHaveLength(1);
      const app = res.items[0];

      // Verify RCA data
      expect(app.review?.root_cause.confidence).toBe('high');
      expect(app.review?.root_cause.status).toBe('root_cause_identified');
      expect(app.review?.root_cause.selected_root_cause?.category).toBe('resource_exhaustion');

      // Verify Epistemic evidence classification
      const factEvidence = app.review?.root_cause.observed_facts?.[0];
      expect(factEvidence?.classification).toBe('fact');
      expect(factEvidence?.source).toBe('api-gateway');

      // Verify Proposal and risk matrix
      expect(app.review?.proposal.changes?.[0].proposed_diff).toContain('--- a/PaymentClient.java');
      expect(app.review?.proposal.risks?.[0].severity).toBe('low');
      expect(app.review?.proposal.rollback_plan?.[0].trigger).toContain('Error rate persists');

      // Verify Sandbox Verification review
      expect(app.review?.verification.status).toBe('passed');
      expect(app.review?.verification.passed_steps).toBe(482);
      expect(app.review?.verification.verification_steps[0].exit_code).toBe(0);
    });

    it('correctly handles investigation with missing RCA or missing fix proposal', async () => {
      const mockEmptyApproval: ApprovalResponse = {
        id: 'appr-empty',
        fix_proposal_id: 'fp-none',
        verification_id: null,
        status: 'pending',
        requested_by_id: 'user-orch',
        approver_id: null,
        decision: null,
        rationale: null,
        requested_at: '2026-10-25T14:19:00Z',
        decided_at: null,
        expires_at: null,
        proposal_fingerprint: null,
        verification_fingerprint: null,
        review: null,
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockEmptyApproval,
      } as Response);

      const res = await getApproval(projectId, investigationId, 'appr-empty');
      expect(res.review).toBeNull();
      expect(res.verification_id).toBeNull();
    });
  });

  describe('Governed Approval and Rejection Boundary', () => {
    it('records approval with rationale and enforces minimum length', async () => {
      const validRationale = 'Verified sandbox tests pass; no resource leaks identified.';

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: approvalId,
          status: 'approved',
          decision: 'approved',
          rationale: validRationale,
        }),
      } as Response);

      const res = await approveRequest(projectId, investigationId, approvalId, validRationale);
      expect(res.status).toBe('approved');
      expect(res.decision).toBe('approved');
      expect(res.rationale).toBe(validRationale);
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/approvals/${approvalId}/approve`),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ reason: validRationale }),
        })
      );
    });

    it('rejects approval when rationale is missing or server returns 422', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: 'Decision reason must contain at least 8 non-whitespace characters',
        }),
      } as Response);

      await expect(
        approveRequest(projectId, investigationId, approvalId, 'too short')
      ).rejects.toThrow(ApiError);
    });

    it('records rejection with rationale', async () => {
      const rejectRationale = 'Candidate patch modifies legacy retry semantics unfavorably.';

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          id: approvalId,
          status: 'rejected',
          decision: 'rejected',
          rationale: rejectRationale,
        }),
      } as Response);

      const res = await rejectRequest(projectId, investigationId, approvalId, rejectRationale);
      expect(res.status).toBe('rejected');
      expect(res.decision).toBe('rejected');
      expect(res.rationale).toBe(rejectRationale);
    });
  });

  describe('Investigation Orchestration Lifecycle', () => {
    it('executes run endpoint returning evidence count and approval artifact id', async () => {
      const mockRunResponse = {
        id: investigationId,
        project_id: projectId,
        incident_id: incidentId,
        initiated_by_id: null,
        status: 'completed' as const,
        summary: 'Investigation completed with root cause identified',
        tokens_used: 12400,
        estimated_cost_usd: 0.0496,
        error_message: null,
        started_at: '2026-10-25T14:11:32Z',
        completed_at: '2026-10-25T14:24:07Z',
        created_at: '2026-10-25T14:11:32Z',
        updated_at: '2026-10-25T14:24:07Z',
        evidence_count: 5,
        has_root_cause_analysis: true,
        has_fix_proposal: true,
        approval_artifact_id: 'appr-101',
        approval_status: 'pending',
      };

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockRunResponse,
      } as Response);

      const res = await runInvestigation(projectId, incidentId, investigationId);
      expect(res.evidence_count).toBe(5);
      expect(res.has_root_cause_analysis).toBe(true);
      expect(res.has_fix_proposal).toBe(true);
      expect(res.approval_artifact_id).toBe('appr-101');
      expect(res.approval_status).toBe('pending');
    });

    it('handles 409 conflict when investigation is already running', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          detail: `Investigation '${investigationId}' is already running`,
        }),
      } as Response);

      await expect(
        runInvestigation(projectId, incidentId, investigationId)
      ).rejects.toThrow(ApiError);
    });
  });

  describe('Project Context Isolation and Cancellation', () => {
    it('cancels pending requests when AbortSignal fires upon project switch', async () => {
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

      await expect(
        listIncidents('proj-other', {}, { signal: controller.signal })
      ).rejects.toThrow();
    });
  });
});
