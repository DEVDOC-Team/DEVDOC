import React, { useState } from 'react';
import { AppShell } from './components/layout/AppShell';
import type { NavRoute } from './components/layout/Sidebar';
import { OverviewView } from './views/OverviewView';
import { IncidentsView } from './views/IncidentsView';
import { InvestigationConsoleView } from './views/InvestigationConsoleView';
import { ApprovalsView } from './views/ApprovalsView';
import { AuditView } from './views/AuditView';
import { ProjectsView } from './views/ProjectsView';
import { SettingsView } from './views/SettingsView';
import { NotFoundView } from './views/NotFoundView';

export const App: React.FC = () => {
  const [activeRoute, setActiveRoute] = useState<NavRoute>('investigations');
  const [selectedIncidentId, setSelectedIncidentId] = useState<string>('INC-2291');

  const handleSelectIncident = (id: string) => {
    setSelectedIncidentId(id);
    setActiveRoute('investigations');
  };

  const getBreadcrumb = () => {
    switch (activeRoute) {
      case 'overview':
        return 'DEVDOC / Operations Deck';
      case 'incidents':
        return 'DEVDOC / Incidents Queue';
      case 'investigations':
        return `PROD / checkout-api / ${selectedIncidentId}`;
      case 'approvals':
        return 'DEVDOC / Human Approval Gate';
      case 'audit':
        return 'SECURITY / Cryptographic Audit';
      case 'projects':
        return 'PLATFORM / Monitored Projects';
      case 'settings':
        return 'SETTINGS / Diagnostics & Engine Health';
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
        return 'Monitored Codebases & Repositories';
      case 'settings':
        return 'Diagnostics Engine & Sandbox Isolation';
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

export default App;
