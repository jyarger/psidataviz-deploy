import { useEffect, useRef, useState } from "react";

// A micrograph with wheel-zoom, drag-pan, and double-click reset.
export function ZoomableImage({ src, alt }: { src: string; alt: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [t, setT] = useState({ s: 1, x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);

  // attach the wheel listener natively (non-passive) so preventDefault stops the page from scrolling
  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
      setT((p) => {
        const s = Math.min(10, Math.max(1, p.s * factor));
        return s === 1 ? { s: 1, x: 0, y: 0 } : { ...p, s };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  function onDown(e: React.MouseEvent) {
    if (t.s <= 1) return;
    drag.current = { x: e.clientX - t.x, y: e.clientY - t.y };
  }
  function onMove(e: React.MouseEvent) {
    if (drag.current) setT((p) => ({ ...p, x: e.clientX - drag.current!.x, y: e.clientY - drag.current!.y }));
  }
  const stop = () => (drag.current = null);
  const reset = () => setT({ s: 1, x: 0, y: 0 });

  return (
    <div
      ref={wrap}
      className="zoom-wrap"
      onMouseDown={onDown}
      onMouseMove={onMove}
      onMouseUp={stop}
      onMouseLeave={stop}
      onDoubleClick={reset}
      title="Scroll to zoom, drag to pan, double-click to reset"
    >
      <img
        src={src}
        alt={alt}
        draggable={false}
        style={{
          transform: `translate(${t.x}px, ${t.y}px) scale(${t.s})`,
          cursor: t.s > 1 ? (drag.current ? "grabbing" : "grab") : "zoom-in",
        }}
      />
      {t.s > 1 && (
        <button className="zoom-reset" onClick={reset}>
          {t.s.toFixed(1)}× · reset
        </button>
      )}
    </div>
  );
}
