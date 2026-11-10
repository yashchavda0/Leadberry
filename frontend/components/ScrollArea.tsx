"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

type Direction = "y" | "x" | "both";

/**
 * The one scroll container for the app. Vertical lists get a slim thumb, edge fades and a "more below" hint;
 * wide content (tables) scrolls sideways with the same slim themed bar. Cap the height with `maxHeight`.
 */
export default function ScrollArea({ className = "", label, direction = "y", maxHeight, children }: {
  className?: string; label: string; direction?: Direction; maxHeight?: string | number; children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const overlay = direction === "y";
  const [state, setState] = useState({ top: 0, height: 0, atStart: true, atEnd: true, scrollable: false });
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el || !overlay) return;
    const scrollable = el.scrollHeight > el.clientHeight + 1;
    const ratio = el.clientHeight / el.scrollHeight;
    const height = Math.max(ratio * el.clientHeight, 28);
    const top = (el.scrollTop / (el.scrollHeight - el.clientHeight || 1)) * (el.clientHeight - height);
    setState({ top, height, scrollable, atStart: el.scrollTop <= 1, atEnd: el.scrollTop + el.clientHeight >= el.scrollHeight - 1 });
  }, [overlay]);
  useEffect(() => {
    measure();
    const el = ref.current;
    if (!el || !overlay || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (el.firstElementChild) observer.observe(el.firstElementChild);
    return () => observer.disconnect();
  }, [measure, overlay]);
  return <div className={`scroll-area ${className}`}>
    <div className="scroll-area-viewport" data-direction={direction} ref={ref} tabIndex={0} role="region" aria-label={label} onScroll={measure} style={maxHeight === undefined ? undefined : { maxHeight }}>{children}</div>
    {overlay && state.scrollable && <>
      <span className={`scroll-fade top${state.atStart ? "" : " on"}`} aria-hidden="true" />
      <span className={`scroll-fade bottom${state.atEnd ? "" : " on"}`} aria-hidden="true" />
      <span className="scroll-track" aria-hidden="true"><span className="scroll-thumb" style={{ height: state.height, transform: `translateY(${state.top}px)` }} /></span>
      {!state.atEnd && <button type="button" className="scroll-more" onClick={() => ref.current?.scrollBy({ top: ref.current.clientHeight * 0.8, behavior: "smooth" })}><Icon name="chevron" size={14} />More below</button>}
    </>}
  </div>;
}
