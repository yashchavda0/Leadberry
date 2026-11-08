"use client";

import { useEffect, useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, formatDate, type MarketplaceAccount, type MarketplaceProvider, type MarketplaceRun } from "@/lib/crm";
import { usePaged, useResource } from "@/lib/hooks";

type Assignee = { id: string; display_name: string };

export default function MarketplacePage() {
  return <Guard permission="marketplace.view"><MarketplaceWorkspace /></Guard>;
}

function MarketplaceWorkspace() {
  const { can } = useSession();
  const catalog = useResource<{ data: MarketplaceProvider[]; credential_storage_ready: boolean }>("/marketplace/providers");
  const accounts = usePaged<MarketplaceAccount>("/marketplace/accounts");
  const [tab, setTab] = useState<"providers" | "accounts">("providers");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [editor, setEditor] = useState<{ provider: MarketplaceProvider; account?: MarketplaceAccount } | null>(null);
  const [history, setHistory] = useState<MarketplaceAccount | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const providers = catalog.data?.data || [];
  const query = search.trim().toLowerCase();
  const filteredProviders = providers.filter(provider => (!category || provider.category === category) &&
    `${provider.name} ${provider.method}`.toLowerCase().includes(query));
  const filteredAccounts = (accounts.data?.data || []).filter(account =>
    `${account.name} ${providers.find(provider => provider.code === account.provider_code)?.name || account.provider_code}`.toLowerCase().includes(query));

  async function act(account: MarketplaceAccount, action: "test" | "sync" | "activate" | "pause" | "retire") {
    if (action === "retire" && !window.confirm(`Disconnect ${account.name}? Existing leads and history will be retained.`)) return;
    setBusy(account.id); setError(""); setNotice("");
    try {
      const updated = await crm<MarketplaceAccount>(`/marketplace/accounts/${account.id}/${action}`, {
        method: "POST", body: JSON.stringify({ row_version: account.row_version }),
      });
      accounts.reload();
      if (action === "test" || action === "sync") setHistory(updated);
      else setNotice(`${account.name}: ${updated.status}.`);
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(null); }
  }

  return <div className="marketplace-workspace">
    <div className="page-header"><div><span className="eyebrow">LEAD CHANNELS</span><h1>Marketplace</h1></div><button className="btn" onClick={() => { catalog.reload(); accounts.reload(); }}>Refresh</button></div>
    <div className="management-tabs" role="tablist" aria-label="Marketplace views">
      <button role="tab" aria-selected={tab === "providers"} onClick={() => { setTab("providers"); setSearch(""); }}>Providers</button>
      <button role="tab" aria-selected={tab === "accounts"} onClick={() => { setTab("accounts"); setSearch(""); }}>Connected accounts</button>
    </div>
    <ErrorNotice error={catalog.error || accounts.error || error} />
    {notice && <div className="alert alert-success" role="status">{notice}</div>}
    {catalog.data && !catalog.data.credential_storage_ready && <div className="alert alert-info">Secure credential storage is not configured.</div>}
    <div className="marketplace-toolbar"><label className="marketplace-search"><span className="sr-only">Search marketplace</span><input className="input" aria-label={tab === "providers" ? "Search providers" : "Search connected accounts"} placeholder={tab === "providers" ? "Search providers" : "Search connected accounts"} value={search} onChange={event => setSearch(event.target.value)} /></label>
      {tab === "providers" && <select className="select" aria-label="Provider category" value={category} onChange={event => setCategory(event.target.value)}><option value="">All categories</option><option value="marketplace">Marketplaces</option><option value="social">Social</option><option value="commerce">Commerce</option><option value="form">Forms</option><option value="api">API</option><option value="telephony">Telephony</option></select>}
    </div>
    <section role="tabpanel" className="marketplace-panel">
      {tab === "providers" ? catalog.loading ? <Loading /> : <div className="marketplace-provider-list">{filteredProviders.map(provider => <article className="marketplace-provider-row" key={provider.code}>
        <div className="marketplace-provider-main"><strong>{provider.name}</strong><span className="small muted">{provider.category} · {provider.method}</span><span className="small muted">{provider.note}</span></div>
        <span className={`badge ${provider.adapter ? "badge-SUCCESS" : ""}`}>{provider.adapter ? "Available" : provider.setup ? "Setup only" : "Coming later"}</span>
        <div className="actions">{provider.documentation_url && <a className="btn" href={provider.documentation_url} target="_blank" rel="noreferrer">Documentation</a>}
          {provider.setup && <button className="btn btn-primary" disabled={!can("marketplace.manage") || !catalog.data?.credential_storage_ready} onClick={() => setEditor({ provider })}>Add account</button>}
        </div>
      </article>)}{!filteredProviders.length && <div className="empty-state"><h2>No providers match</h2></div>}</div> : accounts.loading ? <Loading /> : filteredAccounts.length ? <div className="marketplace-account-list">{filteredAccounts.map(account => {
        const provider = providers.find(value => value.code === account.provider_code);
        const verified = account.verified_version === account.credential_version;
        return <article className="marketplace-account-row" key={account.id}>
          <div className="marketplace-account-heading"><div><h2>{account.name}</h2><span className="small muted">{provider?.name || account.provider_code} · credential v{account.credential_version}</span></div><span className={`badge marketplace-status-${account.status}`}>{account.status}</span></div>
          <dl className="marketplace-account-health"><div><dt>Last successful request</dt><dd>{formatDate(account.last_success_at)}</dd></div><div><dt>Last lead received</dt><dd>{formatDate(account.last_received_at)}</dd></div><div><dt>Default assignee</dt><dd>{account.default_assignee_membership_id ? "Configured" : "Unassigned"}</dd></div></dl>
          {account.safe_error_code && <p className="marketplace-error small">{account.safe_error_code.replaceAll("_", " ")}</p>}
          <div className="actions marketplace-account-actions"><button className="btn" onClick={() => setHistory(account)}>Connection history</button>
            {can("marketplace.manage") && provider?.setup && <><button className="btn" disabled={busy === account.id} onClick={() => setEditor({ provider, account })}>Settings</button>{provider.adapter && <button className="btn" disabled={busy === account.id} onClick={() => void act(account, "test")}>Test connection</button>}
              {provider.adapter && account.status === "active" && <><button className="btn" disabled={busy === account.id} onClick={() => void act(account, "sync")}>Sync leads</button><button className="btn" disabled={busy === account.id} onClick={() => void act(account, "pause")}>Pause</button></>}
              {provider.adapter && account.status !== "active" && <button className="btn" disabled={busy === account.id || !verified} title={!verified ? "Successful connection test required" : undefined} onClick={() => void act(account, "activate")}>Activate</button>}
              <button className="btn btn-danger" disabled={busy === account.id} onClick={() => void act(account, "retire")}>Disconnect</button></>}
          </div>
        </article>;
      })}</div> : <div className="empty-state"><h2>{search ? "No matching accounts" : "No connected accounts"}</h2><button className="btn" onClick={() => { setTab("providers"); setSearch(""); }}>Browse providers</button></div>}
    </section>
    {tab === "accounts" && <Pagination page={accounts.page} previous={accounts.previous} next={accounts.next} hasPrevious={accounts.hasPrevious} hasNext={Boolean(accounts.data?.next_cursor)} loading={accounts.loading} />}
    {editor && <AccountEditor provider={editor.provider} account={editor.account} storageReady={Boolean(catalog.data?.credential_storage_ready)} canAssign={can("leads.assign")} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); setTab("accounts"); accounts.reload(); setNotice("Account saved as draft."); }} />}
    {history && <RunHistory account={history} onClose={() => { setHistory(null); accounts.reload(); }} />}
  </div>;
}

