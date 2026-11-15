"use client";

import { useState } from "react";
import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import BackfillProgress, { type ImportAction } from "@/components/marketplace/BackfillProgress";
import HoldReason from "@/components/marketplace/HoldReason";
import { formatDate, formatInterval, type MarketplaceAccount, type MarketplaceProvider } from "@/lib/crm";

export type AccountStatus = { label: string; tone: "success" | "warn" | "danger" | ""; detail: string };
export type AccountAction = "test" | "sync" | "activate" | "pause" | "retire";

export default function AccountRow({ account, provider, providerName, status, manage, busy, pending, verified, onAction, onHistory, onSettings, onSchedule, onImport, onImportDetails, onImportAction }: {
  account: MarketplaceAccount; provider?: MarketplaceProvider; providerName: string; status: AccountStatus; manage: boolean;
  busy: boolean; pending: boolean; verified: boolean;
  onAction: (action: AccountAction) => void; onHistory: () => void; onSettings: () => void;
  onSchedule: () => void; onImport: () => void; onImportDetails: () => void; onImportAction: (action: ImportAction) => void;
}) {
  const [open, setOpen] = useState(false);
  const leads = `/leads?${new URLSearchParams({ integration_id: account.id, connection: account.name })}`;
  const live = account.schedule_status.live;
  const history = account.schedule_status.history;
  const importing = history?.state === "active";
  return <article className="account-row">
    <div className="account-row-main">
      <div className="marketplace-title account-row-id"><ProviderLogo code={account.provider_code} name={providerName} /><div><h3>{account.name}</h3><span className="small muted">{providerName}{provider?.adapter ? ` · every ${formatInterval(account.sync_interval_seconds)}` : ""}</span></div></div>
      <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
      <div className="account-row-meta small muted"><span>Last lead</span><strong>{formatDate(account.last_received_at)}</strong></div>
      <div className="account-row-actions">
        {manage && provider?.adapter && (account.status === "active"
          ? <Button className="action-main" disabled={busy || pending} onClick={() => onAction("sync")}><Icon name="sync" />Sync now</Button>
          : verified && !pending
            ? <Button className="action-main" disabled={busy} onClick={() => onAction("activate")}><Icon name="play" />Activate</Button>
            : <Button className="action-main" disabled={busy || pending} onClick={() => onAction("test")}><Icon name="plug" />{pending ? "Testing..." : "Test connection"}</Button>)}
        {manage && provider?.adapter && account.status === "active" && <IconButton label="Pause" disabled={busy} onClick={() => onAction("pause")}><Icon name="pause" /></IconButton>}
        {manage && provider?.adapter && <IconButton label={`Sync schedule for ${account.name}`} disabled={busy} onClick={onSchedule}><Icon name="clock" /></IconButton>}
        {manage && provider?.adapter && <IconButton label={`Import past leads for ${account.name}`} disabled={busy || importing} onClick={onImport}><Icon name="download" /></IconButton>}
        {manage && provider?.setup && <IconButton label={`Settings for ${account.name}`} disabled={busy} onClick={onSettings}><Icon name="settings" /></IconButton>}
        <IconButton label="View leads" href={leads}><Icon name="leads" /></IconButton>
        <IconButton label="History" onClick={onHistory}><Icon name="history" /></IconButton>
        {manage && <IconButton label="Disconnect" className="ui-icon-danger" disabled={busy} onClick={() => onAction("retire")}><Icon name="trash" /></IconButton>}
        <IconButton label={open ? "Hide details" : "Show details"} aria-expanded={open} onClick={() => setOpen(value => !value)}><span className={`chevron${open ? " open" : ""}`}><Icon name="chevron" /></span></IconButton>
      </div>
    </div>
    {status.tone === "danger"
      ? <div className="account-row-alert" role="alert"><Icon name="alert" size={16} /><span>{status.detail}</span></div>
      : <p className="small muted account-row-status">{status.detail}</p>}
    <HoldReason className="account-row-hold" reason={live.reason} until={live.until} provider={providerName} />
    {history && history.state !== "completed" && <BackfillProgress history={history} providerName={providerName} manage={manage} busy={busy} onDetails={onImportDetails} onAction={onImportAction} />}
    {open && <dl className="marketplace-details">
      {provider?.fields.map(field => <div key={field.key}><dt>{field.label}</dt><dd className={field.secret ? "mono" : undefined}>{field.secret ? account.credential_hint?.[field.key] || "Saved (hidden)" : account.config[field.key] || "-"}</dd></div>)}
      {provider?.adapter && <div><dt>Sync schedule</dt><dd>Every {formatInterval(account.sync_interval_seconds)}</dd></div>}
      <div><dt>Last successful check</dt><dd>{formatDate(account.last_success_at)}</dd></div>
      <div><dt>Last lead received</dt><dd>{formatDate(account.last_received_at)}</dd></div>
    </dl>}
  </article>;
}
