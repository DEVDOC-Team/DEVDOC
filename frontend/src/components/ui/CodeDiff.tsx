import React from "react";

export interface CodeDiffProps {
  lines: Array<{
    type?: "add" | "del" | "err" | "dim" | "normal";
    text: string;
  }>;
  className?: string;
}

export const CodeDiff: React.FC<CodeDiffProps> = ({ lines, className = "" }) => {
  return (
    <pre
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: "11px",
        lineHeight: "1.7",
        background: "var(--devdoc-canvas)",
        border: "1px solid var(--devdoc-border)",
        borderRadius: "var(--radius-sm)",
        padding: "10px 14px",
        overflowX: "auto",
        color: "#c7d2e4",
        whiteSpace: "pre",
      }}
      className={className}
    >
      {lines.map((l, idx) => {
        let color = "inherit";
        if (l.type === "add") color = "var(--devdoc-status-ok)";
        if (l.type === "del" || l.type === "err") color = "var(--devdoc-status-bad)";
        if (l.type === "dim") color = "var(--devdoc-fg-subtle)";

        return (
          <div key={idx} style={{ color }}>
            {l.text}
          </div>
        );
      })}
    </pre>
  );
};
