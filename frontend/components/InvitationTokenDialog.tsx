"use client";

import { useEffect, useState } from "react";
import { useNotify } from "@/components/Notifications";
import { Field, Loading } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { crm, errorMessage } from "@/lib/crm";

type Invitation = { invitation_token: string; expires_at: string };

export default function InvitationTokenDialog({ memberId, onClose }: { memberId: string; onClose: () => void }) {
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [error, setError] = useState("");
  const notify = useNotify();
  const path = `/memberships/${memberId}/invitation`;

  useEffect(() => {
    const request = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let expiry: ReturnType<typeof setTimeout>;
    async function check() {
      try {
        const current = await crm<Invitation>(path, { signal: request.signal, cache: "no-store" });
        if (request.signal.aborted) return;
        const remaining = Date.parse(current.expires_at) - Date.now();
        if (remaining <= 0) {
          setInvitation(null);
          setError("This invitation has expired.");
          return;
        }
        setInvitation(current);
        clearTimeout(expiry);
        expiry = setTimeout(() => { setInvitation(null); setError("This invitation has expired."); }, remaining);
        timer = setTimeout(() => void check(), 5000);
      } catch (failure) {
        if (request.signal.aborted) return;
        clearTimeout(expiry);
        setInvitation(null);
        setError(errorMessage(failure));
      }
    }
    void check();
    return () => { request.abort(); clearTimeout(timer); clearTimeout(expiry); };
  }, [path]);

  async function copy() {
    try {
      const current = await crm<Invitation>(path, { cache: "no-store" });
      await navigator.clipboard.writeText(current.invitation_token);
      notify.success("Invitation token copied.");
    } catch (failure) { notify.error(errorMessage(failure), { title: "Token could not be copied" }); }
  }

  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Invitation token</DialogTitle>
        <DialogDescription>Share privately. Do not include it in a URL.</DialogDescription>
      </DialogHeader>
      {invitation ? <>
        <Field label="Private invitation token"><textarea className="input mono" readOnly value={invitation.invitation_token} rows={4} autoComplete="off" /></Field>
        <p className="small muted">Expires {new Date(invitation.expires_at).toLocaleString()}</p>
        <div className="form-actions"><Button onClick={() => void copy()}>Copy token</Button></div>
      </> : error ? <p role="status">{error}</p> : <Loading />}
    </DialogContent>
  </Dialog>;
}