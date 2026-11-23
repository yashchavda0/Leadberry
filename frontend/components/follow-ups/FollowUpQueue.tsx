"use client";

import Link from "next/link";
import { useState } from "react";
import Icon from "@/components/Icon";
import LeadAssignmentPicker from "@/components/LeadAssignmentPicker";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tip } from "@/components/ui/tip";
import { crm, errorMessage } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

export type FollowUp = {
  id: string; lead_id: string; lead_name: string; lead_status: string;
  assigned_membership_id: string | null; assignee: string | null; due_at: string;
  state: "open" | "completed" | "cancelled"; note: string | null;
  completed_at: string | null; created_at: string; row_version: number;
};

export function followUpDate(value: string | null, timezone?: string): string {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short", timeZone: timezone }).format(new Date(value)) : "-";
}

function localInput(value: string) {
  const date = new Date(value);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}

export default function FollowUpQueue() {
  const { identity, organization, can } = useSession();
  const notify = useNotify();
  const [period, setPeriod] = useState("all");
  const [mine, setMine] = useState(false);
  const [assignee, setAssignee] = useState("");
  const [task, setTask] = useState<FollowUp | null>(null);
  const [action, setAction] = useState<"complete" | "reschedule" | "cancel">("complete");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const query = new URLSearchParams({ period });
  if (mine && identity) query.set("assignee", identity.membership_id);
  else if (assignee) query.set("assignee", assignee);
  const queue = usePaged<FollowUp>(`/follow-ups?${query}`);

  function open(item: FollowUp, next: typeof action) {
    setTask(item); setAction(next); setNote(""); setDue(localInput(item.due_at));
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!task) return;
    setBusy(true);
    try {
      const body = action === "complete" ? { row_version: task.row_version, note } : action === "reschedule" ? { row_version: task.row_version, due_at: new Date(due).toISOString() } : { row_version: task.row_version };
      await crm(`/follow-ups/${task.id}/${action}`, { method: "POST", body: JSON.stringify(body) });
      notify.success(action === "complete" ? "Follow-up completed." : action === "reschedule" ? "Follow-up rescheduled." : "Follow-up cancelled.");
      setTask(null); queue.reload();
    } catch (error) { notify.error(errorMessage(error), { title: "Follow-up could not be updated" }); queue.reload(); }
    finally { setBusy(false); }
  }
  const timezone = organization?.timezone || "UTC";
  return <>
    <div className="page-header"><div><span className="eyebrow">SALES WORKSPACE</span><h1>Follow-ups</h1></div>
      <Tip label="Refresh"><Button variant="outline" size="icon" aria-label="Refresh follow-ups" onClick={queue.reload}><Icon name="refresh" /></Button></Tip>
    </div>
    <div className="follow-up-toolbar">
      <div className="follow-up-periods" role="group" aria-label="Follow-up period">{[["all", "All"], ["overdue", "Overdue"], ["today", "Today"], ["upcoming", "Upcoming"]].map(([value, label]) => <Button key={value} size="sm" variant={period === value ? "default" : "outline"} aria-pressed={period === value} onClick={() => setPeriod(value)}>{label}</Button>)}</div>
      <label className="follow-up-mine"><input type="checkbox" checked={mine} onChange={event => setMine(event.target.checked)} /> Assigned to me</label>
      {can("leads.assign") && !mine && <LeadAssignmentPicker path="/leads/assignees" label="Assignee" value={assignee} onChange={setAssignee} emptyLabel="All assignees" />}
      <span className="small muted">{timezone}</span>
    </div>
    <ErrorNotice error={queue.error} />
    {queue.loading ? <Loading /> : <div className="follow-up-table-wrap"><table className="follow-up-table"><thead><tr><th>Due</th><th>Lead</th><th>Status</th><th>Assigned to</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>
      {queue.data?.data.length ? queue.data.data.map(item => <tr key={item.id}>
        <td><span className={new Date(item.due_at).getTime() < Date.now() ? "follow-up-overdue" : undefined}>{followUpDate(item.due_at, timezone)}</span></td>
        <td><Link href={`/leads/${item.lead_id}`}>{item.lead_name}</Link></td><td>{item.lead_status}</td><td>{item.assignee || "Unassigned"}</td>
        <td><div className="follow-up-actions">{can("leads.edit") && <>
          <Tip label="Complete"><Button variant="outline" size="icon" aria-label={`Complete follow-up for ${item.lead_name}`} onClick={() => open(item, "complete")}><Icon name="check" /></Button></Tip>
          <Tip label="Reschedule"><Button variant="outline" size="icon" aria-label={`Reschedule follow-up for ${item.lead_name}`} onClick={() => open(item, "reschedule")}><Icon name="calendar" /></Button></Tip>
          <Tip label="Cancel follow-up"><Button variant="outline" size="icon" aria-label={`Cancel follow-up for ${item.lead_name}`} onClick={() => open(item, "cancel")}><Icon name="close" /></Button></Tip>
        </>}</div></td>
      </tr>) : <tr><td colSpan={5} className="muted">No follow-ups found.</td></tr>}
    </tbody></table></div>}
    <Pagination list={queue} />
    <Dialog open={Boolean(task)} onOpenChange={openState => { if (!openState && !busy) setTask(null); }}><DialogContent size="sm"><form onSubmit={submit}>
      <DialogHeader><DialogTitle>{action === "complete" ? "Complete follow-up" : action === "reschedule" ? "Reschedule follow-up" : "Cancel follow-up"}</DialogTitle><DialogDescription>{task?.lead_name}</DialogDescription></DialogHeader>
      {action === "complete" && can("leads.pii.view") && <label className="follow-up-field">Note (optional)<textarea className="input" rows={3} maxLength={2000} value={note} onChange={event => setNote(event.target.value)} /></label>}
      {action === "reschedule" && <label className="follow-up-field">Date and time (your local time)<input className="input" type="datetime-local" required value={due} onChange={event => setDue(event.target.value)} /></label>}
      <DialogFooter><Button variant="outline" onClick={() => setTask(null)} disabled={busy}>Back</Button><Button type="submit" disabled={busy}>{busy ? "Saving..." : action === "complete" ? "Complete" : action === "reschedule" ? "Reschedule" : "Cancel follow-up"}</Button></DialogFooter>
    </form></DialogContent></Dialog>
  </>;
}