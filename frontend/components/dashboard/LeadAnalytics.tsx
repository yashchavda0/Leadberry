"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import Icon from "@/components/Icon";
import ScrollArea from "@/components/ScrollArea";
import { StatCard } from "@/components/ui/stat-card";
import { Tip } from "@/components/ui/tip";
import type { Dashboard } from "@/lib/crm";

const number = (value: number) => value.toLocaleString();
export const percent = (value: number, total: number) => total ? `${(value / total * 100).toFixed(1)}%` : "0.0%";

export function AnalyticsSection({ title, detail, children, action }: { title: string; detail?: string; children: ReactNode; action?: ReactNode }) {
  return <section className="analytics-section"><header className="analytics-section-heading"><div><h2>{title}</h2>{detail && <p>{detail}</p>}</div>{action}</header>{children}</section>;
}

export function LeadMetrics({ data }: { data: Dashboard }) {
  return <div className="dashboard-metrics">
    <StatCard label="Total leads" value={number(data.total)} icon="leads" hint={`${number(data.today)} received today in this selection`} />
    <StatCard label="Converted" value={number(data.converted)} icon="check" className="metric-success" hint={`${percent(data.converted, data.total)} of all selected leads`} />
    <StatCard label="Open pipeline" value={number(data.open)} icon="target" className="metric-open" hint={`${percent(data.open, data.total)} still in progress`} />
    <StatCard label="Lost / cancelled" value={number(data.lost)} icon="close" className="metric-lost" hint={`${percent(data.lost, data.total)} in lost-category statuses`} />
    <StatCard label="Repeat enquiries" value={number(data.repeat_leads)} icon="history" className="metric-repeat" hint={`${number(data.repeat_contacts)} shared phone / email contacts`} />
    <StatCard label="Overdue follow-ups" value={number(data.overdue)} icon="clock" className="metric-warning" hint={`${percent(data.overdue, data.open)} of open leads`} />
  </div>;
}

export function LeadOutcomes({ data, leadLink }: { data: Dashboard; leadLink?: (filters: Record<string, string>) => string }) {
  const won = data.total ? data.converted / data.total * 100 : 0;
  const lost = data.total ? data.lost / data.total * 100 : 0;
  const closed = data.converted + data.lost;
  return <AnalyticsSection title="Pipeline health" detail={`${number(closed)} closed leads · ${percent(data.converted, closed)} closed-lead win rate`}>
    <div className="outcome-layout">
      <div className="outcome-ring" role="img" aria-label={`${number(data.converted)} converted, ${number(data.lost)} lost or cancelled, ${number(data.open)} open`} style={{ background: data.total ? `conic-gradient(var(--analytics-won) 0% ${won}%, var(--analytics-lost) ${won}% ${won + lost}%, var(--analytics-open) ${won + lost}% 100%)` : "var(--border)" }}>
        <div><strong>{percent(data.converted, data.total)}</strong><span>Conversion rate</span></div>
      </div>
      <dl className="outcome-legend">{[{ label: "Converted", value: data.converted, tone: "won" }, { label: "Lost / cancelled", value: data.lost, tone: "lost" }, { label: "Open", value: data.open, tone: "open" }].map(item => <div key={item.label}><dt><i className={`analytics-dot tone-${item.tone}`} />{item.label}</dt><dd>{number(item.value)} <span>{percent(item.value, data.total)}</span></dd></div>)}</dl>
    </div>
    <ScrollArea className="status-distribution" label="Leads by status" maxHeight={180}>{data.statuses.map(status => <div className="status-distribution-row" key={status.id}>
      <div>{leadLink ? <Link href={leadLink({ status_id: status.id })}>{status.name}</Link> : <span>{status.name}</span>}<strong>{number(status.count)} <small>{percent(status.count, data.total)}</small></strong></div>
      <div className="analytics-track"><span style={{ width: `${data.total ? status.count / data.total * 100 : 0}%`, background: status.color }} /></div>
    </div>)}</ScrollArea>
    {!data.total && <p className="analytics-empty">No leads in this selection.</p>}
  </AnalyticsSection>;
}

