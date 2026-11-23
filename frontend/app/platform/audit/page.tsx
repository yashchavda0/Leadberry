"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { ErrorNotice, Field, Loading } from "@/components/Ui";
import { crm, errorMessage, type Page, type PlatformAuditEntry } from "@/lib/crm";

export default function PlatformAuditPage() {
  const [organizationId, setOrganizationId] = useState("");
  const [filter, setFilter] = useState("");
  const [page, setPage] = useState<Page<PlatformAuditEntry> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load(after?: string) {
    setLoading(true);
    setError("");
    const query = new URLSearchParams({ limit: "50" });
    if (after) query.set("after", after);
    if (filter.trim()) query.set("organization_id", filter.trim());
    try {
      setPage(await crm<Page<PlatformAuditEntry>>(`/platform/audit?${query}`));
    } catch (reason) {
      setError(errorMessage(reason));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void load(); }, []);

  return <>
    <header className="platform-page-header"><div><span className="eyebrow">SECURITY AND OPERATIONS</span><h1>Platform audit log</h1><p>Organization-level account actions by platform operators</p></div></header>
    <form className="platform-toolbar" onSubmit={event => { event.preventDefault(); setFilter(organizationId); void load(); }}>
      <Field label="Organization ID"><input className="input" value={organizationId} onChange={event => setOrganizationId(event.target.value)} placeholder="Optional UUID filter" /></Field>
      <Button type="submit" variant="outline">Apply filter</Button>
    </form>
    <ErrorNotice error={error} onRetry={() => void load()} what="audit events" />
    {loading && !page ? <Loading /> : <>
      <div className="platform-table"><table>
        <thead><tr><th>Time</th><th>Operator</th><th>Action</th><th>Organization</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>{page?.data.map(entry => <tr key={entry.id}>
          <td>{new Date(entry.occurred_at).toLocaleString()}</td><td>{entry.actor_email}</td><td><span className="platform-state">{entry.action.replaceAll(".", " ")}</span></td><td>{entry.organization_id ?? "Platform"}</td><td>{entry.entity_type}{entry.entity_id ? ` · ${entry.entity_id}` : ""}</td><td><code className="platform-audit-details">{JSON.stringify(entry.details)}</code></td>
        </tr>)}</tbody>
      </table></div>
      {!loading && page?.data.length === 0 && <p className="muted">No audit events found.</p>}
      <div className="platform-pagination"><span>{page?.data.length ?? 0} events</span><Button variant="outline" size="sm" disabled={!page?.next_cursor || loading} onClick={() => page?.next_cursor && void load(page.next_cursor)}>Next page</Button></div>
    </>}
  </>;
}