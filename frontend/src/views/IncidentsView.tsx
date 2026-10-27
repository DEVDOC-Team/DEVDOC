import React, { useState } from 'react';
import { useIncidents } from '../context/IncidentContext';
import { useProjects } from '../context/ProjectContext';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Panel } from '../components/ui/Panel';
import {
  AlertTriangle,
  ArrowUpRight,
  Filter,
  Plus,
  RefreshCw,
  Search,
  ShieldAlert,
} from 'lucide-react';
import type { IncidentSeverity, IncidentSource, IncidentStatus } from '../api/types';
import './views.css';

export interface IncidentsViewProps {
  onSelectIncident: (id: string) => void;
}

export const IncidentsView: React.FC<IncidentsViewProps> = ({ onSelectIncident }) => {
  const { selectedProject } = useProjects();
  const {
    incidents,
    loadingIncidents,
    error,
    refreshIncidents,
    selectIncident,
    createIncident,
  } = useIncidents();

  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Create Incident Modal State
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [title, setTitle] = useState('');
  const [severity, setSeverity] = useState<IncidentSeverity>('medium');
  const [source, setSource] = useState<IncidentSource>('manual');
  const [description, setDescription] = useState('');
  const [externalReference, setExternalReference] = useState('');
  const [affectedUsers, setAffectedUsers] = useState<number>(0);
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const filteredIncidents = incidents.filter((inc) => {
    const matchesSeverity = severityFilter === 'ALL' || inc.severity.toLowerCase() === severityFilter.toLowerCase();
    const matchesStatus = statusFilter === 'ALL' || inc.status.toLowerCase() === statusFilter.toLowerCase();
    const matchesSearch =
      inc.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      inc.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (inc.external_reference && inc.external_reference.toLowerCase().includes(searchQuery.toLowerCase()));

    return matchesSeverity && matchesStatus && matchesSearch;
  });

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setCreateError('Incident title is required');
      return;
    }

    setIsSubmitting(true);
    setCreateError(null);

    try {
      const created = await createIncident({
        title: title.trim(),
        severity,
        source,
        description: description.trim() || undefined,
        external_reference: externalReference.trim() || undefined,
        affected_users: Number(affectedUsers) || 0,
      });
      setShowCreateModal(false);
      setTitle('');
      setDescription('');
      setExternalReference('');
      setAffectedUsers(0);
      onSelectIncident(created.id);
    } catch (err: any) {
      setCreateError(err.message || 'Failed to report incident');
    } finally {
      setIsSubmitting(false);
    }
  };

  const getSeverityBadgeVariant = (sev: IncidentSeverity) => {
    switch (sev) {
      case 'critical':
        return 'sev1';
      case 'high':
        return 'sev2';
      case 'medium':
        return 'warn';
      case 'low':
      default:
        return 'neutral';
    }
  };

  const getStatusBadgeVariant = (st: IncidentStatus) => {
    switch (st) {
      case 'resolved':
      case 'closed':
        return 'ok';
      case 'investigating':
      case 'mitigated':
        return 'accent';
      case 'open':
      default:
        return 'warn';
    }
  };

  return (
    <div className="incidents-view">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h1 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 700, color: 'var(--devdoc-fg)' }}>
            Incident Management Queue
          </h1>
          <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            {selectedProject
              ? `Operational incidents tracked for workspace: ${selectedProject.name}`
              : 'Select a project to view operational incident tickets.'}
          </p>
        </div>

        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={refreshIncidents}
            disabled={loadingIncidents}
            icon={<RefreshCw size={13} className={loadingIncidents ? 'spin' : ''} />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setCreateError(null);
              setShowCreateModal(true);
            }}
            icon={<Plus size={14} />}
          >
            Report Incident
          </Button>
        </div>
      </div>

      {error && (
        <div
          style={{
            padding: '12px 14px',
            background: 'var(--devdoc-status-bad-bg)',
            border: '1px solid var(--devdoc-status-bad-border)',
            borderRadius: 'var(--radius-sm)',
            color: 'var(--devdoc-status-bad)',
            fontSize: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} />
            <span>{error}</span>
          </div>
          <Button variant="ghost" size="sm" onClick={refreshIncidents}>
            Retry
          </Button>
        </div>
      )}

      {/* Filters & Search Bar */}
      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1', minWidth: '220px' }}>
          <input
            type="text"
            placeholder="Search by title, incident ID, or external ref..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              background: 'var(--devdoc-surface-sunken)',
              border: '1px solid var(--devdoc-border)',
              color: 'var(--devdoc-fg)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 10px 6px 30px',
              fontSize: '12px',
            }}
          />
          <Search size={14} style={{ position: 'absolute', left: '10px', top: '8px', color: 'var(--devdoc-fg-dim)' }} />
        </div>

        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          <Filter size={13} color="var(--devdoc-fg-muted)" />
          <select
            value={severityFilter}
            onChange={(e) => setSeverityFilter(e.target.value)}
            style={{
              background: 'var(--devdoc-surface-sunken)',
              border: '1px solid var(--devdoc-border)',
              color: 'var(--devdoc-fg)',
              borderRadius: 'var(--radius-sm)',
              padding: '5px 8px',
              fontSize: '11px',
            }}
          >
            <option value="ALL">All Severities</option>
            <option value="CRITICAL">Critical (SEV-1)</option>
            <option value="HIGH">High (SEV-2)</option>
            <option value="MEDIUM">Medium (SEV-3)</option>
            <option value="LOW">Low (SEV-4)</option>
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              background: 'var(--devdoc-surface-sunken)',
              border: '1px solid var(--devdoc-border)',
              color: 'var(--devdoc-fg)',
              borderRadius: 'var(--radius-sm)',
              padding: '5px 8px',
              fontSize: '11px',
            }}
          >
            <option value="ALL">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="MITIGATED">Mitigated</option>
            <option value="RESOLVED">Resolved</option>
            <option value="CLOSED">Closed</option>
          </select>
        </div>
      </div>

      {/* Incidents Table / Cards */}
      <Panel
        title={`Incidents (${filteredIncidents.length})`}
        meta={selectedProject ? `Workspace: ${selectedProject.slug}` : 'All'}
      >
        {loadingIncidents && incidents.length === 0 ? (
          <div style={{ padding: '30px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '12px' }}>
            Loading incidents queue...
          </div>
        ) : filteredIncidents.length === 0 ? (
          <div style={{ padding: '36px', textAlign: 'center' }}>
            <ShieldAlert size={28} color="var(--devdoc-fg-dim)" style={{ marginBottom: '8px' }} />
            <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
              No Incidents Found
            </div>
            <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginTop: '4px' }}>
              {searchQuery || severityFilter !== 'ALL' || statusFilter !== 'ALL'
                ? 'No incidents match the active search or filter criteria.'
                : 'No incidents have been detected or recorded for this project.'}
            </p>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--devdoc-border)', color: 'var(--devdoc-fg-muted)', fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  <th style={{ padding: '8px 12px' }}>Incident ID</th>
                  <th style={{ padding: '8px 12px' }}>Severity</th>
                  <th style={{ padding: '8px 12px' }}>Title & Description</th>
                  <th style={{ padding: '8px 12px' }}>Source</th>
                  <th style={{ padding: '8px 12px' }}>Status</th>
                  <th style={{ padding: '8px 12px' }}>Detected</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {filteredIncidents.map((inc) => (
                  <tr
                    key={inc.id}
                    style={{ borderBottom: '1px solid var(--devdoc-border)', transition: 'background var(--transition-fast)' }}
                    className="table-row-hover"
                  >
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-accent)', fontWeight: 600 }}>
                      {inc.id.slice(0, 8)}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <Badge variant={getSeverityBadgeVariant(inc.severity)}>
                        {inc.severity.toUpperCase()}
                      </Badge>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ fontWeight: 600, color: 'var(--devdoc-fg)' }}>{inc.title}</div>
                      {inc.description && (
                        <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px', maxWidth: '420px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {inc.description}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
                      {inc.source.toUpperCase()}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <Badge variant={getStatusBadgeVariant(inc.status)}>
                        {inc.status.toUpperCase()}
                      </Badge>
                    </td>
                    <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: '11px', color: 'var(--devdoc-fg-dim)' }}>
                      {new Date(inc.detected_at).toLocaleTimeString()}
                    </td>
                    <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                      <Button
                        variant="primary"
                        size="sm"
                        onClick={() => {
                          selectIncident(inc.id);
                          onSelectIncident(inc.id);
                        }}
                        icon={<ArrowUpRight size={13} />}
                      >
                        Investigate
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      {/* Report Incident Modal */}
      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(16, 18, 20, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '16px',
          }}
          onClick={() => setShowCreateModal(false)}
        >
          <div
            style={{ width: '100%', maxWidth: '480px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <Panel
              title="Report Operational Incident"
              meta={
                <button
                  onClick={() => setShowCreateModal(false)}
                  style={{ color: 'var(--devdoc-fg-muted)', cursor: 'pointer' }}
                >
                  ✕
                </button>
              }
            >
              {createError && (
                <div
                  style={{
                    padding: '8px 10px',
                    background: 'var(--devdoc-status-bad-bg)',
                    border: '1px solid var(--devdoc-status-bad-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--devdoc-status-bad)',
                    fontSize: '11px',
                    marginBottom: '12px',
                  }}
                >
                  {createError}
                </div>
              )}

              <form onSubmit={handleCreateSubmit}>
                <div style={{ marginBottom: '12px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: 'var(--devdoc-fg-muted)',
                      marginBottom: '4px',
                    }}
                  >
                    Incident Summary / Title *
                  </label>
                  <input
                    type="text"
                    required
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g. Worker pool exhaustion: 504 Gateway Timeout"
                    style={{
                      width: '100%',
                      background: 'var(--devdoc-surface-sunken)',
                      border: '1px solid var(--devdoc-border)',
                      color: 'var(--devdoc-fg)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '8px 10px',
                      fontSize: '12px',
                    }}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '12px' }}>
                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '11px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: 'var(--devdoc-fg-muted)',
                        marginBottom: '4px',
                      }}
                    >
                      Severity Level
                    </label>
                    <select
                      value={severity}
                      onChange={(e) => setSeverity(e.target.value as IncidentSeverity)}
                      style={{
                        width: '100%',
                        background: 'var(--devdoc-surface-sunken)',
                        border: '1px solid var(--devdoc-border)',
                        color: 'var(--devdoc-fg)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '6px 8px',
                        fontSize: '11px',
                      }}
                    >
                      <option value="critical">Critical (SEV-1)</option>
                      <option value="high">High (SEV-2)</option>
                      <option value="medium">Medium (SEV-3)</option>
                      <option value="low">Low (SEV-4)</option>
                    </select>
                  </div>

                  <div>
                    <label
                      style={{
                        display: 'block',
                        fontSize: '11px',
                        textTransform: 'uppercase',
                        letterSpacing: '0.06em',
                        color: 'var(--devdoc-fg-muted)',
                        marginBottom: '4px',
                      }}
                    >
                      Reporting Origin
                    </label>
                    <select
                      value={source}
                      onChange={(e) => setSource(e.target.value as IncidentSource)}
                      style={{
                        width: '100%',
                        background: 'var(--devdoc-surface-sunken)',
                        border: '1px solid var(--devdoc-border)',
                        color: 'var(--devdoc-fg)',
                        borderRadius: 'var(--radius-sm)',
                        padding: '6px 8px',
                        fontSize: '11px',
                      }}
                    >
                      <option value="manual">Manual Report</option>
                      <option value="alert">Prometheus / Alert</option>
                      <option value="datadog">Datadog</option>
                      <option value="sentry">Sentry</option>
                      <option value="pagerduty">PagerDuty</option>
                    </select>
                  </div>
                </div>

                <div style={{ marginBottom: '12px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: 'var(--devdoc-fg-muted)',
                      marginBottom: '4px',
                    }}
                  >
                    External Reference (Optional)
                  </label>
                  <input
                    type="text"
                    value={externalReference}
                    onChange={(e) => setExternalReference(e.target.value)}
                    placeholder="e.g. SENTRY-ISSUE-4902 or PAGERDUTY-9102"
                    style={{
                      width: '100%',
                      background: 'var(--devdoc-surface-sunken)',
                      border: '1px solid var(--devdoc-border)',
                      color: 'var(--devdoc-fg)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '8px 10px',
                      fontFamily: 'var(--font-mono)',
                      fontSize: '11px',
                    }}
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label
                    style={{
                      display: 'block',
                      fontSize: '11px',
                      textTransform: 'uppercase',
                      letterSpacing: '0.06em',
                      color: 'var(--devdoc-fg-muted)',
                      marginBottom: '4px',
                    }}
                  >
                    Incident Description
                  </label>
                  <textarea
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Provide diagnostic signals, symptoms, observed error rates..."
                    style={{
                      width: '100%',
                      background: 'var(--devdoc-surface-sunken)',
                      border: '1px solid var(--devdoc-border)',
                      color: 'var(--devdoc-fg)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '8px 10px',
                      fontSize: '12px',
                      resize: 'none',
                    }}
                  />
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowCreateModal(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    disabled={isSubmitting || !title.trim()}
                  >
                    {isSubmitting ? 'Submitting...' : 'Create & Investigate'}
                  </Button>
                </div>
              </form>
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
};
