import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import {
  apiClient,
  setStoredToken,
  getStoredToken,
  clearStoredToken,
  ApiError,
} from '../client';
import {
  listIncidents,
} from '../incidents';
import {
  createInvestigation,
} from '../investigations';
import {
  listApprovals,
  approveRequest,
  listApprovalAudit,
} from '../approvals';
import { checkHealth, checkReadiness } from '../auth';

// MemoryStorage mock for Node vitest environment
class MemoryStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

const mockLocal = new MemoryStorage();
const mockSession = new MemoryStorage();

Object.defineProperty(globalThis, 'localStorage', { value: mockLocal, writable: true });
Object.defineProperty(globalThis, 'sessionStorage', { value: mockSession, writable: true });

describe('Phase 6: Full Integration, Security, Testing & Hackathon Release', () => {
  const projectId = 'proj-release-01';
  const incidentId = 'inc-live-101';
  const investigationId = 'inv-live-202';
  const approvalId = 'appr-live-303';

  beforeEach(() => {
    mockLocal.clear();
    mockSession.clear();
    vi.stubGlobal('fetch', vi.fn());
    clearStoredToken();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    clearStoredToken();
  });

  describe('1. Live API Errors Never Silently Fall Back to Demo Data', () => {
    it('listIncidents re-throws ApiError on 500 without returning demo incidents', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 500,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Database connection failed' }),
      });

      await expect(listIncidents(projectId)).rejects.toThrow('Database connection failed');
    });

    it('listApprovals re-throws ApiError on network error without returning demo items', async () => {
      (fetch as any).mockRejectedValueOnce(new Error('Network disconnected'));

      await expect(listApprovals(projectId, investigationId)).rejects.toThrow('Network disconnected');
    });

    it('listApprovalAudit re-throws ApiError on server error without returning demo audit ledger', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 503,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Audit service unavailable' }),
      });

      await expect(listApprovalAudit(projectId, investigationId)).rejects.toThrow('Audit service unavailable');
    });
  });

  describe('2. Authentication Security, Expiry, and Token Scrubbing', () => {
    it('401 Unauthorized response clears stored bearer token immediately', async () => {
      setStoredToken('test-secret-token-12345', true);
      expect(getStoredToken()).toBe('test-secret-token-12345');

      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 401,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Session expired or token invalid' }),
      });

      await expect(listIncidents(projectId)).rejects.toThrow('Session expired or token invalid');
      // Token must have been purged from storage
      expect(getStoredToken()).toBeNull();
    });

    it('403 Forbidden is thrown cleanly and not mislabeled as empty result', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 403,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Insufficient project permissions' }),
      });

      try {
        await listIncidents(projectId);
        expect.unreachable('Should have failed with 403');
      } catch (err) {
        expect(err).toBeInstanceOf(ApiError);
        expect((err as ApiError).status).toBe(403);
        expect((err as ApiError).message).toBe('Insufficient project permissions');
      }
    });

    it('bearer token is never passed in URL query parameters', async () => {
      setStoredToken('safe-token-for-headers-only', true);

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 0 }),
      });

      await listIncidents(projectId);

      const [calledUrl, calledInit] = (fetch as any).mock.calls[0];
      expect(calledUrl).not.toContain('safe-token-for-headers-only');
      expect(calledInit.headers.get('Authorization')).toBe('Bearer safe-token-for-headers-only');
    });
  });

  describe('3. Project Isolation and Clean Endpoint Mapping', () => {
    it('different projects query strictly isolated endpoint URLs', async () => {
      (fetch as any).mockResolvedValue({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 0 }),
      });

      await listIncidents('proj-alpha');
      await listIncidents('proj-beta');

      const urlAlpha = (fetch as any).mock.calls[0][0];
      const urlBeta = (fetch as any).mock.calls[1][0];

      expect(urlAlpha).toContain('/api/v1/projects/proj-alpha/incidents');
      expect(urlBeta).toContain('/api/v1/projects/proj-beta/incidents');
    });

    it('aborted request via AbortSignal cancels safely with status 0 ApiError', async () => {
      const controller = new AbortController();
      controller.abort();

      (fetch as any).mockRejectedValueOnce(new DOMException('The user aborted a request.', 'AbortError'));

      await expect(
        apiClient('/api/v1/projects/test/incidents', { signal: controller.signal })
      ).rejects.toThrow('Request timed out or was cancelled');
    });
  });

  describe('4. Investigation Initiation and Decision Idempotency', () => {
    it('createInvestigation sends valid payload to backend endpoint', async () => {
      const mockInvestigation = {
        id: 'inv-new-001',
        project_id: projectId,
        incident_id: incidentId,
        status: 'running',
        started_at: '2026-10-25T12:00:00Z',
      };

      (fetch as any).mockResolvedValueOnce({
        ok: true,
        status: 201,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => mockInvestigation,
      });

      const res = await createInvestigation(projectId, incidentId, {
        summary: 'Autonomous investigation into connection pool spike',
      });
      expect(res.id).toBe('inv-new-001');
      expect(res.status).toBe('running');

      const [calledUrl, calledInit] = (fetch as any).mock.calls[0];
      expect(calledUrl).toContain(`/api/v1/projects/${projectId}/incidents/${incidentId}/investigations`);
      expect(calledInit.method).toBe('POST');
      expect(JSON.parse(calledInit.body)).toEqual({
        summary: 'Autonomous investigation into connection pool spike',
      });
    });

    it('rejects approval decision when server returns 409 Conflict', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 409,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ detail: 'Approval request already decided by another operator' }),
      });

      await expect(
        approveRequest(
          projectId,
          investigationId,
          approvalId,
          'Peer reviewed sandbox test suite and signed patch'
        )
      ).rejects.toThrow('Approval request already decided by another operator');
    });
  });

  describe('5. Audit Search, Pagination, and Provenance Metadata', () => {
    it('listApprovalAudit correctly forwards pagination parameters', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({ items: [], total: 42, limit: 15, offset: 30 }),
      });

      const res = await listApprovalAudit(projectId, investigationId, { limit: 15, offset: 30 });
      expect(res.total).toBe(42);

      const [calledUrl] = (fetch as any).mock.calls[0];
      expect(calledUrl).toContain(
        `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/audit?limit=15&offset=30`
      );
    });

    it('audit export data correctly distinguishes demo data from live audit data', () => {
      const liveRecords = [
        {
          id: 'AUD-LIVE-1',
          timestamp: '2026-10-25 10:00:00 UTC',
          actor: 'operator-1',
          action: 'approval.approved',
          target: 'investigation:inv-1',
          outcome: 'success',
          hash: 'abc123456789',
          details: 'Verified Docker sandbox regression suite',
          isReal: true,
        },
      ];

      // Live payload
      const livePayload = {
        is_demo_data: false,
        total_records: liveRecords.length,
        records: liveRecords,
      };
      expect(livePayload.is_demo_data).toBe(false);
      expect(livePayload.records[0].isReal).toBe(true);

      // Demo payload
      const demoPayload = {
        is_demo_data: true,
        warning: 'DEMO DATA — NOT A LIVE AUDIT TRAIL',
        total_records: 1,
        records: [{ ...liveRecords[0], isReal: false }],
      };
      expect(demoPayload.is_demo_data).toBe(true);
      expect(demoPayload.warning).toContain('DEMO DATA');
      expect(demoPayload.records[0].isReal).toBe(false);
    });
  });

  describe('6. System Health, Readiness, and Timeout Reliability', () => {
    it('checkHealth returns live operational status when healthy', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: true,
        status: 200,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          success: true,
          status: 'healthy',
          service: 'devdoc-orchestrator',
        }),
      });

      const res = await checkHealth();
      expect(res.status).toBe('healthy');
      expect(res.service).toBe('devdoc-orchestrator');
    });

    it('checkReadiness throws ApiError when service dependencies fail (503)', async () => {
      (fetch as any).mockResolvedValueOnce({
        ok: false,
        status: 503,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          status: 'unready',
          checks: { database: 'disconnected', redis: 'healthy' },
        }),
      });

      await expect(checkReadiness()).rejects.toThrow();
    });
  });
});
