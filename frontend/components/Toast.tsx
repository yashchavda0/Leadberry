"use client";

import { useEffect, useRef } from "react";
import Icon, { type IconName } from "@/components/Icon";

export type ToastVariant = "success" | "info" | "warning" | "error";
const icons: Record<ToastVariant, IconName> = { success: "check", info: "info", warning: "alert", error: "error" };

// Prefer useNotify() from Notifications; use Toast directly only for a one-off, self-managed notice.
export default function Toast({ message, title, variant = "success", onDone, duration = 4000 }: { message: string; title?: string; variant?: ToastVariant; onDone: () => void; duration?: number }) {
  const done = useRef(onDone);
  done.current = onDone;
  useEffect(() => {
    const timer = window.setTimeout(() => done.current(), duration);
    return () => window.clearTimeout(timer);
  }, [message, duration]);
  return <div className="toast" data-variant={variant} role={variant === "error" || variant === "warning" ? "alert" : "status"} style={{ "--toast-duration": `${duration}ms` } as React.CSSProperties}>
    <span className="toast-icon"><Icon name={icons[variant]} size={20} /></span>
    <span className="toast-message">{title && <strong className="toast-title">{title}</strong>}{message}</span>
    <button className="toast-close" type="button" aria-label="Dismiss notification" onClick={onDone}><Icon name="close" size={16} /></button>
    <span className="toast-progress" aria-hidden="true" />
  </div>;
}
