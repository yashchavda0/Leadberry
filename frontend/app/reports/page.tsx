"use client";

import { useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { useNotify } from "@/components/Notifications";
import Icon from "@/components/Icon";
import DateRangeFilter, { lastDays, type DateRange } from "@/components/reports/DateRangeFilter";
import ReportTable, { type ReportCell, type ReportRow } from "@/components/reports/ReportTable";
import StatusColumnPicker from "@/components/reports/StatusColumnPicker";
import { ErrorNotice } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tip";
import { download, errorMessage } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

type Counted = { total: number; open: number; counts: Record<string, number> };
type Report = {
  start: string; end: string; timezone: string;
  statuses: { id: string; name: string; color: string; type: string; is_active: boolean }[];
  follow_up: { member_id: string | null; name: string; missed: number; completed: number; upcoming: number }[];
  activity_by_user: { member_id: string | null; name: string; activities: number; leads_touched: number; connected_activities: number; leads_connected: number; first_activity_leads: number; average_first_activity_hours: number | null; median_first_activity_hours: number | null }[];
  by_user: (Counted & { member_id: string | null; name: string; is_me: boolean })[];
  by_source: (Counted & { name: string })[];
  source_conversion: { name: string; total: number; converted: number; conversion_rate: number }[];
};

export default function ReportsPage() { return <Guard permission="reports.view"><Reports /></Guard>; }

const num = (value: number) => value.toLocaleString();
const sum = (values: number[]) => num(values.reduce((total, value) => total + value, 0));
const dim = (value: number): ReportCell["tone"] => value ? undefined : "muted";

function Reports() {
  const { can } = useSession();
  const notify = useNotify();
  const [range, setRange] = useState<DateRange>(() => lastDays(7));
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState<string[] | null>(null);
  const query = new URLSearchParams(range).toString();
  const report = useResource<Report>(`/reports/leads?${query}`, true);
  const data = report.data;
  async function exportExcel() {
    setBusy(true);
    try { const name = await download(`/reports/leads/export?${query}`, "lead-report.xlsx"); notify.success(`${name} downloaded.`); }
    catch (problem) { notify.error(errorMessage(problem), { title: "Report could not be downloaded" }); }
    finally { setBusy(false); }
  }
  const link = (filters: Record<string, string>) => `/leads?${new URLSearchParams({ start: range.start, end: range.end, ...filters })}`;

  // Auto selection: statuses with leads in range (max 8), so 100 statuses never create 100 columns.
  const statuses = data?.statuses || [];
  const used = new Set([...(data?.by_user || []), ...(data?.by_source || [])].flatMap(row => Object.keys(row.counts)));
  const auto = statuses.filter(status => used.has(status.id)).slice(0, 8).map(status => status.id);
  const selected = picked ?? auto;
  const shown = statuses.filter(status => selected.includes(status.id));
  const hidden = statuses.filter(status => !selected.includes(status.id));
  const otherOf = (counts: Record<string, number>) => hidden.reduce((total, status) => total + (counts[status.id] || 0), 0);
  const allRows = [...(data?.by_user || []), ...(data?.by_source || [])];
  const showOther = allRows.some(row => otherOf(row.counts) > 0);
  const headers = ["Total", "Open", ...shown.map(status => status.name), ...(showOther ? ["Other statuses"] : [])];

  function statusCells(row: Counted, filter: Record<string, string> | null): ReportCell[] {
    return [
      { content: num(row.total), href: filter ? link(filter) : undefined },
      { content: num(row.open), tone: dim(row.open) },
      ...shown.map(status => { const count = row.counts[status.id] || 0; return { content: count ? num(count) : "-", href: count && filter ? link({ ...filter, status_id: status.id }) : undefined, tone: dim(count) }; }),
      ...(showOther ? [{ content: otherOf(row.counts) ? num(otherOf(row.counts)) : "-", tone: dim(otherOf(row.counts)) }] : []),
    ];
  }
  function totalsOf(rows: Counted[]): string[] {
    return [sum(rows.map(row => row.total)), sum(rows.map(row => row.open)), ...shown.map(status => sum(rows.map(row => row.counts[status.id] || 0))), ...(showOther ? [sum(rows.map(row => otherOf(row.counts)))] : [])];
  }

  const followRows: ReportRow[] = (data?.follow_up || []).map(row => ({
    key: row.member_id || "none", label: row.name,
    cells: [{ content: num(row.missed), tone: row.missed ? "danger" : "muted" }, { content: num(row.completed), tone: row.completed ? "success" : "muted" }, { content: num(row.upcoming), tone: dim(row.upcoming) }],
  }));
  const activityRows: ReportRow[] = (data?.activity_by_user || []).map(row => ({
    key: row.member_id || "none", label: row.name,
    cells: [
      { content: num(row.activities), tone: dim(row.activities) },
      { content: num(row.leads_touched), tone: dim(row.leads_touched) },
      { content: num(row.leads_connected), tone: row.leads_connected ? "success" : "muted" },
      { content: row.median_first_activity_hours === null ? "-" : `${row.median_first_activity_hours} h` },
    ],
  }));
  const sourceConversionRows: ReportRow[] = (data?.source_conversion || []).map(row => ({
    key: row.name, label: row.name, labelHref: link({ source: row.name }),
    cells: [
      { content: num(row.total), href: link({ source: row.name }) },
      { content: num(row.converted), tone: row.converted ? "success" : "muted", href: row.converted ? link({ source: row.name, status_id: statuses.find(status => status.type === "won")?.id || "" }) : undefined },
      { content: `${row.conversion_rate.toFixed(1)}%` },
    ],
  }));
  const userRows: ReportRow[] = (data?.by_user || []).map(row => {
    const filter = row.member_id ? { assignee: row.member_id } : null;
    return { key: row.member_id || "none", label: row.is_me ? `${row.name} (you)` : row.name, labelHref: filter ? link(filter) : undefined, cells: statusCells(row, filter) };
  });
  const sourceRows: ReportRow[] = (data?.by_source || []).map(row => {
    const filter = { source: row.name };
    return { key: row.name, label: row.name, labelHref: link(filter), cells: statusCells(row, filter) };
  });
  const loading = report.loading && !data;
  const picker = statuses.length > 0 && <StatusColumnPicker statuses={statuses} selected={selected} onChange={setPicked} onReset={() => setPicked(null)} />;
  return <>
    <div className="page-header">
      <div><span className="eyebrow">INSIGHTS</span><h1>Lead reports</h1><p className="muted">See what each user is handling, how leads are progressing and where they come from.</p></div>
      <div className="actions">
        <Tip label="Refresh" disabled={report.loading}><Button variant="outline" size="icon" aria-label="Refresh report" disabled={report.loading} onClick={report.reload}><span className={report.loading ? "spin" : undefined}><Icon name="refresh" /></span></Button></Tip>
        {can("reports.export") && <Button variant="outline" disabled={busy || loading} onClick={() => void exportExcel()}><Icon name="download" />{busy ? "Preparing..." : "Download Excel"}</Button>}
      </div>
    </div>
    <div className="report-toolbar"><DateRangeFilter value={range} onChange={setRange} />{data && <span className="small muted">Times in {data.timezone}</span>}</div>
    <ErrorNotice error={report.error} />
    <ReportTable title="Follow-ups" icon="calendar" description="Scheduled dates and recorded task completions in the selected range. Completions are tracked from the follow-up workspace launch." loading={loading}
      headers={["Missed", "Completed", "Upcoming"]} rows={followRows} empty="No follow-ups are scheduled in this date range."
      totals={[sum((data?.follow_up || []).map(row => row.missed)), sum((data?.follow_up || []).map(row => row.completed)), sum((data?.follow_up || []).map(row => row.upcoming))]} />
    <ReportTable title="Response activity" icon="history" description="Manually logged contact activities by actor. Connected means the actor marked the activity outcome as connected." loading={loading}
      headers={["Activities", "Leads touched", "Leads connected", "Median first activity"]} rows={activityRows} empty="No response activities have been logged for this period."
      totals={[sum((data?.activity_by_user || []).map(row => row.activities)), sum((data?.activity_by_user || []).map(row => row.leads_touched)), sum((data?.activity_by_user || []).map(row => row.leads_connected)), "-" ]} />
    <ReportTable title="Lead report" subtitle="(all channels)" icon="leads" description="Leads received in the range by user and status. Click a name or number to open those leads." loading={loading} action={picker}
      headers={headers} rows={userRows} empty="No leads were received in this date range." totals={totalsOf(data?.by_user || [])} />
    <ReportTable title="Lead report as per source" nameHeader="Source" icon="store" description="The same breakdown by where the leads came from." loading={loading} action={picker}
      headers={headers} rows={sourceRows} empty="No leads were received in this date range." totals={totalsOf(data?.by_source || [])} />
    <ReportTable title="Source conversion" nameHeader="Source" icon="chart" description="Current won leads divided by leads received in the selected cohort. This is lead conversion, not recognized revenue." loading={loading}
      headers={["Leads received", "Currently won", "Conversion rate"]} rows={sourceConversionRows} empty="No leads were received in this date range."
      totals={[sum((data?.source_conversion || []).map(row => row.total)), sum((data?.source_conversion || []).map(row => row.converted)), data?.source_conversion?.length ? `${(100 * data.source_conversion.reduce((total, row) => total + row.converted, 0) / data.source_conversion.reduce((total, row) => total + row.total, 0)).toFixed(1)}%` : "0.0%"]} />
  </>;
}
