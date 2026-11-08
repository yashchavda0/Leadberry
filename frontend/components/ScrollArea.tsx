"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

// Native scrollbar is hidden; a slim thumb, edge fades and a "more below" hint show that the list scrolls.
export default function ScrollArea({ className = "", label, children }: { className?: string; label: string; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [state, setState] = useState({ top: 0, height: 0, atStart: true, atEnd: true, scrollable: false });
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const scrollable = el.scrollHeight > el.clientHeight + 1;
    const ratio = el.clientHeight / el.scrollHeight;
    const height = Math.max(ratio * el.clientHeight, 28);
    const top = (el.scrollTop / (el.scrollHeight - el.clientHeight || 1)) * (el.clientHeight - height);
    setState({ top, height, scrollable, atStart: el.scrollTop <= 1, atEnd: el.scrollTop + el.clientHeight >= el.scrollHeight - 1 });
  }, []);
  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => observer.disconnect();
  }, [measure]);
  return <div className={`scroll-area ${className}`}>
    <div className="scroll-area-viewport" ref={ref} tabIndex={0} role="region" aria-label={label} onScroll={measure}>{children}</div>
    {state.scrollable && <>
      <span className={`scroll-fade top${state.atStart ? "" : " on"}`} aria-hidden="true" />
      <span className={`scroll-fade bottom${state.atEnd ? "" : " on"}`} aria-hidden="true" />
      <span className="scroll-track" aria-hidden="true"><span className="scroll-thumb" style={{ height: state.height, transform: `translateY(${state.top}px)` }} /></span>
      {!state.atEnd && <button type="button" className="scroll-more" onClick={() => ref.current?.scrollBy({ top: ref.current.clientHeight * 0.8, behavior: "smooth" })}><Icon name="chevron" size={14} />More below</button>}
    </>}
  </div>;
}
