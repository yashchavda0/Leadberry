"use client";

import { useState } from "react";
import Dialog from "@/components/marketplace/Dialog";
import ProviderLogo from "@/components/ProviderLogo";
import { ErrorNotice, Field } from "@/components/Ui";
import { crm, errorMessage, formatInterval, importSlotsPerCycle, type MarketplaceAccount, type MarketplaceProvider } from "@/lib/crm";

export function intervalHint(provider: MarketplaceProvider, interval: number): string {
  const slots = importSlotsPerCycle(interval);
  return slots
    ? `Leaves ${slots} free request${slots === 1 ? "" : "s"} per cycle for importing past leads.`
    : `${provider.name} allows one request every 5 minutes, so history import pauses at this interval.`;
}

export function IntervalSelect({ provider, value, onChange }: { provider: MarketplaceProvider; value: number; onChange: (value: number) => void }) {
  return <Field label="Sync every" hint={intervalHint(provider, value)}>
    <select className="select" name="sync_interval_seconds" aria-label="Sync every" value={value} onChange={event => onChange(Number(event.target.value))}>
      {(provider.allowed_intervals || []).map(seconds => <option key={seconds} value={seconds}>{formatInterval(seconds)}{seconds === provider.default_interval_seconds ? " (recommended)" : ""}</option>)}
    </select>
  </Field>;
}

export default function ScheduleDialog({ account, provider, onClose, onSaved }: {
  account: MarketplaceAccount; provider: MarketplaceProvider; onClose: () => void; onSaved: (account: MarketplaceAccount) => void;
}) {
  const [seconds, setSeconds] = useState(account.sync_interval_seconds);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      onSaved(await crm<MarketplaceAccount>(`/marketplace/accounts/${account.id}/schedule`, { method: "PUT", body: JSON.stringify({ sync_interval_seconds: seconds }) }));
    } catch (problem) { setError(errorMessage(problem)); setBusy(false); }
  }
  return <Dialog title="Sync schedule" subtitle={`${account.name} · ${provider.name}`} logo={<ProviderLogo code={provider.code} name={provider.name} />} closeLabel="Close sync schedule" onClose={onClose}>
    <ErrorNotice error={error} />
    <form onSubmit={save}>
      <IntervalSelect provider={provider} value={seconds} onChange={setSeconds} />
      <div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || seconds === account.sync_interval_seconds}>{busy ? "Saving..." : "Save schedule"}</button></div>
    </form>
  </Dialog>;
}
