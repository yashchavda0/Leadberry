"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import Toast, { type ToastVariant } from "@/components/Toast";

type Item = { id: number; variant: ToastVariant; message: string; title?: string };
type Options = { title?: string; duration?: number };
type Notify = Record<ToastVariant, (message: string, options?: Options) => void>;

const Context = createContext<Notify | null>(null);
const defaults: Record<ToastVariant, number> = { success: 4000, info: 5000, warning: 6000, error: 8000 };
const MAX_VISIBLE = 4;
let counter = 0;

export function useNotify(): Notify {
  const value = useContext(Context);
  if (!value) throw new Error("useNotify must be used inside NotificationProvider");
  return value;
}

export default function NotificationProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = useState<(Item & { duration: number })[]>([]);
  const dismiss = useCallback((id: number) => setItems(list => list.filter(item => item.id !== id)), []);
  const notify = useMemo<Notify>(() => {
    const push = (variant: ToastVariant) => (message: string, options?: Options) =>
      setItems(list => [...list, { id: ++counter, variant, message, title: options?.title, duration: options?.duration ?? defaults[variant] }].slice(-MAX_VISIBLE));
    return { success: push("success"), info: push("info"), warning: push("warning"), error: push("error") };
  }, []);
  return <Context.Provider value={notify}>
    {children}
    <div className="toast-stack" aria-label="Notifications">
      {items.map(item => <Toast key={item.id} variant={item.variant} title={item.title} message={item.message} duration={item.duration} onDone={() => dismiss(item.id)} />)}
    </div>
  </Context.Provider>;
}
