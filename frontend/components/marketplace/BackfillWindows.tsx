"use client";

import Dialog from "@/components/marketplace/Dialog";
import HoldReason from "@/components/marketplace/HoldReason";
import ProviderLogo from "@/components/ProviderLogo";
import ScrollArea from "@/components/ScrollArea";
import StatusBadge from "@/components/StatusBadge";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { formatDate, formatDay, marketplaceErrors, type BackfillWindow, type HistoryStatus, type MarketplaceAccount } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

const tones: Record<BackfillWindow["state"], "success" | "warn" | "danger" | ""> = {
  completed: "success", running: "warn", pending: "warn", failed: "danger", expired: "", skipped: "", split: "", cancelled: "",
};
const labels: Record<BackfillWindow["state"], string> = {
  completed: "Imported", running: "Fetching", pending: "Waiting", failed: "Failed", expired: "Too old", skipped: "Skipped", split: "Split", cancelled: "Cancelled",
};

export default function BackfillWindows({ account, history, providerName, onClose }: {
  account: MarketplaceAccount; history: HistoryStatus; providerName: string; onClose: () => void;
}) {
  const windows = usePaged<BackfillWindow>(`/marketplace/accounts/${account.id}/backfills/${history.id}/windows`);
  // Ends are exclusive, so the last day shown is the day before the end instant.
  const lastDay = (value: string) => formatDay(new Date(new Date(value).getTime() - 1).toISOString());
  return <Dialog wide title="History import details" subtitle={`${account.name} · ${providerName}`} logo={<ProviderLogo code={account.provider_code} name={providerName} />} closeLabel="Close history import details" onClose={onClose}>
    <p className="small muted">{history.windows_done}/{history.windows_total} periods done · {history.fetched_count} fetched · {history.accepted_count} new leads. Each period is one provider request, fetched newest first.</p>
    <ErrorNotice error={windows.error} />
    {!windows.data && windows.loading ? <Loading /> : <ScrollArea label="Import periods"><ol className="backfill-windows">
      {windows.data?.data.map(item => <li key={item.id} className="backfill-window">
        <div className="backfill-window-head">
          <strong>{formatDay(item.window_start)} – {lastDay(item.window_end)}</strong>
          <StatusBadge tone={tones[item.state]}>{labels[item.state]}</StatusBadge>
        </div>
        <span className="small muted">{item.fetched_count} fetched · {item.accepted_count} new{item.attempts ? ` · ${item.attempts} failed attempt${item.attempts === 1 ? "" : "s"}` : ""} · updated {formatDate(item.updated_at)}</span>
        <HoldReason reason={item.hold_reason} until={item.state === "pending" ? item.next_attempt_at : null} provider={providerName} />
        {item.state === "failed" && item.safe_error_code && <p className="run-error small" role="alert">{marketplaceErrors[item.safe_error_code] || item.safe_error_code.replaceAll("_", " ")}</p>}
      </li>)}
    </ol></ScrollArea>}
    <Pagination page={windows.page} previous={windows.previous} next={windows.next} hasPrevious={windows.hasPrevious} hasNext={Boolean(windows.data?.next_cursor)} loading={windows.loading} />
  </Dialog>;
}
