import React, { useState } from 'react';
import { useProjects } from '../context/ProjectContext';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { useAuth } from '../context/AuthContext';
import {
  initiateGitHubConnect,
  listGitHubRepositories,
} from '../api/github';
import type { GitHubRepositoryInfo } from '../api/types';
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
  Search,
  CheckCircle2,
  ArrowRight,
  Unlink,
} from 'lucide-react';

export interface ProjectsViewProps {
  onNavigate?: (route: string) => void;
}

// GitHub Mark Icon SVG
const GitHubIcon: React.FC<{ size?: number; style?: React.CSSProperties }> = ({ size = 16, style }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    style={{ display: 'inline-block', verticalAlign: 'middle', flexShrink: 0, ...style }}
  >
    <path
      fillRule="evenodd"
      clipRule="evenodd"
      d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
    />
  </svg>
);

export const ProjectsView: React.FC<ProjectsViewProps> = ({ onNavigate }) => {
  const { status: authStatus, error: authError } = useAuth();
  const {
    projects,
    selectedProjectId,
    connectedRepo,
    githubConnection,
    loading,
    repoLoading,
    githubConnectionLoading,
    error,
    refreshProjects,
    refreshGitHubConnection,
    disconnectUserGitHub,
    attachRepoToProject,
    disconnectRepoFromProject,
    selectProject,
    createProject,
    deleteProject,
  } = useProjects();

  // Create Project Modal state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // GitHub Connection state
  const [isConnectingGithub, setIsConnectingGithub] = useState(false);
  const [githubActionError, setGithubActionError] = useState<string | null>(null);

  // Repository Picker Modal state
  const [showRepoModal, setShowRepoModal] = useState(false);
  const [repoList, setRepoList] = useState<GitHubRepositoryInfo[]>([]);
  const [repoListLoading, setRepoListLoading] = useState(false);
  const [repoListError, setRepoListError] = useState<string | null>(null);
  const [repoSearch, setRepoSearch] = useState('');
  const [attachingRepo, setAttachingRepo] = useState<string | null>(null);

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

  const handleConnectGitHub = async () => {
    setGithubActionError(null);
    setIsConnectingGithub(true);
    try {
      const resp = await initiateGitHubConnect();
      if (!resp.authorization_url) {
        throw new Error('No authorization URL returned by server');
      }

      const width = 600;
      const height = 750;
      const left = window.screenX + (window.outerWidth - width) / 2;
      const top = window.screenY + (window.outerHeight - height) / 2;

      const popup = window.open(
        resp.authorization_url,
        'devdoc_github_oauth',
        `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=no`
      );

      // Periodically check if popup closed
      const timer = setInterval(() => {
        if (!popup || popup.closed) {
          clearInterval(timer);
          setIsConnectingGithub(false);
          refreshGitHubConnection();
        }
      }, 1000);
    } catch (err: any) {
      setGithubActionError(err.message || 'Failed to initiate GitHub authorization flow');
      setIsConnectingGithub(false);
    }
  };

  const handleDisconnectGitHub = async () => {
    if (window.confirm('Are you sure you want to disconnect your GitHub account from DEVDOC? Stored OAuth tokens will be revoked.')) {
      setGithubActionError(null);
      try {
        await disconnectUserGitHub();
      } catch (err: any) {
        setGithubActionError(err.message || 'Failed to disconnect GitHub');
      }
    }
  };

  const openRepoPicker = async (projectId: string) => {
    selectProject(projectId);
    setShowRepoModal(true);
    setRepoListLoading(true);
    setRepoListError(null);
    setRepoSearch('');

    try {
      const resp = await listGitHubRepositories({ per_page: 100 });
      setRepoList(resp.items || []);
    } catch (err: any) {
      setRepoListError(err.message || 'Failed to fetch repositories from GitHub');
    } finally {
      setRepoListLoading(false);
    }
  };

  const handleSelectRepository = async (repoFullName: string) => {
    setAttachingRepo(repoFullName);
    setRepoListError(null);

    try {
      await attachRepoToProject(repoFullName);
      setShowRepoModal(false);
    } catch (err: any) {
      setRepoListError(err.message || `Failed to attach repository ${repoFullName}`);
    } finally {
      setAttachingRepo(null);
    }
  };

  const handleDetachRepo = async () => {
    if (window.confirm('Disconnect this repository from the active project? Incident investigations will require re-attaching.')) {
      try {
        await disconnectRepoFromProject();
      } catch {
        // Error handled in context
      }
    }
  };

  const filteredRepos = repoList.filter((repo) => {
    if (!repoSearch.trim()) return true;
    const query = repoSearch.toLowerCase();
    return (
      repo.full_name.toLowerCase().includes(query) ||
      repo.owner.toLowerCase().includes(query) ||
      (repo.description && repo.description.toLowerCase().includes(query))
    );
  });

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Monitored Projects & GitHub Repositories
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Connect your GitHub account, associate monitored repositories, and launch evidence-grounded AI investigations.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              refreshProjects();
              refreshGitHubConnection();
            }}
            disabled={loading || authStatus === 'unauthenticated'}
            icon={<RefreshCw size={13} className={loading || githubConnectionLoading ? 'spin' : ''} />}
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
            Monitored projects, repository bindings, and isolated Docker test sandboxes are protected workspace resources. Please authenticate with your registered account to manage projects.
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
          {/* GitHub Account Authorization Panel */}
          <div style={{ marginTop: '16px' }}>
            <Panel
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <GitHubIcon size={18} />
                  <span>GitHub Account Authorization</span>
                </div>
              }
              meta={
                githubConnection?.connected ? (
                  <Badge variant="ok">CONNECTED</Badge>
                ) : (
                  <Badge variant="neutral">NOT CONNECTED</Badge>
                )
              }
            >
              {githubActionError && (
                <div
                  style={{
                    padding: '10px 12px',
                    background: 'var(--devdoc-status-bad-bg)',
                    border: '1px solid var(--devdoc-status-bad-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--devdoc-status-bad)',
                    fontSize: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    marginBottom: '12px',
                  }}
                >
                  <AlertTriangle size={15} />
                  <span>{githubActionError}</span>
                </div>
              )}

              {githubConnection?.connected ? (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {githubConnection.avatar_url ? (
                      <img
                        src={githubConnection.avatar_url}
                        alt={githubConnection.github_username || 'GitHub user'}
                        style={{ width: '40px', height: '40px', borderRadius: '50%', border: '1px solid var(--devdoc-border)' }}
                      />
                    ) : (
                      <div
                        style={{
                          width: '40px',
                          height: '40px',
                          borderRadius: '50%',
                          background: 'var(--devdoc-surface-sunken)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <GitHubIcon size={20} />
                      </div>
                    )}
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '14px', color: 'var(--devdoc-fg)' }}>
                        @{githubConnection.github_username}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
                        Authorized Scope: <code>{githubConnection.scope || 'repo, read:user'}</code>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={refreshGitHubConnection}
                      disabled={githubConnectionLoading}
                      icon={<RefreshCw size={12} className={githubConnectionLoading ? 'spin' : ''} />}
                    >
                      Sync
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleDisconnectGitHub}
                      disabled={githubConnectionLoading}
                      icon={<Unlink size={12} color="var(--devdoc-status-bad)" />}
                    >
                      Disconnect GitHub
                    </Button>
                  </div>
                </div>
              ) : (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px',
                  }}
                >
                  <div style={{ maxWidth: '580px' }}>
                    <p style={{ fontSize: '13px', color: 'var(--devdoc-fg)', margin: 0, fontWeight: 500 }}>
                      Connect your GitHub account to enable repository investigation
                    </p>
                    <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', margin: '4px 0 0 0' }}>
                      DEVDOC securely accesses authorized repositories via GitHub OAuth. OAuth state tokens are cryptographically signed to prevent CSRF. Tokens are stored encrypted on the backend.
                    </p>
                  </div>

                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleConnectGitHub}
                    disabled={isConnectingGithub || githubConnectionLoading}
                    icon={<GitHubIcon size={14} />}
                  >
                    {isConnectingGithub ? 'Opening GitHub Authorization...' : 'Connect GitHub'}
                  </Button>
                </div>
              )}
            </Panel>
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
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '14px', marginTop: '16px' }}>
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
                            padding: '12px',
                            background: 'var(--devdoc-surface-sunken)',
                            borderRadius: 'var(--radius-sm)',
                            border: '1px solid var(--devdoc-border-subtle)',
                          }}
                        >
                          <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.06em', color: 'var(--devdoc-fg-muted)', marginBottom: '8px' }}>
                            Connected GitHub Repository
                          </div>

                          {repoLoading ? (
                            <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>Checking repository link...</div>
                          ) : connectedRepo ? (
                            <div>
                              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
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

                              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                                <Button
                                  variant="primary"
                                  size="sm"
                                  onClick={() => onNavigate?.('investigations')}
                                  icon={<ArrowRight size={13} />}
                                >
                                  Investigate Incidents
                                </Button>
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() => openRepoPicker(proj.id)}
                                >
                                  Change Repo
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={handleDetachRepo}
                                  icon={<Unlink size={12} />}
                                >
                                  Detach
                                </Button>
                              </div>
                            </div>
                          ) : (
                            <div>
                              <div style={{ fontSize: '12px', color: 'var(--devdoc-fg-dim)', marginBottom: '10px' }}>
                                No repository attached to this project.
                              </div>
                              {githubConnection?.connected ? (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() => openRepoPicker(proj.id)}
                                  icon={<FolderGit2 size={13} />}
                                >
                                  Select GitHub Repository
                                </Button>
                              ) : (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={handleConnectGitHub}
                                  icon={<GitHubIcon size={13} />}
                                >
                                  Connect GitHub to Select Repo
                                </Button>
                              )}
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

      {/* Repository Picker Modal */}
      {showRepoModal && (
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
          onClick={() => setShowRepoModal(false)}
        >
          <div
            style={{ width: '100%', maxWidth: '620px', maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}
            onClick={(e) => e.stopPropagation()}
          >
            <Panel
              title={
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <GitHubIcon size={18} />
                  <span>Select GitHub Repository</span>
                </div>
              }
              meta={
                <button
                  onClick={() => setShowRepoModal(false)}
                  style={{ background: 'none', border: 'none', color: 'var(--devdoc-fg-muted)', cursor: 'pointer', fontSize: '16px' }}
                >
                  ✕
                </button>
              }
            >
              <p style={{ fontSize: '12px', color: 'var(--devdoc-fg-muted)', marginBottom: '12px' }}>
                Select an authorized repository from your GitHub account to attach to the active project. DEVDOC will analyze code, commits, and dependencies to investigate incidents.
              </p>

              {repoListError && (
                <div
                  style={{
                    padding: '8px 12px',
                    background: 'var(--devdoc-status-bad-bg)',
                    border: '1px solid var(--devdoc-status-bad-border)',
                    borderRadius: 'var(--radius-sm)',
                    color: 'var(--devdoc-status-bad)',
                    fontSize: '12px',
                    marginBottom: '12px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <AlertTriangle size={14} />
                  <span>{repoListError}</span>
                </div>
              )}

              {/* Search filter */}
              <div style={{ position: 'relative', marginBottom: '12px' }}>
                <input
                  type="text"
                  value={repoSearch}
                  onChange={(e) => setRepoSearch(e.target.value)}
                  placeholder="Filter by repository name or owner..."
                  style={{
                    width: '100%',
                    background: 'var(--devdoc-surface-sunken)',
                    border: '1px solid var(--devdoc-border)',
                    color: 'var(--devdoc-fg)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '8px 12px 8px 32px',
                    fontSize: '12px',
                  }}
                />
                <Search
                  size={14}
                  style={{
                    position: 'absolute',
                    left: '10px',
                    top: '50%',
                    transform: 'translateY(-50%)',
                    color: 'var(--devdoc-fg-dim)',
                    pointerEvents: 'none',
                  }}
                />
              </div>

              {/* Repository List */}
              <div
                style={{
                  maxHeight: '360px',
                  overflowY: 'auto',
                  border: '1px solid var(--devdoc-border-subtle)',
                  borderRadius: 'var(--radius-sm)',
                }}
              >
                {repoListLoading ? (
                  <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '13px' }}>
                    <RefreshCw size={20} className="spin" style={{ margin: '0 auto 8px', display: 'block', color: 'var(--devdoc-accent)' }} />
                    Loading authorized repositories from GitHub...
                  </div>
                ) : filteredRepos.length === 0 ? (
                  <div style={{ padding: '32px 16px', textAlign: 'center', color: 'var(--devdoc-fg-muted)', fontSize: '13px' }}>
                    {repoSearch ? 'No repositories matched your search query.' : 'No repositories accessible on this GitHub account.'}
                  </div>
                ) : (
                  filteredRepos.map((repo) => {
                    const isAttaching = attachingRepo === repo.full_name;
                    const isCurrent = connectedRepo?.full_name === repo.full_name;

                    return (
                      <div
                        key={repo.id}
                        style={{
                          padding: '10px 14px',
                          borderBottom: '1px solid var(--devdoc-border-subtle)',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: '12px',
                          background: isCurrent ? 'rgba(56, 189, 248, 0.05)' : undefined,
                        }}
                      >
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: 600, fontSize: '13px', color: 'var(--devdoc-fg)', fontFamily: 'var(--font-mono)' }}>
                              {repo.full_name}
                            </span>
                            {repo.is_private ? (
                              <Badge variant="neutral"><Lock size={9} /> Private</Badge>
                            ) : (
                              <Badge variant="neutral"><Globe size={9} /> Public</Badge>
                            )}
                            {isCurrent && <Badge variant="accent">CURRENT</Badge>}
                          </div>
                          {repo.description && (
                            <div
                              style={{
                                fontSize: '11px',
                                color: 'var(--devdoc-fg-muted)',
                                marginTop: '3px',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              {repo.description}
                            </div>
                          )}
                          <div style={{ fontSize: '10px', color: 'var(--devdoc-fg-dim)', marginTop: '2px' }}>
                            Default branch: <code>{repo.default_branch}</code> {repo.language && `• ${repo.language}`}
                          </div>
                        </div>

                        <Button
                          variant={isCurrent ? 'secondary' : 'primary'}
                          size="sm"
                          disabled={isAttaching || isCurrent}
                          onClick={() => handleSelectRepository(repo.full_name)}
                          icon={isCurrent ? <CheckCircle2 size={12} /> : undefined}
                        >
                          {isAttaching ? 'Attaching...' : isCurrent ? 'Attached' : 'Select'}
                        </Button>
                      </div>
                    );
                  })
                )}
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '14px' }}>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowRepoModal(false)}
                >
                  Close
                </Button>
              </div>
            </Panel>
          </div>
        </div>
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
                  style={{ background: 'none', border: 'none', color: 'var(--devdoc-fg-muted)', cursor: 'pointer' }}
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
