"use client";

import { useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";

export default function GeneratedPasswordDialog({ password, onClose }: { password: string; onClose: () => void }) {
  const notify = useNotify();
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(password);
    setCopied(true);
    notify.success("Temporary password copied.");
  }
  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent size="sm">
      <DialogHeader><DialogTitle>Temporary password generated</DialogTitle><DialogDescription>This password is shown once. The user must change it after signing in. Share it through a secure channel.</DialogDescription></DialogHeader>
      <div className="platform-generated-password"><code>{password}</code><Button variant="outline" size="icon" aria-label="Copy temporary password" title="Copy temporary password" onClick={() => void copy()}><Icon name={copied ? "check" : "copy"} size={16} /></Button></div>
      <DialogFooter><Button onClick={onClose}>Done</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}