"use client";

import { useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";
import SearchInput from "@/components/SearchInput";
import { Pagination } from "@/components/Ui";
import { Badge } from "@/components/ui/badge";
import { type Role } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

// Searchable role cards; selections persist across search and pages.
export default function RolePicker({ values, onChange, single = false }: { values: string[]; onChange: (ids: string[]) => void; single?: boolean }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const names = useRef(new Map<string, Role>());
  useEffect(() => { const timer = setTimeout(() => setSearch(query.trim()), 300); return () => clearTimeout(timer); }, [query]);
  const list = usePaged<Role>(`/roles${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  for (const role of list.data?.data || []) names.current.set(role.id, role);
  const toggle = (role: Role, on: boolean) => onChange(on ? (single ? [role.id] : [...new Set([...values, role.id])]) : values.filter(id => id !== role.id));
  return <div className="role-picker">
    <div className="role-picker-top">
      <SearchInput value={query} onChange={setQuery} placeholder="Search roles" />
      {values.length > 0 && <button type="button" className="permission-group-action" onClick={() => onChange([])}>Clear all</button>}
    </div>
    <div className="role-picker-selected" aria-live="polite">
      {values.length ? values.map(id => <span key={id} className="role-chip">{names.current.get(id)?.name || "Role"}<button type="button" aria-label={`Remove ${names.current.get(id)?.name || "role"}`} onClick={() => onChange(values.filter(value => value !== id))}><Icon name="close" size={12} /></button></span>)
        : <span className="small muted">No role selected yet. Pick one or more below.</span>}
    </div>
    <div className="role-grid">
      {list.loading && !list.data ? Array.from({ length: 6 }, (_, index) => <span key={index} className="skeleton role-skeleton" />)
        : list.data?.data.length ? list.data.data.map(role => {
          const selected = values.includes(role.id);
          const locked = !role.is_active && !selected;
          return <label key={role.id} className={`role-card${selected ? " selected" : ""}${locked ? " locked" : ""}`}>
            <input type={single ? "radio" : "checkbox"} checked={selected} disabled={locked} onChange={event => toggle(role, event.target.checked)} />
            <span className="role-card-check" aria-hidden="true"><Icon name="check" size={14} /></span>
            <span className="role-card-body"><strong>{role.name}</strong><span className="small muted">{role.description || `${role.permissions.length} permissions`}</span>
              <span className="role-card-meta"><Badge variant="outline">Level {role.level}</Badge><Badge variant="info">{role.data_scope}</Badge>{!role.is_active && <Badge variant="warning">Inactive</Badge>}</span></span>
          </label>;
        }) : <p className="small muted">No roles match your search.</p>}
    </div>
    <Pagination list={list} />
  </div>;
}
