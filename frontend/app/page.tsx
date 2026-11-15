"use client";

import { useState } from "react";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Loading } from "@/components/Ui";
import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tip";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import DateRangeFilter, { lastDays, type DateRange } from "@/components/reports/DateRangeFilter";
import { ActionInsights, FollowUpHealth, IntakeTrend, LeadMetrics, LeadOutcomes, MovementSummary, PeriodComparison, PerformanceTable, PipelineAging, ProcessQuality } from "@/components/dashboard/LeadAnalytics";
import { type Dashboard } from "@/lib/crm";
import { useResource } from "@/lib/hooks";
import "./dashboard.css";

export default function DashboardPage() { return <Guard permission="dashboard.view"><Overview /></Guard>; }

function Overview() {
  const { organization, can, identity } = useSession();
  const [range, setRange] = useState<DateRange | null>(null);
  const query = new URLSearchParams(range ?? {}).toString();
  const { data, loading, error, reload } = useResource<Dashboard>(`/dashboard${query ? `?${query}` : ""}`);
  const scope = identity?.data_scope === "all" ? "Organization-wide" : identity?.data_scope === "team" ? "Your team and shared leads" : "Your assigned and shared leads";
  const leadLink = can("leads.view") ? (filters: Record<string, string>) => `/leads?${new URLSearchParams({ ...(range ?? {}), ...filters })}` : undefined;
  return <div className="lead-dashboard" aria-busy={loading}>
    <div className="page-header dashboard-header"><div><span className="eyebrow">LEAD INTELLIGENCE</span><h1>{organization?.name}</h1><p className="muted">{scope}<span className="dashboard-separator">/</span>{data?.timezone ?? organization?.timezone}</p></div><div className="actions dashboard-controls">
      <Popover>
        <PopoverTrigger asChild><Button variant="outline" aria-label="Date range"><Icon name="calendar" />{range ? `${range.start} to ${range.end}` : "All time"}<Icon name="chevron" /></Button></PopoverTrigger>
        <PopoverContent align="end" className="dashboard-range-popover">
          <div className="dashboard-range-heading"><strong>Reporting period</strong>{range && <span>{range.start} to {range.end}</span>}</div>
          <Button variant={!range ? "secondary" : "ghost"} size="sm" aria-pressed={!range} onClick={() => setRange(null)}>All time</Button>
          <DateRangeFilter value={range} onChange={setRange} />
        </PopoverContent>
      </Popover>
      <Tip label="Refresh dashboard"><Button variant="outline" size="icon" aria-label="Refresh dashboard" disabled={loading} onClick={reload}><span className={loading ? "spin" : undefined}><Icon name="refresh" /></span></Button></Tip>
    </div></div>
    <ErrorNotice error={error} />
    {loading && <Loading />}
    {data && <>
      <LeadMetrics data={data} />
      {!data.total && <div className="dashboard-empty"><Icon name="leads" size={28} /><h2>No leads in this selection</h2><p>{range ? "No leads were received in this date range." : "Your accessible pipeline is empty."}</p>{range && <Button variant="outline" onClick={() => setRange(null)}>Show all time</Button>}</div>}
      <div className="dashboard-analysis"><LeadOutcomes data={data} leadLink={leadLink} /><IntakeTrend data={data} /></div>
      <div className="dashboard-detail-grid dashboard-workload-grid"><PipelineAging data={data} /><FollowUpHealth data={data} /></div>
      <ActionInsights data={data} />
      <PeriodComparison data={data} />
      <div className="dashboard-detail-grid"><ProcessQuality data={data} /><MovementSummary data={data} /></div>
      <PerformanceTable title="Source performance" detail="Top 20 sources by lead volume" total={data.total} rows={data.sources.map(source => ({ key: source.name, name: source.name || "Unknown", total: source.count, converted: source.converted, lost: source.lost, href: leadLink?.({ source: source.name }) }))} />
      <PerformanceTable title={identity?.data_scope === "own" ? "Your lead performance" : "Assignee performance"} detail="Top 20 assignees by lead volume, including unassigned leads" total={data.total} workload rows={data.people.map(person => ({ key: person.id ?? "unassigned", name: person.name, total: person.total, converted: person.converted, lost: person.lost, overdue: person.overdue, href: person.id ? leadLink?.({ assignee: person.id }) : undefined }))} />
      <footer className="dashboard-footnote">Current status of non-archived leads received in the selected period. Repeat enquiries are records sharing a normalized phone or email within your access, not verified repeat purchases. Lost / cancelled combines all lost-category statuses.</footer>
    </>}
  </div>;
}
