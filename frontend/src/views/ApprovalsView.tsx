import React, { useState } from "react";
import { CheckCircle2, FileCheck2, Lock, XCircle } from "lucide-react";
import { Button } from "../components/ui/Button";
import { Panel } from "../components/ui/Panel";
import "./views.css";

export const ApprovalsView: React.FC = () => {
  const [decisions, setDecisions] = useState<Record<string, "approved" | "rejected">>({});

  const pendingApprovals = [
    {
      id: "APPR-01",
      incidentId: "INC-2291",
      proposalId: "FP-01",
      title: "PaymentClient connection leak remediation",
      author: "DEVDOC Orchestrator (NVIDIA Nemotron)",
      targetFile: "services/payment/PaymentClient.java",
      fingerprint: "sha256:7f81c9e2b04a91f3c8e4d2a1b9f7...",
      sandboxResult: "PASSED (Docker Alpine Isolated)",
      regressionResult: "482 passed / 0 failed",
      created: "14:16:30Z",
    },
  ];

  const handleDecision = (id: string, decision: "approved" | "rejected") => {
    setDecisions((prev) => ({ ...prev, [id]: decision }));
  };

  return (
    <div className="approvals-view">
      <div style={{ marginBottom: "16px" }}>
        <h1 style={{ fontFamily: "var(--font-display)", fontSize: "20px", fontWeight: 700, color: "var(--devdoc-fg)" }}>
          Human Approval Gate
        </h1>
        <p style={{ fontSize: "12px", color: "var(--devdoc-fg-muted)", marginTop: "2px" }}>
          Autonomous fix proposals requiring verified cryptographic signature and human authorization before staging.
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
        {pendingApprovals.map((appr) => {
          const decision = decisions[appr.id];

          return (
            <Panel
              key={appr.id}
              title={
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <FileCheck2 size={16} color="var(--devdoc-accent)" />
                  <span>{appr.id} · {appr.title}</span>
                </div>
              }
              meta={`INCIDENT ${appr.incidentId}`}
            >
              <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 300px)", gap: "20px" }}>
                <div>
                  <div style={{ fontSize: "13px", lineHeight: 1.5, color: "var(--devdoc-fg)", marginBottom: "10px" }}>
                    Candidate patch verified in Docker sandbox. Encapsulates <code>pool.getConnection()</code> inside try-with-resources to ensure deterministic release upon exception or loop termination.
                  </div>

                  <dl className="kv-list" style={{ maxWidth: "480px" }}>
                    <dt>Target File</dt>
                    <dd>{appr.targetFile}</dd>
                    <dt>Proposal Generator</dt>
                    <dd>{appr.author}</dd>
                    <dt>Sandbox Execution</dt>
                    <dd style={{ color: "var(--devdoc-status-ok)" }}>{appr.sandboxResult}</dd>
                    <dt>Regression Suite</dt>
                    <dd style={{ color: "var(--devdoc-status-ok)" }}>{appr.regressionResult}</dd>
                    <dt>Artifact Hash</dt>
                    <dd style={{ color: "var(--devdoc-accent)" }}>{appr.fingerprint}</dd>
                  </dl>
                </div>

                <div style={{ background: "var(--devdoc-surface-sunken)", border: "1px solid var(--devdoc-border)", borderRadius: "var(--radius-sm)", padding: "14px", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
                  <div>
                    <div style={{ fontSize: "11px", fontWeight: 600, color: "var(--devdoc-accent-amber)", display: "flex", alignItems: "center", gap: "6px", marginBottom: "6px" }}>
                      <Lock size={14} />
                      <span>AUTHORIZATION REQUIRED</span>
                    </div>
                    <p style={{ fontSize: "11px", color: "var(--devdoc-fg-muted)", lineHeight: 1.5 }}>
                      Approval signs and records an immutable audit trail entry. Does not auto-deploy to production.
                    </p>
                  </div>

                  <div style={{ marginTop: "16px" }}>
                    {decision === "approved" ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--devdoc-status-ok)", fontSize: "12px", fontWeight: 600 }}>
                        <CheckCircle2 size={16} />
                        <span>Authorized by m.okafor (Recorded in Audit Log)</span>
                      </div>
                    ) : decision === "rejected" ? (
                      <div style={{ display: "flex", alignItems: "center", gap: "6px", color: "var(--devdoc-status-bad)", fontSize: "12px", fontWeight: 600 }}>
                        <XCircle size={16} />
                        <span>Proposal Rejected & Stored</span>
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "8px" }}>
                        <Button variant="danger" size="sm" onClick={() => handleDecision(appr.id, "rejected")}>
                          Reject
                        </Button>
                        <Button variant="primary" size="sm" onClick={() => handleDecision(appr.id, "approved")}>
                          Authorize Fix
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </Panel>
          );
        })}
      </div>
    </div>
  );
};
