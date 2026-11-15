"use client";

import Link from "next/link";
import Dialog from "@/components/marketplace/Dialog";
import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import ExportLeadsButton from "@/components/ExportLeadsButton";
import HoldReason from "@/components/marketplace/HoldReason";
import { useSession } from "@/components/Session";
import ProviderLogo from "@/components/ProviderLogo";
import ScrollArea from "@/components/ScrollArea";
import StatusBadge from "@/components/StatusBadge";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { formatDate, formatDay, marketplaceErrorMessage, type BackfillWindow, type HistoryStatus, type MarketplaceAccount } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

const tones: Record<BackfillWindow["state"], "success" | "warn" | "danger" | ""> = {
  completed: "success", running: "warn", pending: "warn", failed: "danger", expired: "", skipped: "", split: "", cancelled: "",
};
const labels: Record<BackfillWindow["state"], string> = {
  completed: "Imported", running: "Fetching", pending: "Waiting", failed: "Failed", expired: "Too old", skipped: "Skipped", split: "Split", cancelled: "Cancelled",
};

export function importLabel(accountName: string, history: HistoryStatus): string {
  return `${accountName} · ${formatDay(history.range_start)} – ${formatDay(new Date(new Date(history.range_end).getTime() - 1).toISOString())}`;
}

export function importedLeadsHref(accountName: string, history: HistoryStatus): string {
  return `/leads?${new URLSearchParams({ backfill_id: history.id, import: importLabel(accountName, history) })}`;
}

export default function BackfillWindows({ account, history, providerName, onClose }: {
  account: Pick<MarketplaceAccount, "id" | "name" | "provider_code">; history: HistoryStatus; providerName: string; onClose: () => void;
}) {
  const windows = usePaged<BackfillWindow>(`/marketplace/accounts/${account.id}/backfills/${history.id}/windows`);
  // Ends are exclusive, so the last day shown is the day before the end instant.
  const lastDay = (value: string) => formatDay(new Date(new Date(value).getTime() - 1).toISOString());
  const { can } = useSession();
  const leads = <>{can("leads.view") && <Button size="sm" asChild><Link href={importedLeadsHref(account.name, history)}><Icon name="leads" />View leads</Link></Button>}<ExportLeadsButton iconOnly query={`backfill_id=${history.id}`} label="Download Excel" fileName="imported-leads.xlsx" /></>;
  return <Dialog wide fixed actions={leads} title="History import details" subtitle={`${account.name} · ${providerName}`} logo={<ProviderLogo code={account.provider_code} name={providerName} />} closeLabel="Close history import details" onClose={onClose}>
    <p className="small muted">{history.windows_done}/{history.windows_total} periods done · {history.fetched_count} fetched · {history.accepted_count} new leads. Each period is one provider request, fetched newest first.</p>
    <ErrorNotice error={windows.error} />
    {!windows.data && windows.loading ? <Loading /> : <ScrollArea maxHeight="calc(min(88vh, 900px) - 290px)" label="Import periods"><ol className="backfill-windows">
      {windows.data?.data.map(item => <li key={item.id} className="backfill-window">
        <div className="backfill-window-head">
          <strong>{formatDay(item.window_start)} – {lastDay(item.window_end)}</strong>
          <StatusBadge tone={tones[item.state]}>{labels[item.state]}</StatusBadge>
        </div>
        <span className="small muted">{item.fetched_count} fetched · {item.accepted_count} new{item.attempts ? ` · ${item.attempts} failed attempt${item.attempts === 1 ? "" : "s"}` : ""} · updated {formatDate(item.updated_at)}</span>
        <HoldReason reason={item.hold_reason} until={item.state === "pending" ? item.next_attempt_at : null} provider={providerName} />
        {item.state === "failed" && item.safe_error_code && <p className="run-error small" role="alert">{marketplaceErrorMessage(item.safe_error_code)}</p>}
      </li>)}
    </ol></ScrollArea>}
    <Pagination list={windows} />
  </Dialog>;
}
