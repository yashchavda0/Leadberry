"use client";

import { useCallback, useEffect, useState } from "react";
import { Guard, useSession } from "@/components/Session";
import ProviderLogo from "@/components/ProviderLogo";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import ConfirmDialog from "@/components/ConfirmDialog";
import ProviderCard from "@/components/marketplace/ProviderCard";
import SearchInput from "@/components/SearchInput";
import Dialog from "@/components/marketplace/Dialog";
import RunHistory from "@/components/marketplace/RunHistory";
import AccountRow from "@/components/marketplace/AccountRow";
import ScheduleDialog, { IntervalSelect } from "@/components/marketplace/ScheduleDialog";
import BackfillDialog from "@/components/marketplace/BackfillDialog";
import BackfillWindows from "@/components/marketplace/BackfillWindows";
import ImportRequests from "@/components/marketplace/ImportRequests";
import type { ImportAction } from "@/components/marketplace/BackfillProgress";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { crm, errorMessage, formatInterval, formatWhen, holdReasonText, marketplaceErrors, type MarketplaceAccount, type MarketplaceProvider, type Page } from "@/lib/crm";

type Catalog = { data: MarketplaceProvider[]; credential_storage_ready: boolean; worker_online: boolean; worker_last_seen_at: string | null };
type Action = "test" | "sync" | "activate" | "pause" | "retire";
type Tone = "success" | "warn" | "danger" | "";

export default function MarketplacePage() {
  return <Guard permission="marketplace.view"><MarketplaceWorkspace /></Guard>;
}

const failure = (code: string | null) => code ? marketplaceErrors[code] || code.replaceAll("_", " ") : "";
const pending = (account: MarketplaceAccount) => account.last_run_state === "queued" || account.last_run_state === "running";
const verified = (account: MarketplaceAccount) => account.verified_version === account.credential_version;

function state(account: MarketplaceAccount, workerOnline: boolean): { label: string; tone: Tone; detail: string } {
  if (pending(account) && account.last_run_kind === "test")
    return { label: "Checking", tone: "warn", detail: workerOnline ? "Testing the API key with the provider..." : "Queued: the connector worker is offline." };
  if (account.status === "error" && account.safe_error_code) return { label: "Failed", tone: "danger", detail: failure(account.safe_error_code) || "The last request failed." };
  if (account.last_run_state === "cancelled" && account.last_run_error) return { label: "Failed", tone: "danger", detail: failure(account.last_run_error) };
  if (account.status === "active") {
    const live = account.schedule_status.live;
    const every = `Syncs every ${formatInterval(account.sync_interval_seconds)}.`;
    if (account.safe_error_code && !pending(account))
      return { label: "Live", tone: "warn", detail: `${failure(account.safe_error_code)} ${live.reason ? every : "Retrying automatically."}` };
    if (pending(account) && account.last_run_kind !== "backfill") return { label: "Syncing", tone: "success", detail: every };
    return { label: "Live", tone: "success", detail: !workerOnline ? "Paused until the connector worker is running." : live.reason || !live.until ? every : `${every} Next sync ${formatWhen(live.until)}.` };
  }
  if (account.status === "paused") return { label: "Paused", tone: "", detail: "Automatic lead sync is paused." };
  if (account.safe_error_code && !pending(account)) return { label: verified(account) ? "Verified" : "Not verified", tone: "warn", detail: failure(account.safe_error_code) };
  if (verified(account)) return { label: "Verified", tone: "success", detail: "Connection verified. Activate to start receiving leads." };
  return { label: "Not verified", tone: "warn", detail: "Test the connection to verify the API key." };
}

