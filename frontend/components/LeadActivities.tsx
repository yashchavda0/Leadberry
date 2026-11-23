"use client";

import { useState } from "react";
import { useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading, Pagination } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { useNotify } from "@/components/Notifications";
import { crm, errorMessage, formatDate } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

type Activity = {
  id: string; lead_id: string; actor_membership_id: string; actor_name: string;
  activity_type: "call" | "email" | "meeting" | "other";
  outcome: "connected" | "no_answer" | "left_message" | "scheduled" | "not_applicable";
  note: string | null; created_at: string;
};

const typeLabels: Record<Activity["activity_type"], string> = {
  call: "Call", email: "Email", meeting: "Meeting", other: "Other",
};
const outcomeLabels: Record<Activity["outcome"], string> = {
  connected: "Connected", no_answer: "No answer", left_message: "Left message",
  scheduled: "Scheduled next step", not_applicable: "Not applicable",
};

export default function LeadActivities({ leadId, editable }: { leadId: string; editable: boolean }) {
  const { can } = useSession();
  const notify = useNotify();
  const activities = usePaged<Activity>(`/leads/${encodeURIComponent(leadId)}/activities`, 25);
  const [activityType, setActivityType] = useState<Activity["activity_type"]>("call");
  const [outcome, setOutcome] = useState<Activity["outcome"]>("no_answer");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    try {
      await crm(`/leads/${encodeURIComponent(leadId)}/activities`, {
        method: "POST",
        body: JSON.stringify({ activity_type: activityType, outcome, note: can("leads.pii.view") ? note.trim() : "" }),
      });
      setNote("");
      activities.reload();
      notify.success("Response activity logged.");
    } catch (error) {
      notify.error(errorMessage(error), { title: "Activity could not be logged" });
    } finally {
      setBusy(false);
    }
  }

  return <section className="lead-activities" aria-label="Response activities">
    <div className="lead-activities-heading"><h3>Response activity</h3><span className="small muted">Logged actions, not inferred from status changes</span></div>
    {editable && <form className="lead-activity-form" onSubmit={submit}>
      <Field label="Activity"><select className="select" value={activityType} onChange={event => setActivityType(event.target.value as Activity["activity_type"])} disabled={busy}>{Object.entries(typeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      <Field label="Outcome"><select className="select" value={outcome} onChange={event => setOutcome(event.target.value as Activity["outcome"])} disabled={busy}>{Object.entries(outcomeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></Field>
      {can("leads.pii.view") && <Field label="Note"><input className="input" maxLength={2000} value={note} onChange={event => setNote(event.target.value)} disabled={busy} /></Field>}
      <Button type="submit" disabled={busy}>{busy ? "Logging..." : "Log activity"}</Button>
    </form>}
    <ErrorNotice error={activities.error} />
    {activities.loading ? <Loading /> : activities.data?.data.length ? <div className="lead-activity-list">{activities.data.data.map(activity => <article className="lead-activity-entry" key={activity.id}>
      <div><strong>{typeLabels[activity.activity_type]}</strong><span className={`activity-outcome${activity.outcome === "connected" ? " connected" : ""}`}>{outcomeLabels[activity.outcome]}</span></div>
      <time className="small muted">{formatDate(activity.created_at)} · {activity.actor_name}</time>
      {activity.note && <p>{activity.note}</p>}
    </article>)}</div> : <p className="small muted">No response activities have been logged.</p>}
    <Pagination list={activities} />
  </section>;
}