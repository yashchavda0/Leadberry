"use client";

import { useState, type ReactNode } from "react";
import Icon from "./Icon";
import LeadAssignmentPicker from "./LeadAssignmentPicker";
import { Button } from "./ui/button";
import DatePicker from "./ui/date-picker";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import type { Status } from "@/lib/crm";

type Options = { statuses: Status[]; sources: string[]; accounts: { id: string; name: string }[] };
const labels: Record<string, string> = {
  q: "Search", status_id: "Status", assignee: "Assigned to", source: "Source",
  integration_id: "Source account", source_record_id: "Audience ID", tag: "Tag",
  start: "Received from", end: "Received through", status_start: "Status updated from",
  status_end: "Status updated through", archived: "View",
};
const ADVANCED = ["source", "integration_id", "source_record_id", "tag", "start", "end", "status_start", "status_end", "archived"];

export default function LeadFilters({ value, onChange, options, canAssign, canArchive, loading, tools }: {
  value: string; onChange: (value: string) => void; options?: Options | null;
  canAssign: boolean; canArchive: boolean; loading: boolean; tools?: ReactNode;
}) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [assigneeNames, setAssigneeNames] = useState<Record<string, string>>({});
  const [panelOpen, setPanelOpen] = useState(false);
  const applied = new URLSearchParams(value);
  const advancedCount = ADVANCED.filter(key => applied.has(key)).length;
  const dirty = Object.values(draft).some(entry => entry.trim());
  function update(key: string, next: string) { setDraft(current => ({ ...current, [key]: next })); }
  function applyDraft() {
    const params = new URLSearchParams();
    for (const [key, entry] of Object.entries(draft)) if (entry.trim() && !(key === "archived" && entry === "false")) params.set(key, entry.trim());
    onChange(params.toString());
    setPanelOpen(false);
  }
  function clearAll() { setDraft({}); onChange(""); setPanelOpen(false); }
  function remove(key: string) {
    applied.delete(key);
    setDraft(current => ({ ...current, [key]: "" }));
    onChange(applied.toString());
  }
  function select(key: string, placeholder: string, entries: { value: string; label: string }[]) {
    return <label><span className="lead-filter-label">{labels[key]}</span><select className="select" name={key} value={draft[key] || ""} onChange={event => update(key, event.target.value)}><option value="">{placeholder}</option>{entries.map(entry => <option key={entry.value} value={entry.value}>{entry.label}</option>)}</select></label>;
  }
  function text(key: string, maxLength = 200) {
    return <label>{labels[key]}<input className="input" name={key} maxLength={maxLength} value={draft[key] || ""} onChange={event => update(key, event.target.value)} /></label>;
  }
  function dateRange(title: string, from: string, to: string) {
    return <div className="lead-date-range"><span>{title}</span><div><DatePicker ariaLabel={labels[from]} placeholder="From" value={draft[from] || ""} max={draft[to] || undefined} onChange={next => update(from, next)} /><span className="lead-date-sep">to</span><DatePicker ariaLabel={labels[to]} placeholder="To" value={draft[to] || ""} min={draft[from] || undefined} onChange={next => update(to, next)} /></div></div>;
  }
  function display(key: string, entry: string) {
    if (key === "status_id") return options?.statuses.find(status => status.id === entry)?.name || entry;
    if (key === "assignee") return assigneeNames[entry] || entry;
    if (key === "integration_id") return options?.accounts.find(account => account.id === entry)?.name || entry;
    return key === "archived" ? "Archived" : entry;
  }
  return <form className="lead-filters" onSubmit={event => { event.preventDefault(); applyDraft(); }}>
    <div className="lead-filter-primary">
      <label className="lead-search"><span className="lead-filter-label">Search</span><div className="lead-search-input"><Icon name="search" /><input className="input" name="q" placeholder="Search leads" maxLength={200} value={draft.q || ""} onChange={event => update("q", event.target.value)} /></div></label>
      {select("status_id", "All statuses", options?.statuses.map(status => ({ value: status.id, label: status.name })) || [])}
      {canAssign && <LeadAssignmentPicker path="/leads/assignees" label="Assigned to" value={draft.assignee || ""} emptyLabel="All assignees" onChange={(id, name) => { update("assignee", id); setAssigneeNames(current => ({ ...current, [id]: name })); }} />}
      <Popover open={panelOpen} onOpenChange={setPanelOpen}>
        <PopoverTrigger asChild><Button variant="outline" size="sm" className="lead-more-filters"><Icon name="filter" />More filters{advancedCount > 0 && <span className="badge">{advancedCount}</span>}</Button></PopoverTrigger>
        <PopoverContent className="lead-filter-panel" onOpenAutoFocus={event => event.preventDefault()}>
          <div className="lead-filter-panel-head"><strong>More filters</strong><span className="small muted">Combine any of these with the filters above</span></div>
          <div className="lead-filter-grid">
            {select("source", "All sources", options?.sources.map(source => ({ value: source, label: source })) || [])}
            {select("integration_id", "All accounts", options?.accounts.map(account => ({ value: account.id, label: account.name })) || [])}
            {text("source_record_id")}{text("tag", 50)}
            {dateRange("Received", "start", "end")}
            {dateRange("Status updated", "status_start", "status_end")}
            {canArchive && select("archived", "Active", [{ value: "true", label: "Archived" }])}
          </div>
          <div className="lead-filter-panel-foot"><Button variant="ghost" size="sm" onClick={() => setDraft(current => ({ ...current, ...Object.fromEntries(ADVANCED.map(key => [key, ""])) }))}>Reset these</Button><Button size="sm" onClick={applyDraft} disabled={loading}>Apply filters</Button></div>
        </PopoverContent>
      </Popover>
      <div className="lead-filter-actions">
        <Button type="submit" size="sm" disabled={loading || (!dirty && !value)}><Icon name="check" />Apply</Button>
        <Button variant="ghost" size="sm" disabled={!value && !dirty} onClick={clearAll}>Clear all</Button>
      </div>
      {tools && <div className="lead-filter-tools">{tools}</div>}
    </div>
    {value && <div className="lead-filter-chips" aria-label="Applied filters">{[...applied].map(([key, entry]) => <button type="button" className="lead-filter-chip" key={key} onClick={() => remove(key)} aria-label={`Remove ${labels[key]} filter`}>{labels[key]}: {display(key, entry)}<Icon name="close" size={12} /></button>)}</div>}
  </form>;
}