function AccountEditor({ provider, account, storageReady, canAssign, onClose, onSaved }: {
  provider: MarketplaceProvider; account?: MarketplaceAccount; storageReady: boolean; canAssign: boolean;
  onClose: () => void; onSaved: () => void;
}) {
  const assignees = useResource<{ data: Assignee[] }>(canAssign ? "/marketplace/assignees" : null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    const config: Record<string, string> = {};
    const credentials: Record<string, string> = {};
    for (const field of provider.fields) {
      const value = String(form.get(field.key) || "").trim();
      if (field.secret) { if (value) credentials[field.key] = value; }
      else config[field.key] = value;
    }
    const payload = {
      provider_code: provider.code, name: String(form.get("name") || "").trim(), config, credentials,
      default_assignee_membership_id: canAssign ? String(form.get("assignee") || "") || null : account?.default_assignee_membership_id || null,
      ...(account ? { row_version: account.row_version } : {}),
    };
    try {
      await crm(account ? `/marketplace/accounts/${account.id}` : "/marketplace/accounts", {
        method: account ? "PUT" : "POST", body: JSON.stringify(payload),
      });
      onSaved();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }
  return <div className="marketplace-overlay"><section className="marketplace-dialog" role="dialog" aria-modal="true" aria-labelledby="marketplace-account-title">
    <div className="marketplace-dialog-header"><div><span className="small muted">{provider.name}</span><h2 id="marketplace-account-title">{account ? "Edit connection" : "Add connection"}</h2></div><button className="btn" type="button" onClick={onClose}>Close</button></div>
    <ErrorNotice error={error || assignees.error} />
    <form onSubmit={save}><Field label={provider.code === "indiamart" ? "Form name" : "Connection name"}><input className="input" name="name" required maxLength={100} defaultValue={account?.name || ""} /></Field>
      <div className="form-grid">{provider.fields.map(field => <Field key={field.key} label={field.label} hint={field.secret && account ? "Leave empty to keep the current credential." : undefined}>
        <input className="input" name={field.key} type={field.secret ? "password" : "text"} required={field.required && !field.secret || field.required && !account} autoComplete={field.secret ? "new-password" : "off"} defaultValue={field.secret ? "" : account?.config[field.key] || ""} />
      </Field>)}</div>
      {canAssign && <Field label="Default lead assignee"><select className="select" name="assignee" defaultValue={account?.default_assignee_membership_id || ""}><option value="">Leave unassigned</option>{assignees.data?.data.map(member => <option key={member.id} value={member.id}>{member.display_name}</option>)}</select></Field>}
      <div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || !storageReady}>{busy ? "Saving..." : account ? "Save connection" : "Save account"}</button></div>
    </form>
  </section></div>;
}

