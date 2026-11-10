"use client";

import Icon from "@/components/Icon";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

export default function ConfirmDialog({ title, message, confirmLabel = "Confirm", tone = "danger", busy, onConfirm, onCancel }: {
  title: string; message: React.ReactNode; confirmLabel?: string; tone?: "danger" | "primary"; busy?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return <AlertDialog open onOpenChange={open => { if (!open && !busy) onCancel(); }}>
    <AlertDialogContent>
      <span className={`confirm-icon ${tone}`}><Icon name={tone === "danger" ? "trash" : "alert"} size={22} /></span>
      <AlertDialogHeader>
        <AlertDialogTitle>{title}</AlertDialogTitle>
        <AlertDialogDescription>{message}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
        <AlertDialogAction variant={tone === "danger" ? "destructive" : "default"} disabled={busy} onClick={event => { event.preventDefault(); onConfirm(); }}>{busy ? "Please wait..." : confirmLabel}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
}