function MarketplaceWorkspace() {
  const { can } = useSession();
  const manage = can("marketplace.manage");
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [accounts, setAccounts] = useState<MarketplaceAccount[] | null>(null);
  const [tab, setTab] = useState<"providers" | "accounts" | "imports">("providers");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [editor, setEditor] = useState<{ provider: MarketplaceProvider; account?: MarketplaceAccount } | null>(null);
  const [history, setHistory] = useState<MarketplaceAccount | null>(null);
  const [schedule, setSchedule] = useState<MarketplaceAccount | null>(null);
  const [importing, setImporting] = useState<MarketplaceAccount | null>(null);
  const [details, setDetails] = useState<MarketplaceAccount | null>(null);
  const [error, setError] = useState("");
  const notify = useNotify();
  const [disconnecting, setDisconnecting] = useState<MarketplaceAccount | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    async function allAccounts() {
      const rows: MarketplaceAccount[] = [];
      let cursor: string | null = null;
      do {
        const page: Page<MarketplaceAccount> = await crm(`/marketplace/accounts?limit=100${cursor ? `&after=${cursor}` : ""}`);
        rows.push(...page.data);
        cursor = page.next_cursor;
      } while (cursor);
      return rows;
    }
    try {
      const [providers, rows] = await Promise.all([crm<Catalog>("/marketplace/providers"), allAccounts()]);
      setCatalog(providers); setAccounts(rows);
    } catch (problem) { setError(errorMessage(problem)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const waiting = accounts?.some(pending) ?? false;
  useEffect(() => {
    const timer = window.setInterval(() => void load(), waiting ? 5000 : 30000);
    return () => window.clearInterval(timer);
  }, [load, waiting]);

  const providers = catalog?.data || [];
  const workerOnline = Boolean(catalog?.worker_online);
  const query = search.trim().toLowerCase();
  const providerName = (code: string) => providers.find(item => item.code === code)?.name || code;
  const providerFor = (account: MarketplaceAccount) => providers.find(item => item.code === account.provider_code);
  const filteredProviders = providers.filter(item => (!category || item.category === category) && `${item.name} ${item.method}`.toLowerCase().includes(query));
  const filteredAccounts = (accounts || []).filter(item => `${item.name} ${providerName(item.provider_code)}`.toLowerCase().includes(query));

  async function act(account: MarketplaceAccount, action: Action) {
    setBusy(account.id);
    try {
      const updated = await crm<MarketplaceAccount>(`/marketplace/accounts/${account.id}/${action}`, { method: "POST", body: JSON.stringify({ row_version: account.row_version }) });
      if (action === "retire") notify.error(`${account.name} was removed from your connections.`, { title: "Connection deleted" });
      else if (action === "sync" || action === "test") notify.info(queued(updated, action === "sync" ? "Sync" : "Connection test"));
      else notify[action === "pause" ? "warning" : "success"]({ activate: `${account.name} is live.`, pause: `${account.name} paused.` }[action]);
      await load();
    } catch (problem) { notify.error(errorMessage(problem), { title: "Action failed" }); }
    finally { setBusy(null); }
  }

  // Tells the user when a request will really run and why it is not immediate.
  function queued(account: MarketplaceAccount, label: string) {
    if (!workerOnline) return `${label} queued. The connector worker is offline, so it will run once the worker starts.`;
    const live = account.schedule_status.live;
    const startsAt = live.next_request_at && Date.parse(live.next_request_at) > Date.now() + 5000 ? live.next_request_at : null;
    if (!startsAt) return `${label} queued for the connector worker.`;
    const reason = live.reason || "waiting_key_slot";
    return `${label} queued. It runs ${formatWhen(startsAt)}: ${holdReasonText(reason, providerName(account.provider_code), null)}`;
  }

  async function importAction(account: MarketplaceAccount, action: ImportAction) {
    const job = account.schedule_status.history;
    if (!job) return;
    setBusy(account.id);
    try {
      await crm(`/marketplace/accounts/${account.id}/backfills/${job.id}/${action}`, { method: "POST" });
      if (action === "cancel") notify.warning(`History import for ${account.name} cancelled. Leads already imported are kept.`);
      else notify.info(`Failed periods for ${account.name} queued again.`);
      await load();
    } catch (problem) { notify.error(errorMessage(problem), { title: "Import action failed" }); }
    finally { setBusy(null); }
  }

  async function imported(account: MarketplaceAccount) {
    setImporting(null);
    const job = account.schedule_status.history;
    const reason = job?.reason;
    if (reason) notify.info(`History import queued for ${account.name}. ${holdReasonText(reason, providerName(account.provider_code), job.until)}`);
    else notify.success(`History import started for ${account.name}: ${job?.windows_total ?? 0} periods${job?.eta ? `, estimated finish ${formatWhen(job.eta)}` : ""}.`);
    await load();
  }

  async function scheduled(account: MarketplaceAccount) {
    setSchedule(null);
    notify.success(`${account.name} now syncs every ${formatInterval(account.sync_interval_seconds)}.`);
    await load();
  }

  async function saved(account: MarketplaceAccount) {
    setEditor(null); setTab("accounts"); setSearch("");
    // Saving resets verification, so check the key straight away.
    try {
      await crm(`/marketplace/accounts/${account.id}/test`, { method: "POST", body: JSON.stringify({ row_version: account.row_version }) });
      const job = account.schedule_status.history;
      notify.success(`${account.name} saved. Connection test queued.${job?.state === "active" ? ` History import of ${job.windows_total} periods starts once the connection is tested and active.` : ""}`);
    } catch (problem) { notify.error(errorMessage(problem), { title: "Connection check failed" }); }
    await load();
  }

  return <div className="marketplace-workspace">
    <div className="page-header">
      <div><span className="eyebrow">LEAD CHANNELS</span><h1>Marketplace</h1><p className="muted">Connect lead sources and receive their enquiries as leads.</p></div>
      <div className="actions">
        {catalog && <span className={`marketplace-worker ${workerOnline ? "online" : "offline"}`} role="status">{workerOnline ? "Connector running" : "Connector offline"}</span>}
        <button className="btn" onClick={() => void load()}><Icon name="refresh" />Refresh</button>
      </div>
    </div>
    {catalog && !workerOnline && <div className="alert alert-info">
      The connector worker is not running, so connection tests and syncs stay queued. Start it with <code>python scripts/Invoke-LocalBackend.py worker</code> (or run the backend with <code>Invoke-LocalBackend.py run</code>, which starts it automatically).
    </div>}
    {catalog && !catalog.credential_storage_ready && <div className="alert alert-info">Secure credential storage is not configured on the server.</div>}
    <ErrorNotice error={error} />
    <div className="management-tabs" role="tablist" aria-label="Marketplace views">
      <button role="tab" aria-selected={tab === "providers"} onClick={() => { setTab("providers"); setSearch(""); }}>Providers</button>
      <button role="tab" aria-selected={tab === "accounts"} onClick={() => { setTab("accounts"); setSearch(""); }}>Connected accounts{accounts?.length ? ` (${accounts.length})` : ""}</button>
      <button role="tab" aria-selected={tab === "imports"} onClick={() => { setTab("imports"); setSearch(""); }}>Import requests</button>
    </div>
    {tab !== "imports" && <div className="marketplace-toolbar">
      <SearchInput className="marketplace-search" value={search} onChange={setSearch} placeholder={tab === "providers" ? "Search providers" : "Search connected accounts"} />
      {tab === "providers" && <select className="select" aria-label="Provider category" value={category} onChange={event => setCategory(event.target.value)}>
        <option value="">All categories</option><option value="marketplace">Marketplaces</option><option value="social">Social</option><option value="commerce">Commerce</option><option value="form">Forms</option><option value="api">API</option><option value="telephony">Telephony</option>
      </select>}
    </div>}
    <section role="tabpanel">
      {!catalog || !accounts ? <Loading /> : tab === "imports" ? <ImportRequests accounts={accounts} providerName={providerName} manage={manage} onChanged={() => void load()} /> : tab === "providers" ? <div className="marketplace-grid">
        {filteredProviders.map(item => {
          const connected = accounts.filter(account => account.provider_code === item.code).length;
          return <ProviderCard key={item.code} provider={item} connected={connected} canAdd={manage && catalog.credential_storage_ready} onAdd={() => setEditor({ provider: item })} />;
        })}
        {!filteredProviders.length && <div className="empty-state"><h2>No providers match</h2></div>}
      </div> : filteredAccounts.length ? <div className="account-list">
        {filteredAccounts.map(account => {
          const item = providers.find(value => value.code === account.provider_code);
          return <AccountRow key={account.id} account={account} provider={item} providerName={providerName(account.provider_code)} status={state(account, workerOnline)} manage={manage}
            busy={busy === account.id} pending={pending(account)} verified={verified(account)}
            onAction={action => action === "retire" ? setDisconnecting(account) : void act(account, action)} onHistory={() => setHistory(account)} onSettings={() => item && setEditor({ provider: item, account })}
            onSchedule={() => setSchedule(account)} onImport={() => setImporting(account)} onImportDetails={() => setDetails(account)} onImportAction={action => void importAction(account, action)} />;
        })}
      </div> : <div className="empty-state"><h2>{search ? "No matching accounts" : "No connected accounts"}</h2><button className="btn" onClick={() => { setTab("providers"); setSearch(""); }}>Browse providers</button></div>}
    </section>
    {editor && <AccountEditor provider={editor.provider} account={editor.account} storageReady={Boolean(catalog?.credential_storage_ready)} onClose={() => setEditor(null)} onSaved={account => void saved(account)} />}
    {disconnecting && <ConfirmDialog title={`Delete ${disconnecting.name}?`} message="Automatic syncing stops and the connection is removed from your list. Existing leads and history are kept." confirmLabel="Delete" busy={busy === disconnecting.id}
      onCancel={() => setDisconnecting(null)} onConfirm={() => void act(disconnecting, "retire").then(() => setDisconnecting(null))} />}
    {history && <RunHistory account={history} providerName={providerName(history.provider_code)} onClose={() => { setHistory(null); void load(); }} />}
    {schedule && providerFor(schedule) && <ScheduleDialog account={schedule} provider={providerFor(schedule)!} onClose={() => setSchedule(null)} onSaved={account => void scheduled(account)} />}
    {importing && providerFor(importing) && <BackfillDialog account={importing} provider={providerFor(importing)!} onClose={() => setImporting(null)} onStarted={account => void imported(account)} />}
    {details?.schedule_status.history && <BackfillWindows account={details} history={details.schedule_status.history} providerName={providerName(details.provider_code)} onClose={() => { setDetails(null); void load(); }} />}
  </div>;
}

function AccountEditor({ provider, account, storageReady, onClose, onSaved }: {
  provider: MarketplaceProvider; account?: MarketplaceAccount; storageReady: boolean;
  onClose: () => void; onSaved: (account: MarketplaceAccount) => void;
}) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [interval, setIntervalSeconds] = useState(provider.default_interval_seconds || 900);
  const [importHistory, setImportHistory] = useState(false);
  const schedulable = !account && Boolean(provider.adapter && provider.allowed_intervals?.length);
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
      ...(account ? { row_version: account.row_version } : {}),
      ...(schedulable ? { sync_interval_seconds: interval, import_history: importHistory } : {}),
    };
    try {
      onSaved(await crm<MarketplaceAccount>(account ? `/marketplace/accounts/${account.id}` : "/marketplace/accounts", { method: account ? "PUT" : "POST", body: JSON.stringify(payload) }));
    } catch (problem) { setError(errorMessage(problem)); setBusy(false); }
  }
  return <Dialog title={account ? "Connection settings" : `Connect ${provider.name}`} subtitle={provider.name} logo={<ProviderLogo code={provider.code} name={provider.name} />} closeLabel="Close connection settings" onClose={onClose}>
    <ErrorNotice error={error} />
    <form onSubmit={save}>
      <Field label={provider.code === "indiamart" ? "Form name" : "Connection name"}><input className="input" name="name" required maxLength={100} defaultValue={account?.name || ""} /></Field>
      {provider.fields.map(field => <div key={field.key}>
        <Field label={field.label}>
          <input className="input" name={field.key} aria-label={field.label} type={field.secret ? "password" : "text"} required={field.required && (!field.secret || !account)} autoComplete={field.secret ? "new-password" : "off"} defaultValue={field.secret ? "" : account?.config[field.key] || ""} />
        </Field>
        {field.secret && account && <p className="small muted marketplace-key-note">Current key <span className="mono">{account.credential_hint?.[field.key] || "saved (hidden)"}</span>. Leave empty to keep it.</p>}
      </div>)}
      {schedulable && <>
        <IntervalSelect provider={provider} value={interval} onChange={setIntervalSeconds} />
        <label className="checkbox-row"><input type="checkbox" name="import_history" checked={importHistory} onChange={event => setImportHistory(event.target.checked)} /><span>Import past leads (last {provider.history_days || 365} days). Fetched in free request slots after the connection is tested and active; leads keep their original enquiry date.</span></label>
      </>}
      <div className="form-actions"><button className="btn" type="button" onClick={onClose}>Cancel</button><button className="btn btn-primary" disabled={busy || !storageReady}>{busy ? "Saving..." : account ? "Save and test" : "Save account"}</button></div>
    </form>
  </Dialog>;
}
