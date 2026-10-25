import React, { useState } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ProjectProvider, useProjects } from './context/ProjectContext';
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
  const [activeRoute, setActiveRoute] = useState<NavRoute>('investigations');
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>('INC-2291');

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
          gap: '12px',
        }}
      >
        <StatusPulse status="accent" />
        <span style={{ fontFamily: 'var(--font-display)', fontSize: '12px', letterSpacing: '0.1em' }}>
          INITIALIZING DEVDOC SESSION...
        </span>
      </div>
    );
  }

  const handleSelectIncident = (id: string) => {
    setSelectedIncidentId(id);
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
        return `PROD / ${selectedProject?.slug || 'checkout-api'} / ${selectedIncidentId}`;
      case 'approvals':
        return `${projectPrefix} / Human Approval Gate`;
      case 'audit':
        return 'SECURITY / Cryptographic Audit';
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
        return 'Checkout API 5xx spike';
      case 'overview':
        return 'Operations Intelligence Deck';
      case 'incidents':
        return 'Active Incidents Queue';
      case 'approvals':
        return 'Candidate Patch Verification Gate';
      case 'audit':
        return 'SHA-256 Merkle Chain Audit';
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
        return <InvestigationConsoleView />;
      case 'approvals':
        return <ApprovalsView />;
      case 'audit':
        return <AuditView />;
      case 'projects':
        return <ProjectsView />;
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
        <AppContent />
      </ProjectProvider>
    </AuthProvider>
  );
};

export default App;
