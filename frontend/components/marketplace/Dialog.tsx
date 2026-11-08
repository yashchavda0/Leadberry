"use client";

import { useEffect } from "react";
import Icon from "@/components/Icon";

export default function Dialog({ title, subtitle, logo, closeLabel, wide, actions, onClose, children }: {
  title: string; subtitle: string; logo?: React.ReactNode; closeLabel: string; wide?: boolean; actions?: React.ReactNode; onClose: () => void; children: React.ReactNode;
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  return <div className="marketplace-overlay" onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`marketplace-dialog${wide ? " marketplace-dialog-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby="marketplace-dialog-title">
      <div className="marketplace-dialog-header">
        <div className="marketplace-title">{logo}<div><h2 id="marketplace-dialog-title">{title}</h2><span className="small muted">{subtitle}</span></div></div>
        <div className="dialog-actions">{actions}<button className="btn icon-btn" type="button" aria-label={closeLabel} title="Close" onClick={onClose}><Icon name="close" /></button></div>
      </div>
      {children}
    </section>
  </div>;
}
