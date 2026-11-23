"use client";

import { useState } from "react";
import type { ColumnDef } from "@tanstack/react-table";
import ConfirmDialog from "@/components/ConfirmDialog";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import { ErrorNotice } from "@/components/Ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tip } from "@/components/ui/tip";
import { crm, errorMessage, formatDate } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

type IntakeKey = { id: string; name: string; created_at: string; revoked_at: string | null };

export default function ApiKeys() {
  const list = usePaged<IntakeKey>("/intake/keys");
  const notify = useNotify();
  const [dialog, setDialog] = useState(false);
  const [name, setName] = useState("");
  const [token, setToken] = useState("");
  const [revoking, setRevoking] = useState<IntakeKey | null>(null);
  const [busy, setBusy] = useState(false);
  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try { const result = await crm<{ token: string }>("/intake/keys", { method: "POST", body: JSON.stringify({ name: name.trim() }) }); setToken(result.token); list.reload(); notify.success("API key created."); }
    catch (error) { notify.error(errorMessage(error), { title: "Key could not be created" }); }
    finally { setBusy(false); }
  }
  async function revoke() {
    if (!revoking) return;
    setBusy(true);
    try { await crm(`/intake/keys/${revoking.id}`, { method: "DELETE" }); setRevoking(null); list.reload(); notify.success("API key revoked."); }
    catch (error) { notify.error(errorMessage(error), { title: "Key could not be revoked" }); }
    finally { setBusy(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(token); notify.success("Key copied."); }
    catch { notify.error("Select and copy the key manually."); }
  }
  const columns: ColumnDef<IntakeKey, unknown>[] = [
    { header: "Name", accessorKey: "name" },
    { header: "Created", cell: ({ row }) => formatDate(row.original.created_at) },
    { header: "Status", cell: ({ row }) => <Badge variant={row.original.revoked_at ? "outline" : "success"}>{row.original.revoked_at ? "Revoked" : "Active"}</Badge> },
    { header: "", id: "actions", cell: ({ row }) => !row.original.revoked_at && <Tip label="Revoke key"><Button size="icon" variant="outline" aria-label={`Revoke ${row.original.name}`} onClick={() => setRevoking(row.original)}><Icon name="trash" /></Button></Tip> },
  ];
  return <section className="intake-section">
    <div className="intake-section-header"><div><h2>Website API keys</h2><p className="small muted">Server-to-server credentials</p></div><Button onClick={() => { setName(""); setToken(""); setDialog(true); }}><Icon name="plus" />Create key</Button></div>
    <ErrorNotice error={list.error} /><DataTable columns={columns} data={list.loading ? null : list.data?.data} rowKey={row => row.id} list={list} empty={<p className="muted">No API keys yet.</p>} />
    <Dialog open={dialog} onOpenChange={open => { if (!open && !busy) { setDialog(false); setToken(""); } }}><DialogContent size="sm">
      {token ? <><DialogHeader><DialogTitle>API key created</DialogTitle><DialogDescription>Copy this key now. It cannot be shown again. Keep it on your server, never in browser code.</DialogDescription></DialogHeader><label className="intake-field">API key<textarea className="input intake-secret" readOnly value={token} rows={4} onFocus={event => event.currentTarget.select()} /></label><DialogFooter><Button variant="outline" onClick={copy}><Icon name="copy" />Copy key</Button><Button onClick={() => { setToken(""); setDialog(false); }}>Done</Button></DialogFooter></> :
      <form onSubmit={create}><DialogHeader><DialogTitle>Create API key</DialogTitle><DialogDescription>Name the server or website that will use this key.</DialogDescription></DialogHeader><label className="intake-field">Name<input className="input" required maxLength={100} value={name} onChange={event => setName(event.target.value)} /></label><DialogFooter><Button variant="outline" onClick={() => setDialog(false)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy || !name.trim()}>{busy ? "Creating..." : "Create key"}</Button></DialogFooter></form>}
    </DialogContent></Dialog>
    {revoking && <ConfirmDialog title={`Revoke ${revoking.name}?`} message="Requests using this key will stop working. Existing leads remain unchanged." confirmLabel="Revoke key" busy={busy} onCancel={() => setRevoking(null)} onConfirm={() => void revoke()} />}
  </section>;
}