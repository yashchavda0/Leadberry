"use client";

import HoldReason from "@/components/marketplace/HoldReason";
import { formatDay, formatWhen, type HistoryStatus } from "@/lib/crm";

export type ImportAction = "cancel" | "retry";

export default function BackfillProgress({ history, providerName, manage, busy, onDetails, onAction }: {
  history: HistoryStatus; providerName: string; manage: boolean; busy: boolean;
  onDetails: () => void; onAction: (action: ImportAction) => void;
}) {
  const percent = history.windows_total ? Math.round((100 * history.windows_done) / history.windows_total) : 0;
  const gap = history.kind === "gap";
  const title = history.state === "active" ? (gap ? "Recovering missed leads" : "Importing past leads")
    : history.state === "completed" ? (gap ? "Missed leads recovered" : "Past leads imported") : "History import stopped";
  const finishing = history.state === "active" && history.eta && (!history.reason || history.reason === "gap_recovery") ? ` · estimated finish ${formatWhen(history.eta)}` : "";
  return <div className="backfill-progress">
    <div className="backfill-progress-head">
      <span className="small"><strong>{title}</strong> · {formatDay(history.range_start)} – {formatDay(history.range_end)}</span>
      <span className="small muted">{history.windows_done}/{history.windows_total} periods · {history.accepted_count} new leads{history.windows_failed ? ` · ${history.windows_failed} failed` : ""}{finishing}</span>
    </div>
    <div className="progress-bar" role="progressbar" aria-label="History import progress" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${percent}%` }} /></div>
    <HoldReason reason={history.reason} until={history.until} provider={providerName} />
    <div className="backfill-progress-actions">
      <button className="btn btn-link" type="button" onClick={onDetails}>Import details</button>
      {manage && history.state !== "cancelled" && history.windows_failed > 0 && <button className="btn btn-link" type="button" disabled={busy} onClick={() => onAction("retry")}>Retry failed periods</button>}
      {manage && history.state === "active" && <button className="btn btn-link btn-danger" type="button" disabled={busy} onClick={() => onAction("cancel")}>Cancel import</button>}
    </div>
  </div>;
}
