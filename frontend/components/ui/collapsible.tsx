"use client";

import { useId, useState } from "react";
import Icon from "@/components/Icon";
import { cn } from "@/lib/utils";

// Animated open/close section; content stays mounted so form state inside is kept while collapsed.
export function Collapsible({ title, summary, defaultOpen = false, children, className }: { title: string; summary?: React.ReactNode; defaultOpen?: boolean; children: React.ReactNode; className?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return <section className={cn("ui-collapsible", open && "open", className)}>
    <button type="button" className="ui-collapsible-trigger" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>
      <span className="ui-collapsible-title">{title}</span>
      {summary && <span className="ui-collapsible-summary">{summary}</span>}
      <span className="ui-collapsible-chevron"><Icon name="chevron" size={16} /></span>
    </button>
    <div id={id} className="ui-collapsible-panel" role="region" aria-hidden={!open} inert={!open}><div className="ui-collapsible-inner">{children}</div></div>
  </section>;
}
