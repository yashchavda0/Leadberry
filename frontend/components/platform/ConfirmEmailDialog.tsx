"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Field, ErrorNotice } from "@/components/Ui";
import { errorMessage } from "@/lib/crm";

export default function ConfirmEmailDialog({ title, description, email, actionLabel, onConfirm, onClose }: {
  title: string;
  description: string;
  email: string;
  actionLabel: string;
  onConfirm: (email: string) => Promise<void>;
  onClose: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onConfirm(confirmation.trim());
      onClose();
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setBusy(false);
    }
  }
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}>
    <DialogContent size="sm">
      <form onSubmit={submit}>
        <DialogHeader><DialogTitle>{title}</DialogTitle><DialogDescription>{description}</DialogDescription></DialogHeader>
        <div className="platform-confirm-field"><ErrorNotice error={error} /><Field label={`Enter ${email} to confirm`}><input className="input" type="email" autoComplete="off" value={confirmation} onChange={event => setConfirmation(event.target.value)} required /></Field></div>
        <DialogFooter><Button variant="outline" type="button" disabled={busy} onClick={onClose}>Cancel</Button><Button variant="destructive" type="submit" disabled={busy || confirmation.trim().toLowerCase() !== email.toLowerCase()}>{busy ? "Working..." : actionLabel}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
}