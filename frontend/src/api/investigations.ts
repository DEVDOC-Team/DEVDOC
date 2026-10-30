import { apiClient, type RequestOptions } from './client';
import type {
  Investigation,
  InvestigationCreate,
  InvestigationDeleteResponse,
  InvestigationListResponse,
  InvestigationRunResponse,
  InvestigationStatus,
  InvestigationStatusUpdate,
  InvestigationUpdate,
} from './types';

export interface ListInvestigationsParams {
  limit?: number;
  offset?: number;
  status?: InvestigationStatus;
}

export interface InvestigationCancelResponse {
  success: boolean;
  status: InvestigationStatus;
  cancellation_requested: boolean;
  message: string;
}

/**
 * List investigations for a verified incident.
 * Endpoint: GET /api/v1/projects/{project_id}/incidents/{incident_id}/investigations
 */
export async function listInvestigations(
  projectId: string,
  incidentId: string,
  params?: ListInvestigationsParams,
  options?: RequestOptions
): Promise<InvestigationListResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  if (params?.status) query.set('status', params.status);

  const qs = query.toString();
  const endpoint = `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations${qs ? `?${qs}` : ''}`;

  return apiClient<InvestigationListResponse>(endpoint, {
    method: 'GET',
    ...options,
  });
}

/**
 * Retrieve details for a specific investigation.
 * Endpoint: GET /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}
 */
export async function getInvestigation(
  projectId: string,
  incidentId: string,
  investigationId: string,
  options?: RequestOptions
): Promise<Investigation> {
  return apiClient<Investigation>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}`,
    {
      method: 'GET',
      ...options,
    }
  );
}

/**
 * Initiate a new investigation for an incident.
 * Endpoint: POST /api/v1/projects/{project_id}/incidents/{incident_id}/investigations
 */
export async function createInvestigation(
  projectId: string,
  incidentId: string,
  data: InvestigationCreate,
  options?: RequestOptions
): Promise<Investigation> {
  return apiClient<Investigation>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations`,
    {
      method: 'POST',
      body: JSON.stringify(data),
      ...options,
    }
  );
}

/**
 * Update investigation details.
 * Endpoint: PATCH /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}
 */
export async function updateInvestigation(
  projectId: string,
  incidentId: string,
  investigationId: string,
  data: InvestigationUpdate,
  options?: RequestOptions
): Promise<Investigation> {
  return apiClient<Investigation>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
      ...options,
    }
  );
}

/**
 * Transition investigation status (PENDING -> RUNNING -> COMPLETED/FAILED/CANCELLED).
 * Endpoint: PATCH /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/status
 */
export async function transitionInvestigationStatus(
  projectId: string,
  incidentId: string,
  investigationId: string,
  data: InvestigationStatusUpdate,
  options?: RequestOptions
): Promise<Investigation> {
  return apiClient<Investigation>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}/status`,
    {
      method: 'PATCH',
      body: JSON.stringify(data),
      ...options,
    }
  );
}

/**
 * Delete an investigation.
 * Endpoint: DELETE /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}
 */
export async function deleteInvestigation(
  projectId: string,
  incidentId: string,
  investigationId: string,
  options?: RequestOptions
): Promise<InvestigationDeleteResponse> {
  return apiClient<InvestigationDeleteResponse>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}`,
    {
      method: 'DELETE',
      ...options,
    }
  );
}

/**
 * Trigger an operational investigation run synchronously and persist its results.
 * Endpoint: POST /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/run
 */
export async function runInvestigation(
  projectId: string,
  incidentId: string,
  investigationId: string,
  options?: RequestOptions
): Promise<InvestigationRunResponse> {
  return apiClient<InvestigationRunResponse>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}/run`,
    {
      method: 'POST',
      // Orchestration can take longer than ordinary API calls. Keep the run
      // request alive so the Stop control remains available during execution.
      timeoutMs: 120_000,
      ...options,
    }
  );
}

/**
 * Request cancellation of an active investigation.
 * Endpoint: POST /api/v1/projects/{project_id}/incidents/{incident_id}/investigations/{investigation_id}/cancel
 */
export async function cancelInvestigation(
  projectId: string,
  incidentId: string,
  investigationId: string,
  options?: RequestOptions
): Promise<InvestigationCancelResponse> {
  return apiClient<InvestigationCancelResponse>(
    `/api/v1/projects/${projectId}/incidents/${incidentId}/investigations/${investigationId}/cancel`,
    {
      method: 'POST',
      ...options,
    }
  );
}
