"use client";

import { useState } from "react";
import ColumnActions from "@/components/ColumnActions";
import Icon from "@/components/Icon";
import SearchInput from "@/components/SearchInput";
import ScrollArea from "@/components/ScrollArea";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export type StatusItem = { id: string; name: string; color: string; is_active: boolean };

// Lets users choose which status columns to show; scales to hundreds of statuses via search.
export default function StatusColumnPicker({ statuses, selected, onChange, onReset }: { statuses: StatusItem[]; selected: string[]; onChange: (ids: string[]) => void; onReset: () => void }) {
  const [query, setQuery] = useState("");
  const term = query.trim().toLowerCase();
  const visible = statuses.filter(status => !term || status.name.toLowerCase().includes(term));
  const toggle = (id: string, on: boolean) => onChange(on ? [...new Set([...selected, id])] : selected.filter(item => item !== id));
  return <Popover>
    <PopoverTrigger asChild><Button variant="outline" size="sm"><Icon name="settings" />Status columns <span className="badge">{selected.length}/{statuses.length}</span></Button></PopoverTrigger>
    <PopoverContent className="status-picker" align="end">
      <SearchInput value={query} onChange={setQuery} placeholder="Search statuses" />
      <ColumnActions onShowAll={() => onChange(statuses.map(status => status.id))} onClear={() => onChange([])} onReset={onReset} />
      <ScrollArea maxHeight="min(320px, 50vh)" label="Statuses">
        {visible.length ? visible.map(status => <label className="status-picker-row" key={status.id}>
          <input type="checkbox" checked={selected.includes(status.id)} onChange={event => toggle(status.id, event.target.checked)} />
          <span className="status-dot" style={{ background: status.color }} />
          <span>{status.name}</span>{!status.is_active && <span className="small muted">inactive</span>}
        </label>) : <p className="small muted">No statuses match.</p>}
      </ScrollArea>
      <p className="small muted">Statuses you hide are added together in an "Other statuses" column.</p>
    </PopoverContent>
  </Popover>;
}
