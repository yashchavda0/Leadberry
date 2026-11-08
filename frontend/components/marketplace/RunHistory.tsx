"use client";

import Dialog from "@/components/marketplace/Dialog";
import Icon, { type IconName } from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import ScrollArea from "@/components/ScrollArea";
import StatusBadge from "@/components/StatusBadge";
import { ErrorNotice, Loading } from "@/components/Ui";
import { formatDate, marketplaceErrors, type MarketplaceAccount, type MarketplaceRun } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

const tone = (state: string) => state === "completed" ? "success" : state === "failed" ? "danger" : state === "cancelled" ? "" : "warn";
const stateIcon = (state: string): IconName => state === "completed" ? "check" : state === "failed" ? "alert" : state === "cancelled" ? "pause" : "sync";

export default function RunHistory({ account, providerName, onClose }: { account: MarketplaceAccount; providerName: string; onClose: () => void }) {
  const runs = useResource<{ data: MarketplaceRun[] }>(`/marketplace/accounts/${account.id}/runs`, true);
  const refresh = <button className="btn icon-btn" type="button" aria-label="Refresh" title="Refresh" disabled={runs.loading} onClick={runs.reload}><span className={runs.loading ? "spin" : undefined}><Icon name="refresh" /></span></button>;
  return <Dialog wide actions={refresh} title="Connection history" subtitle={`${account.name} · ${providerName}`} logo={<ProviderLogo code={account.provider_code} name={providerName} />} closeLabel="Close connection history" onClose={onClose}>
    <ErrorNotice error={runs.error} />
    {!runs.data && runs.loading ? <Loading /> : !runs.data?.data.length ? <div className="empty-state"><h3>No activity yet</h3><p className="muted">Connection tests and syncs will appear here.</p></div> : <ScrollArea label="Run history"><ol className="run-timeline">
      {runs.data.data.map(run => <li className={`run-item ${tone(run.state)}`} key={run.id}>
        <span className="run-dot"><Icon name={stateIcon(run.state)} size={14} /></span>
        <div className="run-body">
          <div className="run-head"><strong>{run.kind === "test" ? "Connection test" : "Lead sync"}</strong><StatusBadge tone={tone(run.state)}>{run.state}</StatusBadge></div>
          <span className="small muted">{formatDate(run.created_at)}</span>
          {run.kind === "sync" && run.state === "completed" && <div className="run-stats"><span><strong>{run.fetched_count}</strong> fetched</span><span><strong>{run.accepted_count}</strong> new leads</span></div>}
          {run.safe_error_code && <div className="run-error" role="alert"><span>{marketplaceErrors[run.safe_error_code] || run.safe_error_code.replaceAll("_", " ")}</span></div>}
        </div>
      </li>)}
    </ol></ScrollArea>}
  </Dialog>;
}
