import React, { memo, useEffect, useRef } from "react";

export const DotField: React.FC = memo(() => {
  // A dense, evenly spaced dot matrix for the background.
  const cols = Array.from({ length: 36 });
  const dots = Array.from({ length: 48 });
  const canvasRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    let centers: Array<{ element: HTMLSpanElement; x: number; y: number }> = [];
    let animationFrame = 0;
    let pointer = { x: -10000, y: -10000 };
    const lensRadius = 110;

    const measureDots = () => {
      centers = Array.from(canvas.querySelectorAll<HTMLSpanElement>(".dotfield-col span")).map((element) => {
        const rect = element.getBoundingClientRect();
        return { element, x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
      });
    };

    const updateFisheye = () => {
      animationFrame = 0;

      for (const dot of centers) {
        const distance = Math.hypot(pointer.x - dot.x, pointer.y - dot.y);
        if (distance < lensRadius) {
          const strength = 1 - distance / lensRadius;
          const scale = 1 + 0.28 * strength * strength;
          dot.element.style.transform = `scale(${scale.toFixed(3)})`;
          dot.element.classList.add("is-fisheye-active");
        } else if (dot.element.classList.contains("is-fisheye-active")) {
          dot.element.style.transform = "";
          dot.element.classList.remove("is-fisheye-active");
        }
      }
    };

    const handlePointerMove = (event: PointerEvent) => {
      pointer = { x: event.clientX, y: event.clientY };
      if (!animationFrame) animationFrame = window.requestAnimationFrame(updateFisheye);
    };

    const clearFisheye = () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      animationFrame = 0;
      pointer = { x: -10000, y: -10000 };
      centers.forEach(({ element }) => {
        element.style.transform = "";
        element.classList.remove("is-fisheye-active");
      });
    };

    const handlePointerOut = (event: PointerEvent) => {
      if (!event.relatedTarget) clearFisheye();
    };

    measureDots();
    window.addEventListener("resize", measureDots);
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("blur", clearFisheye);
    document.addEventListener("pointerout", handlePointerOut);

    return () => {
      window.removeEventListener("resize", measureDots);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("blur", clearFisheye);
      document.removeEventListener("pointerout", handlePointerOut);
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      clearFisheye();
    };
  }, []);

  return (
    <div ref={canvasRef} className="dotfield-canvas" aria-hidden="true">
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
