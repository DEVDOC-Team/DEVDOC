import React, { useState } from 'react';
import { Sidebar, type NavRoute } from './Sidebar';
import { TopBar } from './TopBar';
import { AuditFooter } from './AuditFooter';
import { DotField } from '../ui/DotField';
import './layout.css';

export interface AppShellProps {
  children: React.ReactNode;
  activeRoute: NavRoute;
  onRouteChange: (route: NavRoute) => void;
  breadcrumb?: string;
  incidentTitle?: string;
}

export const AppShell: React.FC<AppShellProps> = ({
  children,
  activeRoute,
  onRouteChange,
  breadcrumb,
  incidentTitle,
}) => {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="app-shell app-container">
      {/* Background Dot Matrix Pattern */}
      <DotField />

      {/* Main Navigation Sidebar */}
      <Sidebar
        activeRoute={activeRoute}
        onRouteChange={onRouteChange}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />

      {/* Primary Layout Column */}
      <div className="app-main-wrap app-main">
        <TopBar
          onNavigateSignIn={() => onRouteChange('signin')}
          breadcrumb={breadcrumb}
          incidentTitle={incidentTitle}
        />

        <main id="main-content" className="app-main-content page-container" tabIndex={-1}>
          {children}
        </main>

        <AuditFooter />
      </div>
    </div>
  );
};
