"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ColumnPicker, { type PickerColumn } from "@/components/ColumnPicker";
import ExportLeadsButton from "@/components/ExportLeadsButton";
import BackfillWindows, { importedLeadsHref } from "@/components/marketplace/BackfillWindows";
import HoldReason from "@/components/marketplace/HoldReason";
import ProviderLogo from "@/components/ProviderLogo";
import ScrollArea from "@/components/ScrollArea";
import StatusBadge from "@/components/StatusBadge";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, formatDate, formatDay, type ImportRequest, type MarketplaceAccount } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

const stateLabels: Record<ImportRequest["state"], string> = { active: "In progress", completed: "Completed", cancelled: "Cancelled" };
const stateTones: Record<ImportRequest["state"], "success" | "warn" | ""> = { active: "warn", completed: "success", cancelled: "" };

const COLUMNS: (PickerColumn & { defaultOn: boolean; width: number })[] = [
  { key: "requested", label: "Requested", defaultOn: true, width: 160 },
  { key: "requested_by", label: "Requested by", defaultOn: true, width: 140 },
  { key: "connection", label: "Connection", defaultOn: true, width: 190 },
  { key: "provider", label: "Provider", defaultOn: false, width: 120 },
  { key: "type", label: "Type", defaultOn: true, width: 160 },
  { key: "period", label: "Period", defaultOn: true, width: 200 },
  { key: "progress", label: "Progress", defaultOn: true, width: 180 },
  { key: "new_leads", label: "New leads", defaultOn: true, width: 100 },
  { key: "fetched", label: "Leads fetched", defaultOn: false, width: 120 },
  { key: "failed", label: "Failed periods", defaultOn: false, width: 120 },
  { key: "status", label: "Status", defaultOn: true, width: 130 },
  { key: "note", label: "Note", defaultOn: true, width: 260 },
  { key: "finished", label: "Finished", defaultOn: false, width: 160 },
];
const STORAGE_KEY = "crm.import-request-columns";
const DEFAULT_COLUMNS = COLUMNS.filter(column => column.defaultOn).map(column => column.key);

