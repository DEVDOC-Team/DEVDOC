# DEVDOC Frontend

The DEVDOC frontend is a browser-based React application for monitoring projects, reviewing incidents, running investigations, and managing approvals and audit records. It communicates with the FastAPI backend through a shared typed API client.

## Technology stack

| Area | Technology | Use |
| --- | --- | --- |
| UI | React 19 | Component-based user interface |
| Language | TypeScript 6 | Typed components, API contracts, and application state |
| Build and development server | Vite 8 | Local dev server, HMR, and production bundling |
| Icons | Lucide React | Navigation and interface icons |
| Styling | CSS | Design tokens, global styles, layout, view, and UI component styles |
| Typography | Source Sans 3 | Locally bundled variable regular and italic fonts |
| Tests | Vitest 5 | API client, endpoint, and application layout tests |
| Lint | Oxlint | JavaScript, TypeScript, and React linting |

The declared dependency versions and npm commands are in `package.json`; `package-lock.json` locks the install tree.

## Frontend structure

```text
frontend/
├── public/
│   ├── assets/                  # Public static images
│   ├── fonts/                   # Local Source Sans 3 fonts and OFL license
│   ├── favicon.svg
│   └── icons.svg
├── src/
│   ├── api/                     # Typed backend client, resource functions, and API types
│   │   └── __tests__/           # Vitest client, endpoint, and layout tests
│   ├── assets/                  # Assets imported by source modules
│   ├── components/
│   │   ├── layout/              # App shell, sidebar, top bar, and audit footer
│   │   └── ui/                  # Reusable buttons, panels, badges, status, and phase components
│   ├── context/                 # Authentication, project, and incident state providers
│   ├── styles/                  # Global CSS and design tokens
│   ├── views/                   # Screen-level views for each application section
│   ├── App.tsx                  # Context providers, view selection, and app-level state
│   ├── App.css
│   ├── index.css                # Global stylesheet entry point
│   └── main.tsx                 # React DOM entry point
├── .env.example                 # Frontend environment template
├── index.html                   # Vite HTML entry point
├── package.json                 # Scripts and dependencies
├── package-lock.json
├── tsconfig*.json                # TypeScript project configuration
└── vite.config.ts               # Vite and React plugin configuration
```

### Main source areas

- `src/views/` contains the Overview, Incidents, Investigation Console, Approvals, Audit, Projects, Settings, Sign In, and Not Found screens.
- `src/components/layout/` provides the persistent application shell and navigation.
- `src/components/ui/` contains shared UI primitives, including `Panel`, `Button`, `Badge`, `PhaseRail`, `StatusPulse`, and `DotField`.
- `src/context/` owns authentication, selected-project, incident, investigation, and approval state shared across views.
- `src/api/` contains `client.ts` plus resource modules for auth, projects, incidents, investigations, GitHub, and approvals. `types.ts` defines shared API contracts.
- `src/styles/tokens.css` defines color, typography, spacing, shadow, and layout tokens. `global.css`, `components/**.css`, and `views/views.css` apply the shared theme.

## Application structure and data flow

`src/main.tsx` mounts the React app. `src/App.tsx` wraps the interface in `AuthProvider`, `ProjectProvider`, and `IncidentProvider`, then renders the current view inside `AppShell`.

The app uses the `NavRoute` state in `App.tsx` to select views; it does not currently use a URL-based client router. Views read shared state from context and call resource functions from `src/api/`. Those functions use `apiClient` to send HTTP requests, attach the stored bearer token when available, apply request timeouts, and translate backend errors into `ApiError` values.

The API base URL is configured by `VITE_API_BASE_URL`. During development, the client defaults to `http://127.0.0.1:8000`. In production, an unset value uses the frontend's own origin, which works when a reverse proxy serves the frontend and FastAPI under one domain.

When frontend and backend are hosted separately, set `VITE_API_BASE_URL` to the HTTPS FastAPI URL that browsers can reach and rebuild the frontend. Do not use `localhost` for a shared deployment: each visitor's browser resolves it to that visitor's own computer. Set backend `CORS_ORIGINS` to the exact frontend origin, including its scheme and any non-default port. A loopback API URL used from a non-local browser now produces a configuration message instead of a generic fetch error. A user listed in Supabase Auth still needs the DEVDOC FastAPI backend to be reachable; the Supabase user list does not host this API.

## Local development

Run commands from the `frontend/` directory.

```powershell
npm ci
Copy-Item .env.example .env
npm run dev
```

Vite serves the app at `http://localhost:5173` by default. Start the FastAPI backend separately; for local development, use `VITE_API_BASE_URL=http://127.0.0.1:8000`. Restart Vite after changing `.env` so it picks up the new value.

The environment template also lists optional public Supabase URL and anon-key variables. Any `VITE_` value is included in the browser build and must be treated as public; do not put a service-role key or other private secret in the frontend environment.

## Available commands

```powershell
npm run dev       # Start the Vite development server
npm run build     # Type-check and create the production bundle in dist/
npm run preview   # Serve the production bundle locally
npm run lint      # Run Oxlint
npm run test      # Run Vitest
```

Vitest discovers the test files under `src/api/__tests__/`.

For backend architecture and API setup, see [`../backend/README.md`](../backend/README.md). For product-wide architecture, see [`../README.md`](../README.md).
