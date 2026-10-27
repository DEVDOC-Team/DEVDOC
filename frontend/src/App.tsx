import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProjectProvider, useProjects } from './context/ProjectContext';
import { IncidentProvider, useIncidents } from './context/IncidentContext';
import { AppShell } from './components/layout/AppShell';
import type { NavRoute } from './components/layout/Sidebar';
import { OverviewView } from './views/OverviewView';
import { IncidentsView } from './views/IncidentsView';
import { InvestigationConsoleView } from './views/InvestigationConsoleView';
import { ApprovalsView } from './views/ApprovalsView';
import { AuditView } from './views/AuditView';
import { ProjectsView } from './views/ProjectsView';
import { SettingsView } from './views/SettingsView';
import { SignInView } from './views/SignInView';
import { NotFoundView } from './views/NotFoundView';
import { StatusPulse } from './components/ui/StatusPulse';

const AppContent: React.FC = () => {
  const { isAuthResolving } = useAuth();
  const { selectedProject } = useProjects();
  const { selectedIncident, selectIncident, isDemoMode } = useIncidents();
  const [activeRoute, setActiveRoute] = useState<NavRoute>('investigations');

  // Prevent UI flash while resolving initial stored session
  if (isAuthResolving) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          background: 'var(--devdoc-canvas)',
          color: 'var(--devdoc-fg-muted)',
          gap: '16px',
        }}
      >
        <img
          src="/assets/devdoc-logo.jpg"
          alt="DevDOC Logo"
          style={{
            width: 76,
            height: 76,
            borderRadius: 16,
            boxShadow: '0 0 32px rgba(245, 158, 11, 0.25), 0 0 12px rgba(245, 158, 11, 0.15)',
            objectFit: 'cover',
          }}
        />
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <StatusPulse status="accent" />
          <span style={{ fontFamily: 'var(--font-display)', fontSize: '13px', letterSpacing: '0.08em', color: 'var(--devdoc-fg)', fontWeight: 600 }}>
            Initializing DevDOC investigation engine...
          </span>
        </div>
        <div style={{ fontSize: '11px', color: 'var(--devdoc-fg-muted)', letterSpacing: '0.04em' }}>
          Autonomous AI DevOps & SRE Incident Platform
        </div>
      </div>
    );
  }

  const handleSelectIncident = (id: string) => {
    selectIncident(id);
    setActiveRoute('investigations');
  };

  const getBreadcrumb = () => {
    const projectPrefix = selectedProject ? `PROJECT: ${selectedProject.name}` : 'WORKSPACE';

    switch (activeRoute) {
      case 'overview':
        return `${projectPrefix} / Operations Deck`;
      case 'incidents':
        return `${projectPrefix} / Incidents Queue`;
      case 'investigations':
        if (isDemoMode) {
          return `PROD / checkout-api / INC-2291 [DEMO DATA]`;
        }
        return `PROD / ${selectedProject?.slug || 'workspace'} / ${
          selectedIncident ? `INC-${selectedIncident.id.slice(0, 8)}` : 'No Incident Selected'
        }`;
      case 'approvals':
        return `${projectPrefix} / Human Approval Gate${isDemoMode ? ' [DEMO DATA]' : ''}`;
      case 'audit':
        return `SECURITY / Audit Ledger${isDemoMode ? ' [DEMO DATA]' : ''}`;
      case 'projects':
        return 'PLATFORM / Monitored Projects';
      case 'settings':
        return 'SETTINGS / Diagnostics & Engine Health';
      case 'signin':
        return 'SECURITY / Authentication';
      default:
        return 'DEVDOC / Autonomous DevOps';
    }
  };

  const getIncidentTitle = () => {
    switch (activeRoute) {
      case 'investigations':
        if (isDemoMode) {
          return '[DEMO DATA — NOT A LIVE INCIDENT] Checkout API 5xx spike';
        }
        return selectedIncident ? selectedIncident.title : 'Investigation Console — No Incident Selected';
      case 'overview':
        return 'Operations Intelligence Deck';
      case 'incidents':
        return 'Active Incidents Queue';
      case 'approvals':
        return 'Candidate Patch Verification Gate';
      case 'audit':
        return 'Audit Ledger & Governance Trail';
      case 'projects':
        return selectedProject ? `Active Project: ${selectedProject.name}` : 'Monitored Workspaces & Repositories';
      case 'settings':
        return 'Diagnostics Engine & Sandbox Isolation';
      case 'signin':
        return 'Access Authorization';
      default:
        return 'DEVDOC Orchestrator';
    }
  };

  const renderCurrentView = () => {
    switch (activeRoute) {
      case 'overview':
        return (
          <OverviewView
            onNavigate={(route) => setActiveRoute(route as NavRoute)}
            onSelectIncident={handleSelectIncident}
          />
        );
      case 'incidents':
        return <IncidentsView onSelectIncident={handleSelectIncident} />;
      case 'investigations':
        return <InvestigationConsoleView onNavigate={(route) => setActiveRoute(route as NavRoute)} />;
      case 'approvals':
        return <ApprovalsView />;
      case 'audit':
        return <AuditView />;
      case 'projects':
        return <ProjectsView onNavigate={(route) => setActiveRoute(route as NavRoute)} />;
      case 'settings':
        return <SettingsView />;
      case 'signin':
        return <SignInView onSuccess={() => setActiveRoute('projects')} />;
      default:
        return <NotFoundView onNavigate={(route) => setActiveRoute(route as NavRoute)} />;
    }
  };

  return (
    <AppShell
      activeRoute={activeRoute}
      onRouteChange={setActiveRoute}
      breadcrumb={getBreadcrumb()}
      incidentTitle={getIncidentTitle()}
    >
      {renderCurrentView()}
    </AppShell>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <ProjectProvider>
        <IncidentProvider>
          <AppContent />
        </IncidentProvider>
      </ProjectProvider>
    </AuthProvider>
  );
};

export default App;
