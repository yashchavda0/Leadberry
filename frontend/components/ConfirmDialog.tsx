"use client";

import { useEffect } from "react";
import Icon from "@/components/Icon";

export default function ConfirmDialog({ title, message, confirmLabel = "Confirm", tone = "danger", busy, onConfirm, onCancel }: {
  title: string; message: React.ReactNode; confirmLabel?: string; tone?: "danger" | "primary"; busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape" && !busy) onCancel(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [busy, onCancel]);
  return <div className="marketplace-overlay" onClick={event => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section className="marketplace-dialog confirm-dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" aria-describedby="confirm-message">
      <span className={`confirm-icon ${tone}`}><Icon name={tone === "danger" ? "trash" : "alert"} size={22} /></span>
      <h2 id="confirm-title">{title}</h2>
      <p id="confirm-message" className="muted">{message}</p>
      <div className="form-actions">
        <button className="btn" type="button" autoFocus disabled={busy} onClick={onCancel}>Cancel</button>
        <button className={`btn ${tone === "danger" ? "btn-danger-solid" : "btn-primary"}`} type="button" disabled={busy} onClick={onConfirm}>{busy ? "Please wait..." : confirmLabel}</button>
      </div>
    </section>
  </div>;
}