/** Every history import requested in the organization, with progress, imported leads and Excel download. */
export default function ImportRequests({ accounts, providerName, manage, onChanged }: {
  accounts: MarketplaceAccount[]; providerName: (code: string) => string; manage: boolean; onChanged: () => void;
}) {
  const { can } = useSession();
  const notify = useNotify();
  const [accountId, setAccountId] = useState("");
  const [state, setState] = useState("");
  const [kind, setKind] = useState("");
  const [details, setDetails] = useState<ImportRequest | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [columns, setColumns] = useState<string[]>(DEFAULT_COLUMNS);
  useEffect(() => {
    try {
      const saved: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
      if (Array.isArray(saved)) setColumns(saved.filter((key): key is string => COLUMNS.some(column => column.key === key)));
    } catch { /* unreadable preference: keep defaults */ }
  }, []);
  function chooseColumns(next: string[]) {
    setColumns(next);
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }
  const show = (key: string) => columns.includes(key);
  const query = new URLSearchParams(Object.entries({ account_id: accountId, state, kind }).filter(([, value]) => value));
  const list = usePaged<ImportRequest>(`/marketplace/backfills?${query}`);
  const lastDay = (value: string) => formatDay(new Date(new Date(value).getTime() - 1).toISOString());

  async function act(item: ImportRequest, action: "cancel" | "retry") {
    setBusy(item.id);
    try {
      await crm(`/marketplace/accounts/${item.account_id}/backfills/${item.id}/${action}`, { method: "POST" });
      if (action === "cancel") notify.warning(`Import for ${item.account_name} cancelled. Leads already imported are kept.`);
      else notify.info(`Failed periods for ${item.account_name} queued again.`);
      list.reload(); onChanged();
    } catch (problem) { notify.error(errorMessage(problem), { title: "Import action failed" }); }
    finally { setBusy(null); }
  }

  return <div className="import-requests">
    <div className="marketplace-toolbar">
      <select className="select" aria-label="Connection" value={accountId} onChange={event => setAccountId(event.target.value)}>
        <option value="">All connections</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.name}</option>)}
      </select>
      <select className="select" aria-label="Import status" value={state} onChange={event => setState(event.target.value)}>
        <option value="">All statuses</option><option value="active">In progress</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option>
      </select>
      <select className="select" aria-label="Request type" value={kind} onChange={event => setKind(event.target.value)}>
        <option value="">All requests</option><option value="import">Requested imports</option><option value="gap">Missed-lead recovery</option>
      </select>
      <ColumnPicker columns={COLUMNS} selected={columns} defaults={DEFAULT_COLUMNS} onChange={chooseColumns} />
    </div>
    <ErrorNotice error={list.error} />
    {!list.data && list.loading ? <Loading /> : !list.data?.data.length ? <div className="empty-state"><h2>No import requests</h2><p className="muted">Use &quot;Import past leads&quot; on a connected account to fetch earlier enquiries.</p></div> : <ScrollArea direction="x" className="import-table" label="Import requests"><table>
      <thead><tr>{COLUMNS.filter(column => show(column.key)).map(column => <th key={column.key} style={{ minWidth: column.width }}>{column.label}</th>)}<th className="sticky-actions">Actions</th></tr></thead>
      <tbody>{list.data.data.map(item => {
        const percent = item.windows_total ? Math.round((100 * item.windows_done) / item.windows_total) : 0;
        const name = providerName(item.provider_code);
        const cells: Record<string, React.ReactNode> = {
          requested: formatDate(item.created_at),
          requested_by: item.kind === "gap" ? <span className="muted">Automatic</span> : item.requested_by || <span className="muted">Former member</span>,
          connection: <div className="marketplace-title"><ProviderLogo code={item.provider_code} name={name} /><strong>{item.account_name}</strong></div>,
          provider: name,
          type: item.kind === "gap" ? "Missed-lead recovery" : "History import",
          period: <span className="small">{formatDay(item.range_start)} – {lastDay(item.range_end)}</span>,
          progress: <div className="import-progress">
            <div className="progress-bar" role="progressbar" aria-label={`Progress for ${item.account_name}`} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${percent}%` }} /></div>
            <span className="small muted">{item.windows_done}/{item.windows_total} periods</span>
          </div>,
          new_leads: item.accepted_count.toLocaleString(),
          fetched: item.fetched_count.toLocaleString(),
          failed: item.windows_failed ? <span className="danger-text">{item.windows_failed}</span> : "0",
          status: <StatusBadge tone={stateTones[item.state]}>{stateLabels[item.state]}</StatusBadge>,
          note: item.reason ? <HoldReason reason={item.reason} until={item.until} provider={name} /> : <span className="muted">–</span>,
          finished: item.finished_at ? formatDate(item.finished_at) : <span className="muted">–</span>,
        };
        return <tr key={item.id}>
          {COLUMNS.filter(column => show(column.key)).map(column => <td key={column.key} style={{ minWidth: column.width }}>{cells[column.key]}</td>)}
          <td className="sticky-actions"><div className="import-actions">
            {can("leads.view") && <Link className="row-action" href={importedLeadsHref(item.account_name, item)}>View leads</Link>}
            <ExportLeadsButton className="row-action" query={`backfill_id=${item.id}`} label="Excel" fileName="imported-leads.xlsx" />
            <button className="row-action" type="button" onClick={() => setDetails(item)}>Details</button>
            {manage && item.state !== "cancelled" && item.windows_failed > 0 && <button className="row-action" type="button" disabled={busy === item.id} onClick={() => void act(item, "retry")}>Retry failed</button>}
            {manage && item.state === "active" && <button className="row-action danger" type="button" disabled={busy === item.id} onClick={() => void act(item, "cancel")}>Cancel</button>}
          </div></td>
        </tr>;
      })}</tbody>
    </table></ScrollArea>}
    <Pagination list={list} />
    {details && <BackfillWindows account={{ id: details.account_id, name: details.account_name, provider_code: details.provider_code }} history={details} providerName={providerName(details.provider_code)} onClose={() => { setDetails(null); list.reload(); }} />}
  </div>;
}
