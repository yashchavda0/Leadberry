"use client";

import Link from "next/link";
import { useState } from "react";
import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import StatusBadge from "@/components/StatusBadge";
import { formatDate, type MarketplaceAccount, type MarketplaceProvider } from "@/lib/crm";

export type AccountStatus = { label: string; tone: "success" | "warn" | "danger" | ""; detail: string };
export type AccountAction = "test" | "sync" | "activate" | "pause" | "retire";

export default function AccountRow({ account, provider, providerName, status, manage, busy, pending, verified, onAction, onHistory, onSettings }: {
  account: MarketplaceAccount; provider?: MarketplaceProvider; providerName: string; status: AccountStatus; manage: boolean;
  busy: boolean; pending: boolean; verified: boolean;
  onAction: (action: AccountAction) => void; onHistory: () => void; onSettings: () => void;
}) {
  const [open, setOpen] = useState(false);
  const leads = `/leads?${new URLSearchParams({ integration_id: account.id, connection: account.name })}`;
  return <article className="account-row">
    <div className="account-row-main">
      <div className="marketplace-title account-row-id"><ProviderLogo code={account.provider_code} name={providerName} /><div><h3>{account.name}</h3><span className="small muted">{providerName}</span></div></div>
      <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
      <div className="account-row-meta small muted"><span>Last lead</span><strong>{formatDate(account.last_received_at)}</strong></div>
      <div className="account-row-actions">
        {manage && provider?.adapter && (account.status === "active"
          ? <button className="btn btn-primary" disabled={busy || pending} onClick={() => onAction("sync")}><Icon name="sync" />Sync now</button>
          : verified && !pending
            ? <button className="btn btn-primary" disabled={busy} onClick={() => onAction("activate")}><Icon name="play" />Activate</button>
            : <button className="btn btn-primary" disabled={busy || pending} onClick={() => onAction("test")}><Icon name="plug" />{pending ? "Testing..." : "Test connection"}</button>)}
        <Link className="btn icon-btn" href={leads} title="View leads" aria-label="View leads"><Icon name="leads" /></Link>
        {manage && provider?.adapter && account.status === "active" && <button className="btn icon-btn" aria-label="Pause" title="Pause" disabled={busy} onClick={() => onAction("pause")}><Icon name="pause" /></button>}
        <button className="btn icon-btn" aria-label="History" title="History" onClick={onHistory}><Icon name="history" /></button>
        {manage && provider?.setup && <button className="btn icon-btn" aria-label={`Settings for ${account.name}`} title="Settings" disabled={busy} onClick={onSettings}><Icon name="settings" /></button>}
        {manage && <button className="btn icon-btn btn-danger" aria-label="Disconnect" title="Disconnect" disabled={busy} onClick={() => onAction("retire")}><Icon name="trash" /></button>}
        <button className="btn icon-btn" aria-expanded={open} aria-label={open ? "Hide details" : "Show details"} title="Details" onClick={() => setOpen(value => !value)}><span className={`chevron${open ? " open" : ""}`}><Icon name="chevron" /></span></button>
      </div>
    </div>
    {status.tone === "danger"
      ? <div className="account-row-alert" role="alert"><Icon name="alert" size={16} /><span>{status.detail}</span></div>
      : <p className="small muted account-row-status">{status.detail}</p>}
    {open && <dl className="marketplace-details">
      {provider?.fields.map(field => <div key={field.key}><dt>{field.label}</dt><dd className={field.secret ? "mono" : undefined}>{field.secret ? account.credential_hint?.[field.key] || "Saved (hidden)" : account.config[field.key] || "-"}</dd></div>)}
      <div><dt>Last successful check</dt><dd>{formatDate(account.last_success_at)}</dd></div>
      <div><dt>Last lead received</dt><dd>{formatDate(account.last_received_at)}</dd></div>
    </dl>}
  </article>;
}
