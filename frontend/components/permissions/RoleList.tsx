"use client";

import { useEffect, useState } from "react";
import { Loading, Pagination } from "@/components/Ui";
import SearchInput from "@/components/SearchInput";
import { type Role } from "@/lib/crm";
import { usePaged } from "@/lib/hooks";

export default function RoleList({ selectedId, onSelect }: { selectedId?: string; onSelect: (role: Role) => void }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setSearch(query.trim()), 300);
    return () => clearTimeout(timer);
  }, [query]);
  const list = usePaged<Role>(`/roles${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  return <aside className="perm-roles" aria-label="Roles">
    <SearchInput placeholder="Search roles" value={query} onChange={setQuery} />
    <div className="perm-roles-list">
      {list.loading ? <Loading /> : list.data?.data.length ? list.data.data.map(role =>
        <button key={role.id} type="button" className="perm-role-item" aria-current={role.id === selectedId ? "true" : undefined} onClick={() => onSelect(role)}>
          <span><strong>{role.name}</strong><span className="small muted"> Level {role.level}</span></span>
          <span className="badge">{role.permissions.length}</span>
        </button>) : <p className="small muted">No roles found.</p>}
    </div>
    <Pagination page={list.page} previous={list.previous} next={list.next} hasPrevious={list.hasPrevious} hasNext={Boolean(list.data?.next_cursor)} loading={list.loading} />
  </aside>;
}