export function IntakeTrend({ data }: { data: Dashboard }) {
  const maximum = Math.max(1, ...data.trend.flatMap(day => [day.received, day.won_events, day.lost_events]));
  const received = data.trend.reduce((total, day) => total + day.received, 0);
  const formatDay = (day: string) => new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
  const wonEvents = data.trend.reduce((total, day) => total + day.won_events, 0);
  const lostEvents = data.trend.reduce((total, day) => total + day.lost_events, 0);
  return <AnalyticsSection title="Intake & outcomes" detail="Daily leads received and status transitions during the latest 30 days">
    <div className="trend-summary"><strong>{number(received)} <span>new leads</span></strong><div><span><i className="analytics-dot tone-open" />Received {number(received)}</span><span><i className="analytics-dot tone-won" />Moved to won {number(wonEvents)}</span><span><i className="analytics-dot tone-lost" />Moved to lost {number(lostEvents)}</span></div></div>
    <div className="intake-chart" role="group" aria-label="Daily leads received and leads moved to won or lost">
      <span className="chart-maximum">{number(maximum)}</span>
      <div className="chart-columns">{data.trend.map(day => <Tip key={day.day} label={`${formatDay(day.day)}: ${number(day.received)} received, ${number(day.won_events)} moved to won, ${number(day.lost_events)} moved to lost`}><button type="button" className="chart-column" aria-label={`${formatDay(day.day)}: ${number(day.received)} received, ${number(day.won_events)} moved to won, ${number(day.lost_events)} moved to lost`}>
        <span className="chart-bar chart-bar-received" style={{ height: `${day.received / maximum * 100}%` }} />
        <span className="chart-bar chart-bar-won" style={{ height: `${day.won_events / maximum * 100}%` }} />
        <span className="chart-bar chart-bar-lost" style={{ height: `${day.lost_events / maximum * 100}%` }} />
      </button></Tip>)}</div>
      <span className="chart-zero">0</span>
    </div>
    <div className="chart-dates"><span>{data.trend[0] && formatDay(data.trend[0].day)}</span><span>{data.trend.at(-1) && formatDay(data.trend.at(-1)!.day)}</span></div>
    {!received && <p className="analytics-empty">No leads received during these days.</p>}
  </AnalyticsSection>;
}

export function FollowUpHealth({ data }: { data: Dashboard }) {
  const workload = [{ label: "Overdue", count: data.overdue, tone: "lost", icon: "alert" as const }, { label: "Upcoming", count: data.upcoming, tone: "open", icon: "calendar" as const }, { label: "Not scheduled", count: data.unscheduled, tone: "neutral", icon: "clock" as const }];
  return <AnalyticsSection title="Follow-up priorities" detail="Current workload for open leads in this selection">
    <div className="followup-breakdown">{workload.map(item => <div key={item.label}><span className={`followup-icon text-${item.tone}`}><Icon name={item.icon} size={19} /></span><div className="followup-copy"><span>{item.label}</span><div className="followup-value"><strong>{number(item.count)}</strong><span className="muted">{percent(item.count, data.open)}</span></div></div></div>)}</div>
    <div className="workload-bar" aria-hidden="true">{workload.map(item => <span className={`tone-${item.tone}`} key={item.label} style={{ width: `${data.open ? item.count / data.open * 100 : 0}%` }} />)}</div>
    <div className="analytics-observations"><p><strong>{number(data.unassigned)}</strong> leads awaiting assignment</p><p><strong>{number(data.repeat_leads)}</strong> lead records share a phone or email with another lead</p></div>
  </AnalyticsSection>;
}

function changeLabel(current: number, previous: number) {
  if (!previous) return current ? "New" : "No change";
  const change = (current - previous) / previous * 100;
  return `${change > 0 ? "+" : ""}${change.toFixed(0)}%`;
}

function dateLabel(value: string) {
  return new Date(`${value}T12:00:00Z`).toLocaleDateString(undefined, { month: "short", day: "numeric", timeZone: "UTC" });
}

