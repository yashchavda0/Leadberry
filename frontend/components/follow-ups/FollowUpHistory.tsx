"use client";

import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { useSession } from "@/components/Session";
import { usePaged } from "@/lib/hooks";
import { followUpDate, type FollowUp } from "./FollowUpQueue";

export default function FollowUpHistory({ leadId }: { leadId: string }) {
  const { organization } = useSession();
  const history = usePaged<FollowUp>(`/leads/${encodeURIComponent(leadId)}/follow-ups`, 25);
  const timezone = organization?.timezone || "UTC";
  return <div className="follow-up-history"><h3>Follow-up history</h3><ErrorNotice error={history.error} />
    {history.loading ? <Loading /> : history.data?.data.length ? history.data.data.map(task => <div className="follow-up-history-entry" key={task.id}>
      <strong>{task.state === "open" ? "Scheduled" : task.state === "completed" ? "Completed" : "Cancelled"}</strong>
      <span className="small muted">Due {followUpDate(task.due_at, timezone)}{task.completed_at ? ` - Completed ${followUpDate(task.completed_at, timezone)}` : ""}</span>
      {task.note && <p>{task.note}</p>}
    </div>) : <p className="muted">No follow-ups recorded.</p>}
    <Pagination list={history} />
  </div>;
}