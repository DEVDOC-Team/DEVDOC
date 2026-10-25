import React, { useState } from "react";
import {
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Database,
  FileCheck2,
  FileText,
  GitCommit,
  Lock,
  Rocket,
  Route,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { CodeDiff } from "../components/ui/CodeDiff";
import { Panel } from "../components/ui/Panel";
import { PhaseRail } from "../components/ui/PhaseRail";
import "./views.css";

interface EvidenceData {
  id: string;
  icon: React.ReactNode;
  desc: string;
  meta: string;
  detailTag: string;
  detailTimestamp: string;
  detailCode: Array<{ type?: "add" | "del" | "err" | "dim" | "normal"; text: string }>;
  detailNote: React.ReactNode;
  isMetricChart?: boolean;
}

export const InvestigationConsoleView: React.FC = () => {
  const [selectedEvidence, setSelectedEvidence] = useState<string>("E-01");
  const [showApprovalModal, setShowApprovalModal] = useState<boolean>(false);
  const [approvalDecision, setApprovalDecision] = useState<"pending" | "approved" | "rejected">("pending");

  const evidenceItems: EvidenceData[] = [
    {
      id: "E-01",
      icon: <FileText size={15} />,
      desc: 'HikariCP connection-timeout burst, api-gateway',
      meta: "14:02:11Z · 214 events · all pods",
      detailTag: "LOG · api-gateway · pod 7f4c9d",
      detailTimestamp: "14:02:11.412Z",
      detailCode: [
        { type: "normal", text: '14:02:08.412Z ERROR [api-gateway] hikari pool "checkout-pool"' },
        { type: "err", text: "  stats: active=214 idle=0 waiting=37 max=200" },
        { type: "err", text: '  SQLState=HYT0 msg="Connection is not available,' },
        { type: "err", text: '  request timed out after 30000ms."' },
      ],
      detailNote: (
        <span>
          First of <b>214 identical timeout events</b> in the 13:58–14:07 window. Errors are cluster-wide across all 4 pods, ruling out a single bad replica.
        </span>
      ),
    },
    {
      id: "E-02",
      icon: <TrendingUp size={15} />,
      desc: "db_connections climbs 74 → 214 after deploy",
      meta: "13:58–14:02Z · 5 samples · 15s step",
      detailTag: "METRIC · db_connections",
      detailTimestamp: "checkout-pool · 15s step",
      isMetricChart: true,
      detailCode: [],
      detailNote: (
        <span>
          74 → 96 → 138 → 181 → <b>214 connections</b> over four minutes. Slope begins at <b>13:58:04Z</b>, matching deploy v2.14.0 to the second.
        </span>
      ),
    },
    {
      id: "E-03",
      icon: <GitCommit size={15} />,
      desc: "a91f3c2 adds retry loop to PaymentClient",
      meta: "PR #482 · d.lindqvist · +18 −4",
      detailTag: "COMMIT · a91f3c2",
      detailTimestamp: "payments-service · PR #482",
      detailCode: [
        { type: "dim", text: 'PaymentClient.java · "Add retry with backoff"' },
        { type: "dim", text: "author d.lindqvist · 2026-10-25 13:50Z · +18 −4" },
        { type: "normal", text: "" },
        { type: "normal", text: "  ChargeResult charge(Payment p) {" },
        { type: "del", text: "-   Connection c = pool.getConnection();" },
        { type: "add", text: "+   for (int attempt = 0; attempt < 3; attempt++) {" },
        { type: "err", text: "+     c = pool.getConnection();   // prior handle never released" },
        { type: "add", text: "+     try {" },
        { type: "add", text: "+       return gateway.send(p, c);" },
        { type: "add", text: "+     } catch (TransientException te) { backoff(attempt); }" },
      ],
      detailNote: (
        <span>
          Commit introduced an inner retry loop that acquires a fresh connection handle per attempt without releasing the previous connection, leaking up to 3 connections per transient error.
        </span>
      ),
    },
    {
      id: "E-04",
      icon: <Route size={15} />,
      desc: "Trace: hikari.acquire span never closes",
      meta: "trace 7c41d9 · span 12 of 22",
      detailTag: "TRACE · OpenTelemetry",
      detailTimestamp: "trace 7c41d9 · span 12/22",
      detailCode: [
        { type: "dim", text: "GET /api/v1/checkout/charge (504 Gateway Timeout)" },
        { type: "normal", text: "├─ gateway.auth (1.2ms) [200 OK]" },
        { type: "err", text: "├─ hikari.acquire (30,000ms TIMEOUT)" },
        { type: "err", text: "└─ thread.blocked: waiting for database connection" },
      ],
      detailNote: (
        <span>
          Distributed trace captures client thread blocked indefinitely inside <code>hikari.acquire</code> until downstream 30s timeout triggered HTTP 504.
        </span>
      ),
    },
    {
      id: "E-05",
      icon: <Rocket size={15} />,
      desc: "Deploy v2.14.0 → prod, 4 minutes before onset",
      meta: "13:58:04Z · rollout 4/4 pods",
      detailTag: "DEPLOY · payments-service",
      detailTimestamp: "13:58:04Z · prod-cluster",
      detailCode: [
        { type: "normal", text: "Rollout started: 13:57:12Z" },
        { type: "normal", text: "Image: registry.internal/payments:v2.14.0@sha256:d8a9..." },
        { type: "normal", text: "Pods updated: 4/4 pods healthy" },
        { type: "err", text: "Onset time: 14:02:11Z (4 min post-rollout)" },
      ],
      detailNote: (
        <span>
          Canary deployment bypassed due to urgent hotfix tag. 100% traffic exposed to leaky retry loop immediately upon rollout.
        </span>
      ),
    },
  ];

  const activeEvidence = evidenceItems.find((e) => e.id === selectedEvidence) || evidenceItems[0];

  return (
    <div className="investigation-console">
      {/* Investigation Pipeline Phase Rail */}
      <PhaseRail />

      {/* Incident Subheader Facts */}
      <div className="incident-header-banner" style={{ marginTop: "12px" }}>
        <div>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "10px",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--devdoc-fg-muted)",
            }}
          >
            PROD / checkout-api / INC-2291
          </span>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "18px",
              fontWeight: 600,
              color: "var(--devdoc-fg)",
              display: "flex",
              alignItems: "center",
              gap: "10px",
              marginTop: "2px",
            }}
          >
            <span>Checkout API 5xx spike</span>
            <Badge variant="sev2">SEV-2</Badge>
          </div>
        </div>

        <div className="incident-facts">
          <span>
            Declared <b>14:07:02Z</b>
          </span>
          <span>
            Duration <b>00:19:41</b>
          </span>
          <span>
            Severity <b>SEV-2</b>
          </span>
          <span>
            Error budget burn <b>6.2×</b>
          </span>
        </div>
      </div>

      {/* 3-Column Main Grid */}
      <div className="console-grid">
        {/* Left Column: Metadata & Evidence Ledger */}
        <div className="column-stack">
          {/* Investigation Metadata */}
          <Panel title="Investigation" meta="run-3f9c">
            <dl className="kv-list">
              <dt>Started</dt>
              <dd>14:11:32Z</dd>
              <dt>Duration</dt>
              <dd>12m 35s</dd>
              <dt>Orchestrator</dt>
              <dd>Autonomous v1.0</dd>
              <dt>Sources queried</dt>
              <dd>4 external</dd>
              <dt>Evidence artifacts</dt>
              <dd>5 verified</dd>
              <dt>Query window</dt>
              <dd>13:45–14:30Z</dd>
            </dl>
          </Panel>

          {/* Evidence Ledger Panel */}
          <Panel
            title="Evidence Ledger"
            meta={`${evidenceItems.length} items`}
            bodyClassName="p-0"
            footer={
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "8px 12px",
                  fontSize: "10px",
                  fontFamily: "var(--font-mono)",
                  color: "var(--devdoc-fg-muted)",
                  borderTop: "1px solid var(--devdoc-border)",
                }}
              >
                <span>Sources: GitHub, Logs, Datadog, Traces</span>
                <span>SHA-256 Verified</span>
              </div>
            }
          >
            <div>
              {evidenceItems.map((item) => (
                <button
                  key={item.id}
                  className={`evidence-item ${selectedEvidence === item.id ? "selected" : ""}`}
                  onClick={() => setSelectedEvidence(item.id)}
                >
                  <span className="evidence-id">{item.id}</span>
                  <span style={{ color: "var(--devdoc-fg-muted)" }}>{item.icon}</span>
                  <div className="evidence-text">
                    <span className="evidence-title">{item.desc}</span>
                    <span className="evidence-ref">{item.meta}</span>
                  </div>
                  <ArrowUpRight size={13} color="var(--devdoc-fg-muted)" />
                </button>
              ))}
            </div>
          </Panel>

          {/* Source Preview Drawer Panel */}
          <Panel title="Source Preview" meta={activeEvidence.id}>
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "10px",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                color: "var(--devdoc-accent)",
                marginBottom: "8px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <span>{activeEvidence.detailTag}</span>
              <span style={{ color: "var(--devdoc-fg-muted)" }}>{activeEvidence.detailTimestamp}</span>
            </div>

            {activeEvidence.isMetricChart ? (
              <div style={{ background: "var(--devdoc-canvas)", border: "1px solid var(--devdoc-border)", borderRadius: "var(--radius-sm)", padding: "10px" }}>
                <svg viewBox="0 0 300 74" style={{ width: "100%", height: "auto", display: "block" }}>
                  <line x1="8" y1="8" x2="292" y2="8" stroke="#f87171" strokeWidth="1" strokeDasharray="3 3" />
                  <text x="292" y="6" textAnchor="end" fontSize="7" fill="#f87171" fontFamily="ui-monospace, Menlo, monospace">
                    max 200
                  </text>
                  <rect x="14" y="45" width="42" height="20" fill="#38bdf8" />
                  <rect x="72" y="38" width="42" height="27" fill="#38bdf8" />
                  <rect x="130" y="26" width="42" height="39" fill="#f5a524" />
                  <rect x="188" y="14" width="42" height="51" fill="#f5a524" />
                  <rect x="246" y="3" width="42" height="62" fill="#f87171" />
                  <text x="35" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    13:58
                  </text>
                  <text x="93" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    13:59
                  </text>
                  <text x="151" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:00
                  </text>
                  <text x="209" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:01
                  </text>
                  <text x="267" y="72" textAnchor="middle" fontSize="7" fill="#93a1b8" fontFamily="ui-monospace, Menlo, monospace">
                    14:02
                  </text>
                </svg>
              </div>
            ) : (
              <CodeDiff lines={activeEvidence.detailCode} />
            )}

            <div style={{ fontSize: "11px", color: "var(--devdoc-fg-muted)", marginTop: "8px", lineHeight: 1.5 }}>
              {activeEvidence.detailNote}
            </div>
          </Panel>
        </div>

        {/* Center Column: RCA Diagnosis, Causal Chain, Fix Proposal */}
        <div className="column-stack">
          <Panel
            title={
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span>Root Cause Analysis</span>
                <Badge variant="ok">94% Confidence</Badge>
              </div>
            }
            meta="EMITTED AT 14:15:02Z"
            bodyClassName="p-0"
          >
            <div className="claim-title">
              Database connection pool exhaustion caused by <em>unreleased handles</em> in retry loop inside PaymentClient.java
            </div>

            <div className="claim-desc">
              Commit <b>a91f3c2</b> introduced an inner retry loop around <code>pool.getConnection()</code> without releasing previous connection handles before initiating subsequent attempts. Under transient downstream gateway throttling, each client request consumed 3 concurrent connections, saturating the 200-handle pool in 240 seconds.
            </div>

            {/* Causal Chain Sequence */}
            <div style={{ borderTop: "1px solid var(--devdoc-border)", padding: "12px 18px 4px" }}>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "10px",
                  fontWeight: 600,
                  letterSpacing: "0.14em",
                  textTransform: "uppercase",
                  color: "var(--devdoc-fg-muted)",
                  marginBottom: "12px",
                }}
              >
                Causal Sequence Chain
              </div>

              <ol className="causal-chain">
                <li className="chain-item">
                  <span className="step-num">01</span>
                  <div className="chain-body">
                    Deploy <b>v2.14.0</b> rolls out to production pods at 13:58:04Z introducing new retry logic.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-05 Deploy</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">02</span>
                  <div className="chain-body">
                    Upstream banking provider returns transient HTTP 429 rate limit errors to PaymentClient.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-01 Logs</span>
                      <span className="evidence-chip">E-04 Trace</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">03</span>
                  <div className="chain-body">
                    PaymentClient retries 3x, acquiring new Hikari handles while holding prior unclosed connections.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-03 Commit</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">04</span>
                  <div className="chain-body">
                    HikariCP connection pool reaches max capacity (200/200) within 4 minutes.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-02 Metric</span>
                    </div>
                  </div>
                </li>

                <li className="chain-item">
                  <span className="step-num">05</span>
                  <div className="chain-body">
                    Incoming checkout requests block on connection acquisition until 30s timeout causes cluster-wide 5xx cascade.
                    <div className="evidence-chips">
                      <span className="evidence-chip">E-01 Error</span>
                    </div>
                  </div>
                </li>
              </ol>
            </div>

            {/* Excluded Non-Causes */}
            <div style={{ borderTop: "1px solid var(--devdoc-border)", padding: "10px 18px 12px", background: "rgba(0,0,0,0.15)" }}>
              <div style={{ fontSize: "11px", color: "var(--devdoc-fg-muted)", display: "flex", alignItems: "center", gap: "6px" }}>
                <CheckCircle2 size={13} color="var(--devdoc-status-ok)" />
                <span><b>Excluded:</b> Postgres CPU saturation ruled out (hovered at 28% throughout onset).</span>
              </div>
            </div>

            {/* Proposed Code Fix */}
            <div className="proposal-box">
              <div className="proposal-heading">
                <FileCheck2 size={16} color="var(--devdoc-status-ok)" />
                <span>Proposed Candidate Remediation · PaymentClient.java</span>
              </div>

              <CodeDiff
                lines={[
                  { type: "dim", text: "--- a/services/payment/PaymentClient.java" },
                  { type: "dim", text: "+++ b/services/payment/PaymentClient.java" },
                  { type: "normal", text: "   for (int attempt = 0; attempt < 3; attempt++) {" },
                  { type: "del", text: "-    Connection c = pool.getConnection();" },
                  { type: "del", text: "-    try { return gateway.send(p, c); }" },
                  { type: "add", text: "+    try (Connection c = pool.getConnection()) {" },
                  { type: "add", text: "+      return gateway.send(p, c);" },
                  { type: "add", text: "+    } catch (TransientException te) {" },
                  { type: "add", text: "+      logger.warn(\"Retrying payment attempt={}\", attempt);" },
                  { type: "add", text: "+      backoff(attempt);" },
                  { type: "add", text: "+    }" },
                ]}
              />

              <div style={{ display: "flex", gap: "16px", marginTop: "10px", fontSize: "11px", color: "var(--devdoc-fg-muted)" }}>
                <span>Sandbox Verification: <b style={{ color: "var(--devdoc-status-ok)" }}>PASSED (Docker)</b></span>
                <span>Regression Tests: <b style={{ color: "var(--devdoc-status-ok)" }}>482/482 Passed</b></span>
                <span>Rollback Step: <b>git revert a91f3c2</b></span>
              </div>
            </div>

            {/* Action Bar */}
            <div className="action-strip">
              <div style={{ fontSize: "11px", color: "var(--devdoc-fg-muted)" }}>
                <span style={{ color: "var(--devdoc-accent-amber)", fontWeight: 600 }}>Governed Gate:</span>{" "}
                Human approval required before any branch creation or patch submission.
              </div>

              {approvalDecision === "approved" ? (
                <Badge variant="ok">✓ Approved by m.okafor</Badge>
              ) : approvalDecision === "rejected" ? (
                <Badge variant="sev1">✕ Rejected</Badge>
              ) : (
                <Button variant="primary" onClick={() => setShowApprovalModal(true)}>
                  Review & Approve Candidate Fix
                </Button>
              )}
            </div>
          </Panel>
        </div>

        {/* Right Column: Telemetry & Verification Checklist */}
        <div className="column-stack">
          {/* Live Telemetry Meter */}
          <Panel title="Real-Time Telemetry" meta="METRICS PROXY">
            <div className="telemetry-row">
              <div className="telemetry-label">
                <ShieldAlert size={14} color="var(--devdoc-status-bad)" />
                <span>checkout_5xx_rate</span>
              </div>
              <div className="telemetry-val" style={{ color: "var(--devdoc-status-bad)" }}>
                8.4% <small style={{ fontSize: "10px", color: "var(--devdoc-fg-muted)" }}>+8.38%</small>
              </div>
            </div>

            <div className="telemetry-row">
              <div className="telemetry-label">
                <Database size={14} color="var(--devdoc-accent-amber)" />
                <span>hikari_active_conn</span>
              </div>
              <div className="telemetry-val" style={{ color: "var(--devdoc-accent-amber)" }}>
                214 <small style={{ fontSize: "10px", color: "var(--devdoc-fg-muted)" }}>/ 200</small>
              </div>
            </div>

            <div className="telemetry-row">
              <div className="telemetry-label">
                <Clock size={14} color="var(--devdoc-fg-muted)" />
                <span>p95_latency</span>
              </div>
              <div className="telemetry-val">
                3,420ms <small style={{ fontSize: "10px", color: "var(--devdoc-fg-muted)" }}>p95</small>
              </div>
            </div>

            <div style={{ padding: "10px 12px 6px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "10px", fontFamily: "var(--font-mono)", color: "var(--devdoc-fg-muted)", marginBottom: "4px" }}>
                <span>Error Rate Trend (15m window)</span>
                <span style={{ color: "var(--devdoc-status-bad)" }}>PEAK 14:05Z</span>
              </div>
              <svg viewBox="0 0 100 24" style={{ width: "100%", height: "28px" }}>
                <path d="M 0 22 L 20 22 L 35 22 L 45 20 L 55 6 L 65 4 L 75 7 L 85 5 L 100 6" fill="none" stroke="var(--devdoc-status-bad)" strokeWidth="1.5" />
              </svg>
            </div>
          </Panel>

          {/* Verification Gates Checklist */}
          <Panel title="Verification Gates" meta="4 CHECKS">
            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: "2px", flexShrink: 0 }} />
              <div>
                <div className="gate-text">Isolated Sandbox Execution</div>
                <div className="gate-sub">Docker --network none · Pinned Alpine</div>
              </div>
            </div>

            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: "2px", flexShrink: 0 }} />
              <div>
                <div className="gate-text">Regression Test Suite</div>
                <div className="gate-sub">482 passed · 0 failures in 105s</div>
              </div>
            </div>

            <div className="gate-item">
              <CheckCircle2 size={16} color="var(--devdoc-status-ok)" style={{ marginTop: "2px", flexShrink: 0 }} />
              <div>
                <div className="gate-text">Threat & Boundary Scan</div>
                <div className="gate-sub">SSRF check · Secret scrubbing active</div>
              </div>
            </div>

            <div className="gate-item">
              <Lock size={16} color="var(--devdoc-accent-amber)" style={{ marginTop: "2px", flexShrink: 0 }} />
              <div>
                <div className="gate-text">Authorized Human Approval</div>
                <div className="gate-sub">Required prior to PR branch creation</div>
              </div>
            </div>
          </Panel>
        </div>
      </div>

      {/* Human Approval Gate Modal */}
      {showApprovalModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(10, 16, 32, 0.8)",
            backdropFilter: "blur(6px)",
            display: "grid",
            placeItems: "center",
            zIndex: 100,
            padding: "16px",
          }}
          role="dialog"
          aria-modal="true"
          aria-labelledby="approval-title"
        >
          <div
            style={{
              background: "var(--devdoc-surface)",
              border: "1px solid var(--devdoc-border)",
              borderRadius: "var(--radius-lg)",
              maxWidth: "520px",
              width: "100%",
              overflow: "hidden",
              boxShadow: "var(--shadow-md)",
            }}
          >
            <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--devdoc-border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span id="approval-title" style={{ fontFamily: "var(--font-display)", fontWeight: 600, fontSize: "14px", color: "var(--devdoc-fg)" }}>
                Human Approval Gate · INC-2291
              </span>
              <Badge variant="cyan">PROPOSAL STAGE</Badge>
            </div>

            <div style={{ padding: "18px 20px" }}>
              <p style={{ fontSize: "13px", lineHeight: 1.6, color: "var(--devdoc-fg-muted)", marginBottom: "14px" }}>
                You are about to authorize fix proposal <b>FP-01</b> for incident <b>INC-2291</b>. This action will record an immutable cryptographic audit record signed with your identity.
              </p>

              <div style={{ background: "var(--devdoc-surface-sunken)", border: "1px solid var(--devdoc-border)", borderRadius: "var(--radius-sm)", padding: "10px 14px", marginBottom: "16px", fontSize: "11px", fontFamily: "var(--font-mono)" }}>
                <div>Actor: m.okafor@team.internal</div>
                <div>Role: SRE Incident Commander</div>
                <div>Artifact Fingerprint: sha256:7f81c9e2b04a91f3...</div>
                <div>Target File: services/payment/PaymentClient.java</div>
              </div>

              <div style={{ fontSize: "11px", color: "var(--devdoc-status-warn)", marginBottom: "18px" }}>
                ⚠️ Notice: In accordance with safety policies, DEVDOC will stage the verified commit into a review branch. Automated deployment to production remains disabled.
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px" }}>
                <Button variant="ghost" onClick={() => setShowApprovalModal(false)}>
                  Cancel
                </Button>
                <Button
                  variant="danger"
                  onClick={() => {
                    setApprovalDecision("rejected");
                    setShowApprovalModal(false);
                  }}
                >
                  Reject Fix
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    setApprovalDecision("approved");
                    setShowApprovalModal(false);
                  }}
                >
                  Confirm & Authorize
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
