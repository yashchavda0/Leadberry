"use client";

import Link from "next/link";
import LeadsTable from "@/components/LeadsTable";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Loading } from "@/components/Ui";
import { type Dashboard } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

export default function DashboardPage() { return <Guard permission="dashboard.view"><Overview /></Guard>; }
function Overview() {
  const { organization, can, identity } = useSession();
  const { data, loading, error, reload } = useResource<Dashboard>("/dashboard");
  return <>
    <div className="page-header"><div><span className="eyebrow">WORKSPACE OVERVIEW</span><h1>{organization?.name}</h1><p className="muted">Your pipeline at a glance. Showing {identity?.data_scope}-scope leads.</p></div><div className="actions"><button className="btn" onClick={reload}>Refresh</button>{can("leads.create") && can("leads.view") && <Link className="btn btn-primary" href="/leads/new">+ New lead</Link>}</div></div>
    <ErrorNotice error={error} />{loading && <Loading />}
    {data && <>
      <div className="grid stats">{[["Total active leads", data.total], ["Received today", data.today], ["Converted", data.converted], ["Overdue follow-ups", data.overdue]].map(([label, value]) => <div className="card stat-card" key={label}><div className="stat-label">{label}</div><div className="stat-value">{Number(value).toLocaleString()}</div><span className="small muted">{label === "Received today" ? organization?.timezone : "Within your current access"}</span></div>)}</div>
      <div className="grid analytics-grid"><div className="card"><h2>Pipeline by status</h2>{data.statuses.length ? data.statuses.map(status => <div className="metric-row" key={status.name}><div className="metric-heading"><span>{status.name}</span><strong>{status.count.toLocaleString()}</strong></div><div className="meter"><div style={{ width: `${data.total ? status.count / data.total * 100 : 0}%`, background: status.color }} /></div></div>) : <p className="muted">Add your first lead to see your pipeline.</p>}</div><div className="card"><h2>Top lead sources</h2>{data.sources.length ? data.sources.map(source => <div className="source-row" key={source.name}><span className="source-icon">{source.name.slice(0, 2).toUpperCase()}</span><span>{source.name}</span><strong>{source.count.toLocaleString()}</strong></div>) : <p className="muted">No source data yet.</p>}<p className="small muted">Top 20 sources by active lead count.</p></div></div>
      {can("leads.view") && <section className="card"><div className="page-header"><h2>Recent leads</h2><Link href="/leads">View all leads</Link></div><LeadsTable leads={data.recent} /></section>}
    </>}
  </>;
}
