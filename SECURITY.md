# DEVDOC Security Notes

## Trust boundaries

The supported flow is authenticated user → FastAPI authentication and project authorization → database/RLS → investigation services → evidence and external-provider data → RCA → inert fix proposal → opt-in sandbox verification → fingerprint-bound human approval. Approval does not execute a fix. Production remediation is not implemented.

Trusted inputs are server policy, the authenticated principal, database authorization, and server configuration. User incident text, repository files, GitHub issues and pull requests, logs, monitoring data, search results, web pages, and model output are untrusted data. They must not grant authority, change policy, approve work, or become executable commands.

## Phase 19 audit and mitigation

The Phase 1–18 audit confirmed two medium-severity database authorization gaps:

1. The authenticated Supabase role could insert audit events for an accessible project, allowing fabricated history.
2. The authenticated role could create pending approval rows and move them to terminal states without the service's passing-verification eligibility checks.

Migration `0008_restrict_client_approval_audit_writes` removes the authenticated role's INSERT policy on `audit_logs` and INSERT/UPDATE policies on `approvals`. Project-scoped SELECT policies remain. Approval lifecycle events continue to be emitted by the database trigger for trusted server-side lifecycle writes. Apply migrations through the latest revision before relying on this control. Rolling back this migration restores the weaker client-write policies.

The focused PostgreSQL tests verify that authenticated users retain scoped approval/audit reads, cannot directly create or decide approvals, cannot forge audit events, and cannot update/delete audit history. They require an isolated test database and are skipped when PostgreSQL is unavailable.

## Threat model

| Asset | Threat / attack surface | Mitigation in this repository | Test / verification |
|---|---|---|---|
| User identity and project data | Unauthenticated or cross-project user calls protected APIs or reads rows | Supabase JWT validation, active-user/project dependencies, project-scoped RLS policies | `test_auth_phase5.py`, `test_rls_security.py`, API phase tests |
| Approval records and verification bindings | Client fabricates, decides, replays, or changes an approval | Server-side eligibility checks, project/investigation scoping, fingerprints, expiry/terminal-state checks, lifecycle trigger; authenticated direct writes removed in migration 0008 | `test_phase18_approvals.py`; live RLS tests in `test_rls_security.py` |
| Audit events | Authenticated client forges events or alters/deletes history | Direct client INSERT policy removed; update/delete immutability trigger; database-generated approval lifecycle audit | `test_rls_security.py` |
| Repository, log, incident, and evidence content | Malicious content attempts to become trusted prompt instructions or commands | Treat these sources as untrusted data; proposal generation is distinct from configured sandbox argv; approval remains human-only | Existing orchestrator, evidence, fix, sandbox, and approval tests |
| GitHub, Nebius, and Tavily credentials | Client exposure, response/log leakage, or untrusted provider content | Server-side settings and provider boundaries; optional integrations are not called by normal tests | Configuration and provider fake-based tests; secret-file contents were not inspected |
| Sandbox host and production environment | Generated proposal attempts host access or production execution | Docker provider's isolated configuration and bounded execution; no production remediation layer exists | Fake-provider and Docker-agent tests; Docker runtime isolation is not certified by this security change |

Relevant adversaries include unauthenticated attackers, authenticated malicious users, cross-project users, compromised repositories or issue authors, malicious web content, prompt-injection attempts, compromised providers, and malicious model output.

## Deployment requirements and limitations

- Keep `.env` out of version control; use server-side secret injection. `.env.example` is a template, not a source of credentials.
- Configure production `TRUSTED_HOSTS`, explicit CORS origins, HTTPS termination, provider credentials/endpoints, and database connectivity from trusted deployment configuration. Do not treat forwarded headers as trustworthy unless the reverse proxy is configured and controlled.
- Apply all database migrations. Use an application database identity that is not exposed to clients; ensure its RLS behavior is understood for the deployment. Database owners and roles with `BYPASSRLS` can bypass ordinary RLS policies.
- The PostgreSQL RLS tests are opt-in integration tests. A skipped test is not evidence of a live database policy pass.
- This change hardens the confirmed approval/audit direct-write gaps. It is not a certification of every deployment, provider, Docker host, network egress route, or historical migration state. Review these boundaries before production deployment.
