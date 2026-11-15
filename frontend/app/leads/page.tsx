"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import LeadsTable, { isPiiLeadColumn, type LeadSort } from "@/components/LeadsTable";
import LeadFilters from "@/components/LeadFilters";
import LeadContextBar from "@/components/LeadContextBar";
import { Tip } from "@/components/ui/tip";
import LeadColumnPicker, { DEFAULT_LEAD_COLUMNS } from "@/components/LeadColumnPicker";
import ConfirmDialog from "@/components/ConfirmDialog";
import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { useNotify } from "@/components/Notifications";
import ExportLeadsButton from "@/components/ExportLeadsButton";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Loading, Pagination } from "@/components/Ui";
import { crm, errorMessage, type Lead, type LeadCustomField, type Status } from "@/lib/crm";
import { usePaged, useResource } from "@/lib/hooks";

export default function LeadsPage() { return <Guard permission="leads.view"><Suspense fallback={<Loading />}><Leads /></Suspense></Guard>; }
function Leads() {
  const { can } = useSession();
  const notify = useNotify();
  const searchParams = useSearchParams();
  const integrationId = searchParams.get("integration_id");
  const backfillId = searchParams.get("backfill_id");
  const [filters, setFilters] = useState(() => {
    const initial = new URLSearchParams();
    for (const key of ["assignee", "status_id", "start", "end", "source"]) { const value = searchParams.get(key); if (value) initial.set(key, value); }
    return initial.toString();
  });
  const [columns, setColumns] = useState<string[]>(DEFAULT_LEAD_COLUMNS);
  const [sort, setSort] = useState<LeadSort>({ key: "received_at", direction: "desc" });
  const [pageSize, setPageSize] = useState(25);
  const [preferenceBusy, setPreferenceBusy] = useState(false);
  const [pendingAction, setPendingAction] = useState<{ lead: Lead; restore: boolean } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const options = useResource<{ statuses: Status[]; custom_fields: LeadCustomField[]; sources: string[]; accounts: { id: string; name: string }[] }>("/leads/options");
  const preferences = useResource<{ columns: string[] }>("/lead-table-preferences");
  const query = new URLSearchParams(filters);
  if (integrationId) query.set("integration_id", integrationId);
  if (backfillId) query.set("backfill_id", backfillId);
  const listQuery = new URLSearchParams(query);
  listQuery.set("sort_by", sort.key);
  listQuery.set("sort_dir", sort.direction);
  const list = usePaged<Lead>(`/leads?${listQuery}`, pageSize);
  useEffect(() => { if (preferences.data) setColumns(preferences.data.columns); }, [preferences.data]);
  async function saveColumns(next: string[]) {
    setPreferenceBusy(true);
    try { const result = await crm<{ columns: string[] }>("/lead-table-preferences", { method: "PUT", body: JSON.stringify({ columns: next }) }); setColumns(result.columns); }
    catch (error) { notify.error(errorMessage(error), { title: "Columns could not be saved" }); }
    finally { setPreferenceBusy(false); }
  }
  async function changeArchive(lead: Lead, restore: boolean) {
    const action = restore ? "restore" : "archive";
    setBusyId(lead.id);
    try { await crm(`/leads/${lead.id}/${action}`, { method: "POST", body: JSON.stringify({ row_version: lead.row_version }) }); list.reload(); setPendingAction(null); notify.success(`${lead.name} ${restore ? "restored" : "archived"}.`); }
    catch (error) { notify.error(errorMessage(error)); }
    finally { setBusyId(null); }
  }
  return <><div className="page-header leads-header"><div><h1>Leads <span className="lead-count">{list.total !== null ? list.total.toLocaleString() : ""}</span>{query.get("archived") === "true" && <span className="badge">Archived</span>}</h1></div><div className="actions"><ExportLeadsButton query={query.toString()} label="Excel" className="btn lead-header-button" fileName={backfillId ? "imported-leads.xlsx" : "leads.xlsx"} />{can("leads.create") && <Button size="sm" asChild><Link href="/leads/new"><Icon name="plus" />New lead</Link></Button>}</div></div>
    {integrationId && <LeadContextBar kind="Showing leads from connection" value={searchParams.get("connection") || "Selected connection"} clearHref="/leads" clearLabel="Show all leads" />}
    {backfillId && <LeadContextBar kind="Showing leads imported by" value={searchParams.get("import") || "Selected history import"} clearHref="/leads" clearLabel="Show all leads" icon="download" />}
    <section className="leads-workspace" aria-label="Lead directory">
      <LeadFilters value={filters} onChange={setFilters} options={options.data} canAssign={can("leads.assign")} canArchive={can("leads.archive") || can("leads.restore")} loading={list.loading} tools={<><Tip label="Refresh leads" disabled={list.loading}><Button variant="ghost" size="icon" aria-label="Refresh leads" disabled={list.loading} onClick={list.reload}><Icon name="refresh" /></Button></Tip><LeadColumnPicker columns={columns} customFields={options.data?.custom_fields} busy={preferenceBusy || preferences.loading || options.loading} pii={can("leads.pii.view")} onChange={next => void saveColumns(next)} /></>} />
      <ErrorNotice error={options.error || list.error || preferences.error} />{list.error && <Button variant="outline" onClick={list.reload}>Retry</Button>}{list.loading ? <Loading /> : list.data && <LeadsTable leads={list.data.data} customFields={options.data?.custom_fields} columns={columns.filter(key => can("leads.pii.view") || !isPiiLeadColumn(key))} offset={(list.page - 1) * list.pageSize} onArchive={lead => setPendingAction({ lead, restore: false })} onRestore={lead => setPendingAction({ lead, restore: true })} busyId={busyId} canArchive={can("leads.archive")} canRestore={can("leads.restore")} sort={sort} onSortChange={setSort} />}
      <Pagination list={list} pageSizes={[25, 50, 100]} onPageSizeChange={setPageSize} />
    </section>
    {pendingAction && <ConfirmDialog title={`${pendingAction.restore ? "Restore" : "Archive"} lead`} message={`${pendingAction.lead.name} will ${pendingAction.restore ? "return to the active leads list" : "move to the archived leads list"}.`} confirmLabel={pendingAction.restore ? "Restore lead" : "Archive lead"} tone={pendingAction.restore ? "primary" : "danger"} busy={Boolean(busyId)} onCancel={() => setPendingAction(null)} onConfirm={() => void changeArchive(pendingAction.lead, pendingAction.restore)} />}
  </>;
}