export function PeriodComparison({ data }: { data: Dashboard }) {
  const period = data.period;
  const currentRate = period.received ? period.converted / period.received * 100 : 0;
  const previousRate = period.previous_received ? period.previous_converted / period.previous_received * 100 : 0;
  const rateDelta = currentRate - previousRate;
  const change = [
    { label: "New leads", current: period.received, previous: period.previous_received },
    { label: "Now converted", current: period.converted, previous: period.previous_converted },
    { label: "Now lost", current: period.lost, previous: period.previous_lost },
  ];
  return <AnalyticsSection title="Period performance" detail={`${dateLabel(period.start)}–${dateLabel(period.end)} compared with ${dateLabel(period.previous_start)}–${dateLabel(period.previous_end)}`}>
    <div className="period-comparison"><div className="period-rate"><span>Cohort conversion</span><strong>{currentRate.toFixed(1)}%</strong><small className={rateDelta > 0 ? "text-won" : rateDelta < 0 ? "text-lost" : "muted"}>{rateDelta > 0 ? "+" : ""}{rateDelta.toFixed(1)} percentage points vs prior</small><span className="small muted">Based on leads received in each period; current status</span></div>
      <div className="period-counts">{change.map(item => <div key={item.label}><span>{item.label}</span><strong>{number(item.current)}</strong><small className="muted">{changeLabel(item.current, item.previous)} · was {number(item.previous)}</small></div>)}</div>
    </div>
    <p className="small muted period-caveat">Recent cohorts have had less time to convert. Compare with similar time windows, not as a final win rate.</p>
  </AnalyticsSection>;
}

type Insight = { title: string; detail: string; severity: "urgent" | "watch" | "positive"; icon: "alert" | "clock" | "user" | "leads" | "check" };
export function ActionInsights({ data }: { data: Dashboard }) {
  const insights: Insight[] = [];
  const overdueRate = data.open ? data.overdue / data.open : 0;
  const staleRate = data.open ? data.aging.unchanged_7_days / data.open : 0;
  const convertedRate = data.period.received ? data.period.converted / data.period.received : 0;
  const previousRate = data.period.previous_received ? data.period.previous_converted / data.period.previous_received : 0;
  if (data.overdue) insights.push({ severity: overdueRate >= .2 ? "urgent" : "watch", icon: "alert", title: `${number(data.overdue)} overdue follow-ups`, detail: `${percent(data.overdue, data.open)} of open leads are past their follow-up date.` });
  if (data.unassigned) insights.push({ severity: data.unassigned / Math.max(data.total, 1) >= .15 ? "urgent" : "watch", icon: "user", title: `${number(data.unassigned)} leads are unassigned`, detail: "Assign an owner so each lead has clear accountability." });
  if (data.aging.unchanged_7_days) insights.push({ severity: staleRate >= .25 ? "urgent" : "watch", icon: "clock", title: `${number(data.aging.unchanged_7_days)} open leads have stalled`, detail: `${percent(data.aging.unchanged_7_days, data.open)} have had no status change in 7 days.` });
  if (data.quality.no_contact) insights.push({ severity: "watch", icon: "leads", title: `${number(data.quality.no_contact)} leads have no phone or email`, detail: "These records may not be reachable for follow-up." });
  if (data.period.previous_received && convertedRate < previousRate - .03) insights.push({ severity: "urgent", icon: "alert", title: "Cohort conversion is down", detail: `${(Math.abs(convertedRate - previousRate) * 100).toFixed(1)} percentage points below the previous period.` });
  if (data.update_speed.median_days !== null && data.update_speed.median_days > 3) insights.push({ severity: "watch", icon: "clock", title: "Leads are taking longer to progress", detail: `Median time to first recorded status update is ${data.update_speed.median_days} days.` });
  if (!insights.length && data.total) insights.push({ severity: "positive", icon: "check", title: "No urgent pipeline risks detected", detail: "Follow-ups are current and no large stalled or unassigned group was found." });
  return <AnalyticsSection title="What needs attention" detail="Priorities derived from your accessible lead records">
    <div className="action-insights">{insights.map((item, index) => <article className={`action-insight insight-${item.severity}`} key={item.title}><span className="insight-icon"><Icon name={item.icon} size={17} /></span><div><h3>{item.title}</h3><p>{item.detail}</p></div><span className="insight-rank">{String(index + 1).padStart(2, "0")}</span></article>)}</div>
    {!data.total && <p className="analytics-empty">Add leads to see actionable pipeline priorities.</p>}
  </AnalyticsSection>;
}

export function PipelineAging({ data }: { data: Dashboard }) {
  const groups = [{ label: "0–3 days", count: data.aging.days_0_3 }, { label: "4–7 days", count: data.aging.days_4_7 }, { label: "8–14 days", count: data.aging.days_8_14 }, { label: "15–30 days", count: data.aging.days_15_30 }, { label: "Over 30 days", count: data.aging.days_over_30 }];
  const max = Math.max(1, ...groups.map(group => group.count));
  return <AnalyticsSection title="Open pipeline age" detail="Age since lead received · selected cohort, current open status">
    <div className="aging-bars">{groups.map((group, index) => <div className="aging-row" key={group.label}><span>{group.label}</span><span className="analytics-track"><span className={index > 2 ? "aging-risk" : "aging-fresh"} style={{ width: `${group.count / max * 100}%` }} /></span><strong>{number(group.count)}</strong><small>{percent(group.count, data.open)}</small></div>)}</div>
    <p className="small muted">{number(data.aging.unchanged_7_days)} open leads have not changed status in 7 days. Age is based on receipt date, not time in current status.</p>
  </AnalyticsSection>;
}

