import { describe, it, expect } from 'vitest';
// @ts-ignore
import fs from 'node:fs';
// @ts-ignore
import path from 'node:path';

describe('Layout Regression Suite: Side-by-Side Horizontal Layout', () => {
  // @ts-ignore
  const cwd = process.cwd();
  const layoutCssPath = path.resolve(cwd, 'src/components/layout/layout.css');
  const appShellPath = path.resolve(cwd, 'src/components/layout/AppShell.tsx');
  const appPath = path.resolve(cwd, 'src/App.tsx');
  const viewsCssPath = path.resolve(cwd, 'src/views/views.css');

  const layoutCss = fs.readFileSync(layoutCssPath, 'utf-8');
  const appShellCode = fs.readFileSync(appShellPath, 'utf-8');
  const appCode = fs.readFileSync(appPath, 'utf-8');
  const viewsCss = fs.readFileSync(viewsCssPath, 'utf-8');

  it('declares horizontal flex row on .app-shell and .app-container', () => {
    expect(layoutCss).toMatch(/\.app-shell[\s\S]*?display:\s*flex/);
    expect(layoutCss).toMatch(/flex-direction:\s*row/);
    expect(layoutCss).toMatch(/width:\s*100%/);
  });

  it('keeps .app-sidebar fixed on left with proper flex and sticky positioning', () => {
    expect(layoutCss).toMatch(/\.app-sidebar\s*\{[^}]*flex:\s*0\s+0\s+var\(--sidebar-width\)/);
    expect(layoutCss).toMatch(/\.app-sidebar\s*\{[^}]*position:\s*sticky/);
    expect(layoutCss).toMatch(/\.app-sidebar\s*\{[^}]*height:\s*100vh/);
  });

  it('ensures .app-main-wrap occupies remaining width with flex: 1 1 auto and min-width: 0', () => {
    expect(layoutCss).toMatch(/\.app-main-wrap[\s\S]*?flex:\s*1\s+1\s+auto/);
    expect(layoutCss).toMatch(/\.app-main-wrap[\s\S]*?min-width:\s*0/);
    expect(layoutCss).toMatch(/\.app-main-wrap[\s\S]*?width:\s*0/);
  });

  it('configures .app-main-content and .page-container to fill width without overflow', () => {
    expect(layoutCss).toMatch(/\.app-main-content[\s\S]*?max-width:\s*var\(--content-max-width\)/);
    expect(layoutCss).toMatch(/\.app-main-content[\s\S]*?width:\s*100%/);
  });

  it('AppShell renders sidebar and main-wrap as direct siblings in horizontal shell', () => {
    expect(appShellCode).toContain('className="app-shell app-container"');
    expect(appShellCode).toContain('<Sidebar');
    expect(appShellCode).toContain('className="app-main-wrap app-main"');
    expect(appShellCode).toContain('<main id="main-content" className="app-main-content page-container"');
  });

  it('App navigates across all core routes inside AppShell', () => {
    const requiredRoutes = [
      'overview',
      'incidents',
      'investigations',
      'approvals',
      'audit',
      'projects',
      'settings',
    ];

    for (const route of requiredRoutes) {
      expect(appCode).toContain(`case '${route}':`);
    }
  });

  it('includes responsive mobile collapse handling for narrow viewports', () => {
    expect(layoutCss).toContain('@media (max-width: 960px)');
    expect(layoutCss).toMatch(/position:\s*fixed/);
    expect(layoutCss).toMatch(/left:\s*-100%/);
  });

  it('views.css specifies full-width view containers and responsive console grid', () => {
    expect(viewsCss).toContain('.view-container');
    expect(viewsCss).toContain('.investigation-console');
    expect(viewsCss).toContain('@media (max-width: 1120px)');
  });
});
