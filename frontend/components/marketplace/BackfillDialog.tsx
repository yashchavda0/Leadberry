"use client";

import { useState } from "react";
import Dialog from "@/components/marketplace/Dialog";
import ProviderLogo from "@/components/ProviderLogo";
import { Field } from "@/components/Ui";
import { useNotify } from "@/components/Notifications";
import { intervalHint } from "@/components/marketplace/ScheduleDialog";
import { crm, errorMessage, formatInterval, importSlotsPerCycle, type MarketplaceAccount, type MarketplaceProvider } from "@/lib/crm";

const DAY = 86_400_000;
const localDate = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function estimate(provider: MarketplaceProvider, interval: number, from: string, to: string): string {
  const days = Math.round((Date.parse(to) - Date.parse(from)) / DAY) + 1;
  if (!(days > 0)) return "Choose a start date on or before the end date.";
  const windowDays = (provider.max_window_seconds || 7 * 86400) / 86400;
  const requests = Math.ceil(days / windowDays);
  const slots = importSlotsPerCycle(interval);
  if (!slots) return `${requests} requests needed. ${intervalHint(provider, interval)}`;
  const hours = requests / ((slots * 3600) / interval);
  return `${requests} requests of up to ${windowDays} day${windowDays === 1 ? "" : "s"} each; about ${hours < 1 ? `${Math.max(1, Math.round(hours * 60))} min` : `${hours.toFixed(1)} h`} with a ${formatInterval(interval)} sync schedule. Live sync keeps priority.`;
}

export default function BackfillDialog({ account, provider, onClose, onStarted }: {
  account: MarketplaceAccount; provider: MarketplaceProvider; onClose: () => void; onStarted: (account: MarketplaceAccount) => void;
}) {
  const historyDays = provider.history_days || 365;
  const min = localDate(new Date(Date.now() - (historyDays - 1) * DAY));
  const max = localDate(new Date());
  const created = localDate(new Date(account.created_at));
  const [from, setFrom] = useState(min);
  const [to, setTo] = useState(created < max ? created : max);
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  async function start(event: React.FormEvent) {
    event.preventDefault(); setBusy(true);
    try {
      const updated = await crm<MarketplaceAccount>(`/marketplace/accounts/${account.id}/backfills`, { method: "POST", body: JSON.stringify({ from_date: from, to_date: to }) });
      notify.info(`Importing past leads for ${account.name} is queued.`, { title: "History import queued" });
      onStarted(updated);
    } catch (problem) { notify.error(errorMessage(problem), { title: "Import could not start" }); setBusy(false); }
  }
  return <Dialog title="Import past leads" subtitle={`${account.name} · ${provider.name}`} logo={<ProviderLogo code={provider.code} name={provider.name} />} closeLabel="Close import past leads" onClose={onClose}>
    <p className="small muted">{provider.name} keeps the last {historyDays} days. Past leads are fetched newest first in the request slots left free between live syncs, and keep their original enquiry date.</p>
    <form onSubmit={start}>
      <Field label="From"><input className="input" type="date" aria-label="From" min={min} max={to} value={from} required onChange={event => setFrom(event.target.value)} /></Field>
      <Field label="To" hint={estimate(provider, account.sync_interval_seconds, from, to)}><input className="input" type="date" aria-label="To" min={from} max={max} value={to} required onChange={event => setTo(event.target.value)} /></Field>
      <div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy}>{busy ? "Starting..." : "Start import"}</button></div>
    </form>
  </Dialog>;
}