function RunHistory({ account, onClose }: { account: MarketplaceAccount; onClose: () => void }) {
  const runs = useResource<{ data: MarketplaceRun[] }>(`/marketplace/accounts/${account.id}/runs`);
  useEffect(() => {
    if (!runs.data?.data.some(run => ["queued", "running"].includes(run.state))) return;
    const timer = window.setInterval(runs.reload, 10000);
    return () => window.clearInterval(timer);
  }, [runs.data, runs.reload]);
  return <div className="marketplace-overlay"><section className="marketplace-dialog marketplace-history" role="dialog" aria-modal="true" aria-labelledby="connection-history-title">
    <div className="marketplace-dialog-header"><div><span className="small muted">{account.name}</span><h2 id="connection-history-title">Connection history</h2></div><button className="btn" onClick={onClose}>Close</button></div>
    <ErrorNotice error={runs.error} />{runs.loading ? <Loading /> : !runs.data?.data.length ? <p className="muted">No connection tests or sync runs yet.</p> : <div className="marketplace-run-list">{runs.data.data.map(run => <article className="marketplace-run" key={run.id}><div className="marketplace-account-heading"><strong>{run.kind === "test" ? "Connection test" : "Lead sync"}</strong><span className={`badge marketplace-status-${run.state}`}>{run.state}</span></div><p className="small muted">{formatDate(run.created_at)}</p><p className="small">{run.fetched_count} fetched / {run.accepted_count} new leads</p>{run.safe_error_code && <p className="marketplace-error small" role="alert">{run.safe_error_code.replaceAll("_", " ")}</p>}{run.state === "queued" && <p className="small muted">Waiting for the connector worker or account rate limit.</p>}</article>)}</div>}
    <div className="form-actions"><button className="btn" onClick={runs.reload}>Refresh history</button></div>
  </section></div>;
}
