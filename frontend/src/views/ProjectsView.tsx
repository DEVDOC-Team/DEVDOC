import React, { useState } from 'react';
import { Panel } from '../components/ui/Panel';
import { Badge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { GitBranch, Layers, FolderGit2, Plus, ExternalLink, Activity } from 'lucide-react';

interface ProjectItem {
  id: string;
  name: string;
  repo: string;
  defaultBranch: string;
  tier: 'TIER-0' | 'TIER-1' | 'TIER-2';
  sandbox: 'DOCKER' | 'K8S' | 'PROCESS';
  healthScore: number;
  openIncidents: number;
  activeInvestigations: number;
  lastIncident: string;
}

const PROJECTS_DATA: ProjectItem[] = [
  {
    id: 'prj-001',
    name: 'DEVDOC Core Platform',
    repo: 'DEVDOC-Team/DEVDOC',
    defaultBranch: 'frontend',
    tier: 'TIER-0',
    sandbox: 'DOCKER',
    healthScore: 98,
    openIncidents: 1,
    activeInvestigations: 1,
    lastIncident: 'INC-2291 (30m ago)'
  },
  {
    id: 'prj-002',
    name: 'Ingestion Pipeline & Log Daemon',
    repo: 'DEVDOC-Team/ingest-worker',
    defaultBranch: 'main',
    tier: 'TIER-0',
    sandbox: 'DOCKER',
    healthScore: 100,
    openIncidents: 0,
    activeInvestigations: 0,
    lastIncident: 'None in 14d'
  },
  {
    id: 'prj-003',
    name: 'Auth & RLS Gateway',
    repo: 'DEVDOC-Team/auth-service',
    defaultBranch: 'main',
    tier: 'TIER-0',
    sandbox: 'DOCKER',
    healthScore: 99,
    openIncidents: 0,
    activeInvestigations: 0,
    lastIncident: 'INC-2284 (3d ago)'
  },
  {
    id: 'prj-004',
    name: 'Nebius Token Orchestrator',
    repo: 'DEVDOC-Team/nebius-orchestrator',
    defaultBranch: 'main',
    tier: 'TIER-1',
    sandbox: 'PROCESS',
    healthScore: 96,
    openIncidents: 1,
    activeInvestigations: 0,
    lastIncident: 'INC-2290 (4h ago)'
  }
];

export const ProjectsView: React.FC = () => {
  const [filterTier, setFilterTier] = useState<string>('ALL');

  const filtered = PROJECTS_DATA.filter(p => filterTier === 'ALL' || p.tier === filterTier);

  return (
    <div className="view-container">
      <div className="incident-header-banner">
        <div>
          <h2 style={{ fontFamily: 'var(--font-display)', fontSize: '20px', fontWeight: 600, color: 'var(--devdoc-fg)' }}>
            Monitored Projects & Repositories
          </h2>
          <p style={{ fontSize: '13px', color: 'var(--devdoc-fg-muted)', marginTop: '2px' }}>
            Connected repositories with automated branch mirroring, sandbox containers, and evidence scanners.
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <Button variant="primary" size="sm" icon={<Plus size={14} />}>
            Connect Repository
          </Button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px', margin: '14px 0' }}>
        {['ALL', 'TIER-0', 'TIER-1', 'TIER-2'].map(t => (
          <button
            key={t}
            onClick={() => setFilterTier(t)}
            style={{
              background: filterTier === t ? 'var(--devdoc-surface-active)' : 'var(--devdoc-surface)',
              border: '1px solid',
              borderColor: filterTier === t ? 'var(--devdoc-border-focus)' : 'var(--devdoc-border)',
              color: filterTier === t ? 'var(--devdoc-accent)' : 'var(--devdoc-fg-muted)',
              borderRadius: 'var(--radius-sm)',
              padding: '6px 14px',
              fontSize: '12px',
              cursor: 'pointer',
              fontWeight: 500,
              transition: 'all var(--transition-fast)'
            }}
          >
            {t === 'ALL' ? 'All Services' : t}
          </button>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px' }}>
        {filtered.map(proj => (
          <Panel
            key={proj.id}
            title={
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FolderGit2 size={16} color="var(--devdoc-accent)" />
                <span>{proj.name}</span>
              </div>
            }
            meta={<Badge variant={proj.tier === 'TIER-0' ? 'accent' : 'neutral'}>{proj.tier}</Badge>}
            footer={
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: 'var(--devdoc-fg-muted)' }}>
                  <Layers size={13} />
                  <span>Sandbox: <b style={{ color: 'var(--devdoc-fg)' }}>{proj.sandbox}</b></span>
                </div>
                <Button variant="ghost" size="sm" icon={<ExternalLink size={13} />}>
                  Inspect
                </Button>
              </div>
            }
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', fontFamily: 'var(--font-mono)', color: 'var(--devdoc-fg-dim)' }}>
                <GitBranch size={13} />
                <span>{proj.repo} @ {proj.defaultBranch}</span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', padding: '10px', background: 'var(--devdoc-surface-sunken)', borderRadius: 'var(--radius-sm)' }}>
                <div>
                  <div style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase' }}>Health Index</div>
                  <div style={{ fontSize: '18px', fontWeight: 600, color: proj.healthScore > 95 ? 'var(--devdoc-ok)' : 'var(--devdoc-warn)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Activity size={14} />
                    {proj.healthScore}%
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '10px', color: 'var(--devdoc-fg-muted)', textTransform: 'uppercase' }}>Open Incidents</div>
                  <div style={{ fontSize: '18px', fontWeight: 600, color: proj.openIncidents > 0 ? 'var(--devdoc-warn)' : 'var(--devdoc-fg)' }}>
                    {proj.openIncidents}
                  </div>
                </div>
              </div>

              <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', display: 'flex', justifyContent: 'space-between' }}>
                <span>Latest Incident:</span>
                <span style={{ color: 'var(--devdoc-fg)', fontWeight: 500 }}>{proj.lastIncident}</span>
              </div>
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
};
