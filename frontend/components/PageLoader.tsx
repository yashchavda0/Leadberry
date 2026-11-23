"use client";

import { useEffect, useState } from "react";

// Simulated progress that eases toward 92% and holds until the page is ready.
export default function PageLoader({ label = "Loading" }: { label?: string }) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setValue(92);
      return;
    }
    const start = performance.now();
    const duration = 4000;
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      setValue(92 * (1 - Math.pow(1 - t, 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  return <div className="pl-root" role="status" aria-live="polite" aria-label={label}>
    <div className="pl-box">
      <div className="pl-head">
        <span className="pl-label">{label}</span>
        <span className="pl-percent">{Math.round(value)}%</span>
      </div>
      <div className="pl-track" aria-hidden="true">
        <span className="pl-bar" style={{ width: `${value}%` }} />
      </div>
    </div>
  </div>;
}
