import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';
import { useAuth } from './AuthContext';
import { useProjects } from './ProjectContext';
import { listIncidents, createIncident as apiCreateIncident } from '../api/incidents';
import {
  listInvestigations,
  createInvestigation as apiCreateInvestigation,
  runInvestigation as apiRunInvestigation,
} from '../api/investigations';
import { listApprovals, approveRequest, rejectRequest, cancelRequest } from '../api/approvals';
import type {
  Incident,
  IncidentCreate,
  Investigation,
  ApprovalResponse,
} from '../api/types';
import { ApiError } from '../api/client';

export interface IncidentContextValue {
  incidents: Incident[];
  selectedIncident: Incident | null;
  selectedIncidentId: string | null;
  isDemoMode: boolean;
  investigations: Investigation[];
  activeInvestigation: Investigation | null;
  approvals: ApprovalResponse[];
  activeApproval: ApprovalResponse | null;
  loadingIncidents: boolean;
  loadingInvestigations: boolean;
  runningInvestigation: boolean;
  isPolling: boolean;
  error: string | null;
  refreshIncidents: () => Promise<void>;
  refreshInvestigations: () => Promise<void>;
  selectIncident: (id: string) => void;
  selectDemoIncident: () => void;
  exitDemoMode: () => void;
  createIncident: (data: IncidentCreate) => Promise<Incident>;
  triggerInvestigationRun: () => Promise<void>;
  submitApprovalDecision: (approvalId: string, decision: 'approved' | 'rejected', reason: string) => Promise<void>;
  cancelApprovalDecision: (approvalId: string, reason: string) => Promise<void>;
  clearError: () => void;
}

const IncidentContext = createContext<IncidentContextValue | undefined>(undefined);

