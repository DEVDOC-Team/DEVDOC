import React from "react";
import "./ui.css";

export interface PanelProps {
  title?: React.ReactNode;
  meta?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  footer?: React.ReactNode;
  sunken?: boolean;
  style?: React.CSSProperties;
}

export const Panel: React.FC<PanelProps> = ({
  title,
  meta,
  children,
  className = "",
  bodyClassName = "",
  footer,
  sunken = false,
  style,
}) => {
  const panelClasses = `panel ${sunken ? "panel-sunken" : ""} ${className}`.trim();

  return (
    <section className={panelClasses} style={style}>
      {(title || meta) && (
        <div className="panel-header">
          {title && <span className="panel-title">{title}</span>}
          {meta && <span className="panel-meta">{meta}</span>}
        </div>
      )}
      <div className={`panel-body ${bodyClassName}`.trim()}>{children}</div>
      {footer && <div className="panel-footer">{footer}</div>}
    </section>
  );
};
