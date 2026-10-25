import React from "react";
import { ShieldCheck } from "lucide-react";
import "./layout.css";

export const AuditFooter: React.FC = () => {
  return (
    <footer className="app-footer" aria-label="Cryptographic audit metadata">
      <div className="footer-left">
        <ShieldCheck size={16} color="var(--devdoc-status-ok)" />
        <span>
          Verification Fingerprint:{" "}
          <span className="footer-hash">sha256:7f81c9e2b04a91f3...</span>
        </span>
        <span style={{ color: "var(--devdoc-border)" }}>|</span>
        <span>Signer: DEVDOC Orchestrator v0.1.0</span>
      </div>

      <div>
        <span style={{ color: "var(--devdoc-accent-amber)", fontWeight: 500 }}>
          Strict Policy: Zero Auto-Deploy (Human Approval Required)
        </span>
      </div>
    </footer>
  );
};