export const IncidentProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { status: authStatus } = useAuth();
  const { selectedProjectId } = useProjects();
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [approvals, setApprovals] = useState<ApprovalResponse[]>([]);
  const [activeApproval, setActiveApproval] = useState<ApprovalResponse | null>(null);
  const [loadingIncidents, setLoadingIncidents] = useState<boolean>(false);
  const [loadingInvestigations, setLoadingInvestigations] = useState<boolean>(false);
  const [runningInvestigation, setRunningInvestigation] = useState<boolean>(false);
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearError = useCallback(() => setError(null), []);

  const selectIncident = useCallback((id: string) => {
    setSelectedIncidentId(id);
  }, []);

  const selectDemoIncident = useCallback(() => {
    setSelectedIncidentId('INC-2291');
  }, []);

  const exitDemoMode = useCallback(() => {
    setSelectedIncidentId(incidents[0] ? incidents[0].id : null);
  }, [incidents]);

  // Fetch incidents for current selected project with cancellation
  const refreshIncidents = useCallback(async () => {
    if (!selectedProjectId || authStatus !== 'authenticated') {
      setIncidents([]);
      setSelectedIncidentId(null);
      setInvestigations([]);
      setActiveApproval(null);
      setLoadingIncidents(false);
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoadingIncidents(true);
    setError(null);

    try {
      const res = await listIncidents(
        selectedProjectId,
        { limit: 50, offset: 0 },
        { signal: abortControllerRef.current.signal }
      );
      const items = res.items || [];
      setIncidents(items);

      setSelectedIncidentId((currentId) => {
        if (currentId && items.some((i) => i.id === currentId)) {
          return currentId;
        }
        return items[0] ? items[0].id : null;
      });
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 0) {
        // Cancelled / aborted - safe to ignore
        return;
      }
      setError(err instanceof ApiError ? err.message : err.message || 'Failed to load incidents');
    } finally {
      setLoadingIncidents(false);
    }
  }, [selectedProjectId, authStatus]);

  // Project change triggers incident refresh and state reset
  useEffect(() => {
    refreshIncidents();
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [refreshIncidents]);

  // Fetch investigations for selected incident
  const refreshInvestigations = useCallback(async () => {
    if (!selectedProjectId || !selectedIncidentId || selectedIncidentId === 'INC-2291' || authStatus !== 'authenticated') {
      setInvestigations([]);
      setApprovals([]);
      setActiveApproval(null);
      setLoadingInvestigations(false);
      return;
    }

    setLoadingInvestigations(true);
    try {
      const res = await listInvestigations(selectedProjectId, selectedIncidentId, { limit: 20 });
      const items = res.items || [];
      setInvestigations(items);

      // Fetch approvals for the latest investigation if available
      const latest = items[0];
      if (latest) {
        try {
          const appRes = await listApprovals(selectedProjectId, latest.id, { limit: 20 });
          const appItems = appRes.items || [];
          setApprovals(appItems);
          setActiveApproval(appItems[0] || null);
        } catch {
          setApprovals([]);
          setActiveApproval(null);
        }
      } else {
        setApprovals([]);
        setActiveApproval(null);
      }
    } catch {
      // Non-fatal if incident has no investigations yet
      setInvestigations([]);
      setApprovals([]);
      setActiveApproval(null);
    } finally {
      setLoadingInvestigations(false);
    }
  }, [selectedProjectId, selectedIncidentId, authStatus]);

  useEffect(() => {
    refreshInvestigations();
  }, [refreshInvestigations]);

  const activeInvestigation = investigations[0] || null;

  // Bounded polling when active investigation is running
  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (activeInvestigation?.status === 'running') {
      setIsPolling(true);
      pollTimerRef.current = setInterval(() => {
        refreshInvestigations();
      }, 3500);
    } else {
      setIsPolling(false);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [activeInvestigation?.status, refreshInvestigations]);

  const createIncident = useCallback(
    async (data: IncidentCreate): Promise<Incident> => {
      if (!selectedProjectId) throw new Error('No project selected');
      setLoadingIncidents(true);
      setError(null);
      try {
        const created = await apiCreateIncident(selectedProjectId, data);
        setIncidents((prev) => [created, ...prev]);
        setSelectedIncidentId(created.id);
        return created;
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to create incident';
        setError(msg);
        throw err;
      } finally {
        setLoadingIncidents(false);
      }
    },
    [selectedProjectId]
  );

  const triggerInvestigationRun = useCallback(async () => {
    if (!selectedProjectId || !selectedIncidentId) return;

    setRunningInvestigation(true);
    setError(null);

    try {
      let targetInvId = activeInvestigation ? activeInvestigation.id : null;

      // If no investigation exists or current is completed, create a new one first
      if (!targetInvId || activeInvestigation?.status === 'completed' || activeInvestigation?.status === 'failed') {
        const newInv = await apiCreateInvestigation(selectedProjectId, selectedIncidentId, {
          summary: 'Autonomous root-cause diagnosis and candidate patch generation',
          status: 'pending',
        });
        targetInvId = newInv.id;
      }

      await apiRunInvestigation(selectedProjectId, selectedIncidentId, targetInvId);
      await refreshInvestigations();
    } catch (err: any) {
      const msg = err instanceof ApiError ? err.message : err.message || 'Failed to execute investigation run';
      setError(msg);
    } finally {
      setRunningInvestigation(false);
    }
  }, [selectedProjectId, selectedIncidentId, activeInvestigation, refreshInvestigations]);

  const submitApprovalDecision = useCallback(
    async (approvalId: string, decision: 'approved' | 'rejected', reason: string) => {
      if (!selectedProjectId || !activeInvestigation) return;
      setError(null);
      try {
        let res: ApprovalResponse;
        if (decision === 'approved') {
          res = await approveRequest(selectedProjectId, activeInvestigation.id, approvalId, reason);
        } else {
          res = await rejectRequest(selectedProjectId, activeInvestigation.id, approvalId, reason);
        }
        setActiveApproval(res);
        setApprovals((prev) => prev.map((a) => (a.id === approvalId ? res : a)));
        await refreshInvestigations();
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to submit approval decision';
        setError(msg);
        throw err;
      }
    },
    [selectedProjectId, activeInvestigation, refreshInvestigations]
  );

  const cancelApprovalDecision = useCallback(
    async (approvalId: string, reason: string) => {
      if (!selectedProjectId || !activeInvestigation) return;
      setError(null);
      try {
        const res = await cancelRequest(selectedProjectId, activeInvestigation.id, approvalId, reason);
        setActiveApproval(res);
        setApprovals((prev) => prev.map((a) => (a.id === approvalId ? res : a)));
        await refreshInvestigations();
      } catch (err: any) {
        const msg = err instanceof ApiError ? err.message : err.message || 'Failed to cancel approval request';
        setError(msg);
        throw err;
      }
    },
    [selectedProjectId, activeInvestigation, refreshInvestigations]
  );

  const isDemoMode = selectedIncidentId === 'INC-2291';

  const DEMO_INCIDENT: Incident = {
    id: 'INC-2291',
    project_id: selectedProjectId || 'proj-demo',
    repository_id: null,
    reported_by_id: null,
    title: 'Checkout API 5xx spike (Connection Pool Exhaustion)',
    severity: 'high',
    status: 'investigating',
    source: 'datadog',
    description: 'Elevated HTTP 504 errors in checkout gateway service due to HikariCP connection starvation in retry loop.',
    affected_users: 1420,
    external_reference: 'DD-ALERT-8819',
    detected_at: '2026-10-25T14:02:11Z',
    resolved_at: null,
    created_at: '2026-10-25T14:07:02Z',
    updated_at: '2026-10-25T14:12:00Z',
  };

  const selectedIncident = isDemoMode
    ? DEMO_INCIDENT
    : incidents.find((i) => i.id === selectedIncidentId) || null;

  return (
    <IncidentContext.Provider
      value={{
        incidents,
        selectedIncident,
        selectedIncidentId,
        isDemoMode,
        investigations,
        activeInvestigation,
        approvals,
        activeApproval,
        loadingIncidents,
        loadingInvestigations,
        runningInvestigation,
        isPolling,
        error,
        refreshIncidents,
        refreshInvestigations,
        selectIncident,
        selectDemoIncident,
        exitDemoMode,
        createIncident,
        triggerInvestigationRun,
        submitApprovalDecision,
        cancelApprovalDecision,
        clearError,
      }}
    >
      {children}
    </IncidentContext.Provider>
  );
};

export const useIncidents = (): IncidentContextValue => {
  const context = useContext(IncidentContext);
  if (!context) {
    throw new Error('useIncidents must be used within an IncidentProvider');
  }
  return context;
};