export function ProcessQuality({ data }: { data: Dashboard }) {
  const speed = data.update_speed;
  return <AnalyticsSection title="Lead handling quality" detail="Reachability and first recorded pipeline update for this cohort">
    <div className="quality-grid"><div><span>Missing phone and email</span><strong>{number(data.quality.no_contact)}</strong><small>{percent(data.quality.no_contact, data.total)} of selected leads</small></div><div><span>Missing city</span><strong>{number(data.quality.no_city)}</strong><small>{percent(data.quality.no_city, data.total)} of selected leads</small></div><div><span>Median to first status update</span><strong>{speed.median_days === null ? "—" : `${speed.median_days}d`}</strong><small>{number(speed.updated)} of {number(data.period.received)} leads had a recorded update</small></div><div><span>Average to first status update</span><strong>{speed.average_days === null ? "—" : `${speed.average_days}d`}</strong><small>From received time to first status-history event</small></div></div>
    <p className="small muted">A status update is not the same as first customer contact. Calls, emails and meetings are not tracked as activities in this CRM.</p>
  </AnalyticsSection>;
}

export function MovementSummary({ data }: { data: Dashboard }) {
  const outcomes = data.outcomes;
  return <AnalyticsSection title="Pipeline movement" detail="Status-history events recorded during the selected period">
    <div className="movement-summary"><div><span>Leads moved to won</span><strong className="text-won">{number(outcomes.converted_leads)}</strong><small>{number(outcomes.conversion_events)} won transitions, including repeat transitions</small></div><div><span>Leads moved to lost</span><strong className="text-lost">{number(outcomes.lost_leads)}</strong><small>{number(outcomes.loss_events)} lost transitions, including repeat transitions</small></div></div>
    <div className="stage-movement">{data.stage_activity.map(stage => <div key={stage.name}><span>{stage.name}</span><strong>{number(stage.leads)} leads</strong><small>{number(stage.transitions)} transitions</small></div>)}</div>
    {!outcomes.conversion_events && !outcomes.loss_events && !data.stage_activity.length && <p className="analytics-empty">No status changes were recorded in this period.</p>}
  </AnalyticsSection>;
}

type PerformanceRow = { key: string; name: string; total: number; converted: number; lost: number; overdue?: number; href?: string };
export function PerformanceTable({ title, detail, rows, workload = false, total }: { title: string; detail: string; rows: PerformanceRow[]; workload?: boolean; total: number }) {
  const shown = rows.reduce((sum, row) => sum + row.total, 0);
  return <AnalyticsSection title={title} detail={detail}>
    <div className="analytics-table-scroll"><table className="analytics-table"><thead><tr><th>{workload ? "Assignee" : "Source"}</th><th>Leads</th><th>Converted</th><th>Open</th><th>Lost / cancelled</th><th>Conversion</th>{workload && <th>Overdue</th>}</tr></thead>
      <tbody>{rows.map(row => <tr key={row.key}><th scope="row">{row.href ? <Link href={row.href}>{row.name}</Link> : row.name}</th><td>{number(row.total)}</td><td className="text-won">{number(row.converted)}</td><td>{number(row.total - row.converted - row.lost)}</td><td>{number(row.lost)}</td><td><span className="conversion-cell"><span className="analytics-track"><span style={{ width: `${row.total ? row.converted / row.total * 100 : 0}%` }} /></span>{percent(row.converted, row.total)}</span></td>{workload && <td className={row.overdue ? "text-lost" : undefined}>{number(row.overdue ?? 0)}</td>}</tr>)}</tbody>
    </table></div>
    {!rows.length && <p className="analytics-empty">No leads in this selection.</p>}
    {shown < total && <p className="small muted">Top {rows.length} shown · {number(total - shown)} leads across remaining {workload ? "assignees" : "sources"}</p>}
  </AnalyticsSection>;
}