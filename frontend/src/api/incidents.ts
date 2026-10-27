import { apiClient, type RequestOptions } from './client';
import type {
  Incident,
  IncidentCreate,
  IncidentDeleteResponse,
  IncidentListResponse,
  IncidentSeverity,
  IncidentSource,
  IncidentStatus,
  IncidentStatusUpdate,
  IncidentUpdate,
} from './types';

export interface ListIncidentsParams {
  limit?: number;
  offset?: number;
  status?: IncidentStatus;
  severity?: IncidentSeverity;
  source?: IncidentSource;
}

/**
 * List incidents for an authorized project.
 * Endpoint: GET /api/v1/projects/{project_id}/incidents
 */
export async function listIncidents(
  projectId: string,
  params?: ListIncidentsParams,
  options?: RequestOptions
): Promise<IncidentListResponse> {
  const query = new URLSearchParams();
  if (params?.limit !== undefined) query.set('limit', String(params.limit));
  if (params?.offset !== undefined) query.set('offset', String(params.offset));
  if (params?.status) query.set('status', params.status);
  if (params?.severity) query.set('severity', params.severity);
  if (params?.source) query.set('source', params.source);

  const qs = query.toString();
  const endpoint = `/api/v1/projects/${projectId}/incidents${qs ? `?${qs}` : ''}`;

  return apiClient<IncidentListResponse>(endpoint, {
    method: 'GET',
    ...options,
  });
}

/**
 * Retrieve a specific incident in the authorized project.
 * Endpoint: GET /api/v1/projects/{project_id}/incidents/{incident_id}
 */
export async function getIncident(
  projectId: string,
  incidentId: string,
  options?: RequestOptions
): Promise<Incident> {
  return apiClient<Incident>(`/api/v1/projects/${projectId}/incidents/${incidentId}`, {
    method: 'GET',
    ...options,
  });
}

/**
 * Create a new incident within an authorized project.
 * Endpoint: POST /api/v1/projects/{project_id}/incidents
 */
export async function createIncident(
  projectId: string,
  data: IncidentCreate,
  options?: RequestOptions
): Promise<Incident> {
  return apiClient<Incident>(`/api/v1/projects/${projectId}/incidents`, {
    method: 'POST',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Update mutable fields on an incident.
 * Endpoint: PATCH /api/v1/projects/{project_id}/incidents/{incident_id}
 */
export async function updateIncident(
  projectId: string,
  incidentId: string,
  data: IncidentUpdate,
  options?: RequestOptions
): Promise<Incident> {
  return apiClient<Incident>(`/api/v1/projects/${projectId}/incidents/${incidentId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Transition incident status (strict state machine: OPEN -> INVESTIGATING -> MITIGATED -> RESOLVED -> CLOSED).
 * Endpoint: PATCH /api/v1/projects/{project_id}/incidents/{incident_id}/status
 */
export async function transitionIncidentStatus(
  projectId: string,
  incidentId: string,
  data: IncidentStatusUpdate,
  options?: RequestOptions
): Promise<Incident> {
  return apiClient<Incident>(`/api/v1/projects/${projectId}/incidents/${incidentId}/status`, {
    method: 'PATCH',
    body: JSON.stringify(data),
    ...options,
  });
}

/**
 * Delete an incident within the authorized project.
 * Endpoint: DELETE /api/v1/projects/{project_id}/incidents/{incident_id}
 */
export async function deleteIncident(
  projectId: string,
  incidentId: string,
  options?: RequestOptions
): Promise<IncidentDeleteResponse> {
  return apiClient<IncidentDeleteResponse>(`/api/v1/projects/${projectId}/incidents/${incidentId}`, {
    method: 'DELETE',
    ...options,
  });
}
