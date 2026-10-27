import React, { memo } from "react";

export const DotField: React.FC = memo(() => {
  // 18 columns with 24 dots each for desktop background matrix
  const cols = Array.from({ length: 18 });
  const dots = Array.from({ length: 24 });

  return (
    <div className="dotfield-canvas" aria-hidden="true">
      {cols.map((_, colIdx) => (
        <div key={colIdx} className="dotfield-col">
          {dots.map((_, dotIdx) => (
            <span key={dotIdx} />
          ))}
        </div>
      ))}
    </div>
  );
});

DotField.displayName = "DotField";
