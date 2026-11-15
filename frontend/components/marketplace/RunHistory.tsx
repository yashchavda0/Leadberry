"use client";

import Dialog from "@/components/marketplace/Dialog";
import Icon, { type IconName } from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import ScrollArea from "@/components/ScrollArea";
import { Tip } from "@/components/ui/tip";
import StatusBadge from "@/components/StatusBadge";
import { ErrorNotice, Loading } from "@/components/Ui";
import { formatDate, formatDay, marketplaceErrorMessage, type MarketplaceAccount, type MarketplaceRun } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

const tone = (state: string) => state === "completed" ? "success" : state === "failed" ? "danger" : state === "cancelled" ? "" : "warn";
const stateIcon = (state: string): IconName => state === "completed" ? "check" : state === "failed" ? "alert" : state === "cancelled" ? "pause" : "sync";
const title = (run: MarketplaceRun) => run.kind === "test" ? "Connection test" : run.kind === "backfill" && run.window_start && run.window_end
  ? `History import · ${formatDay(run.window_start)} – ${formatDay(new Date(new Date(run.window_end).getTime() - 1).toISOString())}`
  : "Lead sync";

export default function RunHistory({ account, providerName, onClose }: { account: MarketplaceAccount; providerName: string; onClose: () => void }) {
  const runs = useResource<{ data: MarketplaceRun[] }>(`/marketplace/accounts/${account.id}/runs`, true);
  const refresh = <Tip label="Refresh" disabled={runs.loading}><button className="btn icon-btn" type="button" aria-label="Refresh" disabled={runs.loading} onClick={runs.reload}><span className={runs.loading ? "spin" : undefined}><Icon name="refresh" /></span></button></Tip>;
  return <Dialog wide actions={refresh} title="Connection history" subtitle={`${account.name} · ${providerName}`} logo={<ProviderLogo code={account.provider_code} name={providerName} />} closeLabel="Close connection history" onClose={onClose}>
    <ErrorNotice error={runs.error} />
    {!runs.data && runs.loading ? <Loading /> : !runs.data?.data.length ? <div className="empty-state"><h3>No activity yet</h3><p className="muted">Connection tests, syncs and history imports will appear here.</p></div> : <ScrollArea label="Run history"><ol className="run-timeline">
      {runs.data.data.map(run => <li className={`run-item ${tone(run.state)}`} key={run.id}>
        <span className="run-dot"><Icon name={stateIcon(run.state)} size={14} /></span>
        <div className="run-body">
          <div className="run-head"><strong>{title(run)}</strong><StatusBadge tone={tone(run.state)}>{run.state}</StatusBadge></div>
          <span className="small muted">{formatDate(run.created_at)}</span>
          {run.kind !== "test" && run.state === "completed" && <div className="run-stats"><span><strong>{run.fetched_count}</strong> fetched</span><span><strong>{run.accepted_count}</strong> new leads</span></div>}
          {run.safe_error_code && <div className="run-error" role="alert"><span>{marketplaceErrorMessage(run.safe_error_code)}</span></div>}
        </div>
      </li>)}
    </ol></ScrollArea>}
  </Dialog>;
}
