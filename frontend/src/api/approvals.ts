import { apiClient, type RequestOptions } from './client';
import type {
  ApprovalAuditListResponse,
  ApprovalListResponse,
  ApprovalResponse,
} from './types';

/**
 * List approval requests for an investigation.
 * Endpoint: GET /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals
 */
export async function listApprovals(
  projectId: string,
  investigationId: string,
  params?: { limit?: number; offset?: number },
  options?: RequestOptions
): Promise<ApprovalListResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));

  const qs = query.toString();
  const endpoint = `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals${qs ? `?${qs}` : ''}`;

  return apiClient<ApprovalListResponse>(endpoint, {
    method: 'GET',
    ...options,
  });
}

/**
 * Retrieve a specific approval request.
 * Endpoint: GET /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/{approval_id}
 */
export async function getApproval(
  projectId: string,
  investigationId: string,
  approvalId: string,
  options?: RequestOptions
): Promise<ApprovalResponse> {
  return apiClient<ApprovalResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}`,
    {
      method: 'GET',
      ...options,
    }
  );
}

/**
 * Create an approval request for a fix proposal.
 * Endpoint: POST /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals
 */
export async function createApproval(
  projectId: string,
  investigationId: string,
  proposalId: string,
  options?: RequestOptions
): Promise<ApprovalResponse> {
  return apiClient<ApprovalResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals`,
    {
      method: 'POST',
      body: JSON.stringify({ proposal_id: proposalId }),
      ...options,
    }
  );
}

/**
 * Approve a fix proposal request (requires meaningful reason, min 8 chars).
 * Endpoint: POST /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/{approval_id}/approve
 */
export async function approveRequest(
  projectId: string,
  investigationId: string,
  approvalId: string,
  reason: string,
  options?: RequestOptions
): Promise<ApprovalResponse> {
  return apiClient<ApprovalResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/approve`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
      ...options,
    }
  );
}

/**
 * Reject a fix proposal request (requires meaningful reason, min 8 chars).
 * Endpoint: POST /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/{approval_id}/reject
 */
export async function rejectRequest(
  projectId: string,
  investigationId: string,
  approvalId: string,
  reason: string,
  options?: RequestOptions
): Promise<ApprovalResponse> {
  return apiClient<ApprovalResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/reject`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
      ...options,
    }
  );
}

/**
 * Cancel an approval request.
 * Endpoint: POST /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/{approval_id}/cancel
 */
export async function cancelRequest(
  projectId: string,
  investigationId: string,
  approvalId: string,
  reason: string,
  options?: RequestOptions
): Promise<ApprovalResponse> {
  return apiClient<ApprovalResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/${approvalId}/cancel`,
    {
      method: 'POST',
      body: JSON.stringify({ reason }),
      ...options,
    }
  );
}

/**
 * List cryptographic audit trail for an investigation's approvals.
 * Endpoint: GET /api/v1/projects/{project_id}/investigations/{investigation_id}/approvals/audit
 */
export async function listApprovalAudit(
  projectId: string,
  investigationId: string,
  params?: { limit?: number; offset?: number },
  options?: RequestOptions
): Promise<ApprovalAuditListResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));

  const qs = query.toString();
  return apiClient<ApprovalAuditListResponse>(
    `/api/v1/projects/${projectId}/investigations/${investigationId}/approvals/audit${qs ? `?${qs}` : ''}`,
    {
      method: 'GET',
      ...options,
    }
  );
}
