"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Loading } from "@/components/Ui";
import { crm, errorMessage, type Page, type PlatformOrganization } from "@/lib/crm";
import { usePlatformSession } from "@/components/platform/PlatformLayout";

export default function PlatformHomePage() {
  const { operator } = usePlatformSession();
  const [search, setSearch] = useState("");
  const [cursorHistory, setCursorHistory] = useState<(string | null)[]>([null]);
  const [retryVersion, setRetryVersion] = useState(0);
  const cursor = cursorHistory[cursorHistory.length - 1];
  const [page, setPage] = useState<Page<PlatformOrganization> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  if (!operator) return <Loading />;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ limit: "50" });
    if (search.trim()) query.set("search", search.trim());
    if (cursor) query.set("after", cursor);
    void crm<Page<PlatformOrganization>>(`/platform/organizations?${query}`).then(data => {
      if (active) setPage(data);
    }).catch(reason => {
      if (active) setError(errorMessage(reason));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, [search, cursor, retryVersion]);

  return <>
    <header className="platform-page-header">
      <div><span className="eyebrow">CUSTOMER ACCOUNTS</span><h1>Organizations</h1><p>Subscription, access, and user administration</p></div>
      <span className="platform-state">{operator.access_level}</span>
    </header>
    <div className="platform-toolbar"><label className="sr-only" htmlFor="organization-search">Search organizations</label><input id="organization-search" className="input" placeholder="Search by workspace slug" value={search} onChange={event => { setSearch(event.target.value); setCursorHistory([null]); }} /><span className="small muted">Showing up to 50 per page</span></div>
    <ErrorNotice error={error} onRetry={() => setRetryVersion(value => value + 1)} what="organizations" />
    {loading && !page ? <Loading /> : <>
      <div className="platform-table"><table>
        <thead><tr><th>Organization</th><th>Plan</th><th>Subscription</th><th>Users</th><th>Access</th><th></th></tr></thead>
        <tbody>{page?.data.map(organization => <tr key={organization.id}>
          <td><span className="platform-row-title"><strong>{organization.name}</strong><small>{organization.slug}</small></span></td>
          <td>{organization.subscription_plan}</td>
          <td><span className={`platform-state ${organization.subscription_status}`}>{organization.subscription_status}</span><small className="platform-cell-sub">{organization.subscription_ends_at ? `Ends ${new Date(organization.subscription_ends_at).toLocaleDateString()}` : "No end date"}</small></td>
          <td>{organization.user_count.toLocaleString()} / {organization.max_users.toLocaleString()}</td>
          <td><span className={`platform-state ${organization.status}`}>{organization.status}</span></td>
          <td><Button variant="outline" size="sm" asChild><Link href={`/platform/organizations/${organization.id}`}>Manage<Icon name="chevronRight" size={15} /></Link></Button></td>
        </tr>)}</tbody>
      </table></div>
      {!loading && page?.data.length === 0 && <p className="muted">No organizations match this search.</p>}
      <div className="platform-pagination"><span>{page?.data.length ?? 0} organizations</span><div className="actions"><Button variant="outline" size="sm" disabled={cursorHistory.length < 2 || loading} onClick={() => setCursorHistory(history => history.slice(0, -1))}><Icon name="chevronLeft" size={15} />Previous</Button><Button variant="outline" size="sm" disabled={!page?.next_cursor || loading} onClick={() => page?.next_cursor && setCursorHistory(history => [...history, page.next_cursor])}>Next<Icon name="chevronRight" size={15} /></Button></div></div>
    </>}
  </>;
}