import React, { useState } from 'react';
import { useProjects } from '../context/ProjectContext';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { useAuth } from '../context/AuthContext';
import {
  FolderGit2,
  Plus,
  GitBranch,
  RefreshCw,
  AlertTriangle,
  Trash2,
  Lock,
  Globe,
  LogIn,
  ShieldAlert,
} from 'lucide-react';

export interface ProjectsViewProps {
  onNavigate?: (route: string) => void;
}

export const ProjectsView: React.FC<ProjectsViewProps> = ({ onNavigate }) => {
  const { status: authStatus, error: authError } = useAuth();
  const {
    projects,
    selectedProjectId,
    connectedRepo,
    loading,
    repoLoading,
    error,
    refreshProjects,
    selectProject,
    createProject,
    deleteProject,
  } = useProjects();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) {
      setCreateError('Project name is required');
      return;
    }

    setIsSubmitting(true);
    setCreateError(null);

    try {
      await createProject({
        name: newName.trim(),
        slug: newSlug.trim() || undefined,
        description: newDescription.trim() || undefined,
      });
      setShowCreateModal(false);
      setNewName('');
      setNewSlug('');
      setNewDescription('');
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string, name: string) => {
    if (window.confirm(`Are you sure you want to delete project "${name}"?`)) {
      try {
        await deleteProject(id);
      } catch {
        // Error handled in context
      }
    }
  };

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Monitored Projects & Workspaces
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Connected services, repository associations, and isolated Docker sandboxes managed by DEVDOC.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={refreshProjects}
            disabled={loading || authStatus === 'unauthenticated'}
            icon={<RefreshCw size={13} className={loading ? 'spin' : ''} />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              if (authStatus === 'unauthenticated' && onNavigate) {
                onNavigate('signin');
                return;
              }
              setCreateError(null);
              setShowCreateModal(true);
            }}
            icon={authStatus === 'unauthenticated' ? <LogIn size={14} /> : <Plus size={14} />}
          >
            {authStatus === 'unauthenticated' ? 'Sign In to Create' : 'Create Project'}
          </Button>
        </div>
      </div>

      {authStatus === 'unauthenticated' ? (
        <Panel style={{ textAlign: 'center', padding: '48px 24px', marginTop: '16px' }}>
          <div
            style={{
              display: 'inline-flex',
              padding: '16px',
              borderRadius: '50%',
              background: 'rgba(56, 189, 248, 0.1)',
              color: 'var(--devdoc-accent)',
              marginBottom: '16px',
            }}
          >
            <Lock size={32} />
          </div>
          <h3 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--devdoc-fg)', marginBottom: '8px' }}>
            Authentication Required
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', maxWidth: '460px', margin: '0 auto 20px', lineHeight: 1.6 }}>
            Monitored projects, repository bindings, and isolated Docker test sandboxes are protected workspace resources. Please authenticate with your Bearer access token to inspect and manage projects.
          </p>
          {(authError || error) && (
            <div
              style={{
                maxWidth: '460px',
                margin: '0 auto 20px',
                padding: '10px 14px',
                background: 'var(--devdoc-status-bad-bg)',
                border: '1px solid var(--devdoc-status-bad-border)',
                borderRadius: 'var(--radius-sm)',
                color: 'var(--devdoc-status-bad)',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                textAlign: 'left',
              }}
            >
              <ShieldAlert size={16} style={{ flexShrink: 0 }} />
              <span>{authError || error}</span>
            </div>
          )}
          {onNavigate && (
            <Button
              variant="primary"
              onClick={() => onNavigate('signin')}
              icon={<LogIn size={14} />}
            >
              Sign In to DEVDOC
            </Button>
          )}
        </Panel>
      ) : (
        <>
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
                margin: '14px 0',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <AlertTriangle size={16} />
                <span>{error}</span>
              </div>
              <Button variant="ghost" size="sm" onClick={refreshProjects}>
                Retry
              </Button>
            </div>
          )}

      {/* Loading Skeleton */}
      {loading && projects.length === 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px', marginTop: '16px' }}>
          {[1, 2, 3].map((i) => (
            <Panel key={i} style={{ opacity: 0.6 }}>
              <div style={{ height: '16px', background: 'var(--devdoc-surface-sunken)', width: '60%', borderRadius: '4px', marginBottom: '10px' }} />
              <div style={{ height: '12px', background: 'var(--devdoc-surface-sunken)', width: '85%', borderRadius: '4px', marginBottom: '8px' }} />
              <div style={{ height: '12px', background: 'var(--devdoc-surface-sunken)', width: '40%', borderRadius: '4px' }} />
            </Panel>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && projects.length === 0 && !error && (
        <Panel style={{ textAlign: 'center', padding: '36px 20px', marginTop: '16px' }}>
          <div
            style={{
              display: 'inline-flex',
              padding: '12px',
              borderRadius: '50%',
              background: 'rgba(56, 189, 248, 0.1)',
              color: 'var(--devdoc-accent)',
              marginBottom: '12px',
            }}
          >
            <FolderGit2 size={28} />
          </div>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            No Monitored Projects Found
          </h3>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', maxWidth: '420px', margin: '6px auto 16px' }}>
            Create your first project to bind code repositories, configure ephemeral test sandboxes, and enable autonomous incident investigation.
          </p>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowCreateModal(true)}
            icon={<Plus size={14} />}
          >
            Create Your First Project
          </Button>
        </Panel>
      )}

      {/* Real Projects Grid */}
      {projects.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: '14px', marginTop: '16px' }}>
          {projects.map((proj) => {
            const isSelected = proj.id === selectedProjectId;

            return (
              <Panel
                key={proj.id}
                title={
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <FolderGit2 size={16} color={isSelected ? 'var(--devdoc-accent)' : 'var(--devdoc-fg-muted)'} />
                    <span style={{ fontWeight: isSelected ? 700 : 500 }}>{proj.name}</span>
                  </div>
                }
                meta={
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {isSelected && <Badge variant="accent">ACTIVE</Badge>}
                    <Badge variant={proj.is_active ? 'ok' : 'neutral'}>
                      {proj.is_active ? 'ENABLED' : 'ARCHIVED'}
                    </Badge>
                  </div>
                }
                footer={
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                    <Button
                      variant={isSelected ? 'secondary' : 'primary'}
                      size="sm"
                      onClick={() => selectProject(proj.id)}
                    >
                      {isSelected ? 'Selected Active' : 'Select Project'}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDelete(proj.id, proj.name)}
                      icon={<Trash2 size={13} color="var(--devdoc-status-bad)" />}
                      aria-label="Delete project"
                    />
                  </div>
                }
                style={{
                  border: isSelected ? '1px solid var(--devdoc-accent)' : undefined,
                  boxShadow: isSelected ? '0 0 16px rgba(56, 189, 248, 0.1)' : undefined,
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', minHeight: '20px' }}>
                    {proj.description || 'No description provided.'}
                  </div>

                  <dl className="kv-list" style={{ marginTop: '4px' }}>
                    <dt>Slug</dt>
                    <dd>{proj.slug}</dd>
                    <dt>Project ID</dt>
                    <dd style={{ fontSize: '10px' }}>{proj.id}</dd>
                    <dt>Created</dt>
                    <dd>{new Date(proj.created_at).toLocaleDateString()}</dd>
                  </dl>

                  {/* Connected Repository Status */}
                  {isSelected && (
                    <div
                      style={{
                        marginTop: '8px',
                        padding: '10px 12px',
                        background: 'var(--devdoc-surface-sunken)',
                        borderRadius: 'var(--radius-sm)',
                        border: '1px solid var(--devdoc-border-subtle)',
                      }}
                    >
                      <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--devdoc-fg-muted)', marginBottom: '4px' }}>
                        Connected GitHub Repository
                      </div>
                      {repoLoading ? (
                        <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>Checking repository link...</div>
                      ) : connectedRepo ? (
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontFamily: 'var(--font-mono)' }}>
                            <GitBranch size={13} color="var(--devdoc-accent)" />
                            <span style={{ color: 'var(--devdoc-fg)', fontWeight: 600 }}>{connectedRepo.full_name}</span>
                            <span style={{ color: 'var(--devdoc-fg-dim)' }}>@{connectedRepo.default_branch}</span>
                          </div>
                          {connectedRepo.is_private ? (
                            <Badge variant="neutral"><Lock size={10} /> PRIVATE</Badge>
                          ) : (
                            <Badge variant="neutral"><Globe size={10} /> PUBLIC</Badge>
                          )}
                        </div>
                      ) : (
                        <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-dim)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span>No repository attached to this project.</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      )}
        </>
      )}

      {/* Create Project Modal */}
      {showCreateModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(10, 16, 32, 0.75)',
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
            style={{ width: '100%', maxWidth: '440px' }}
            onClick={(e) => e.stopPropagation()}
          >
            <Panel
              title="Create New Project"
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
                    Project Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    placeholder="e.g. Payments Gateway Core"
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
                    Slug (Optional)
                  </label>
                  <input
                    type="text"
                    value={newSlug}
                    onChange={(e) => setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                    placeholder="auto-generated from name if omitted"
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
                    Description (Optional)
                  </label>
                  <textarea
                    rows={3}
                    value={newDescription}
                    onChange={(e) => setNewDescription(e.target.value)}
                    placeholder="Brief description of the monitored codebase or system."
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
                    disabled={isSubmitting || !newName.trim()}
                  >
                    {isSubmitting ? 'Creating...' : 'Create Project'}
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
