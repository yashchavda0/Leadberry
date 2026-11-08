"use client";

import { useState } from "react";
import RoleList from "@/components/permissions/RoleList";
import RolePermissionDetail from "@/components/permissions/RolePermissionDetail";
import { type Permission, type Role } from "@/lib/crm";

export default function RolePermissionsView({ catalog, onEdit }: { catalog: Permission[]; onEdit: (role: Role) => void }) {
  const [role, setRole] = useState<Role | null>(null);
  return <div className="perm-layout">
    <RoleList selectedId={role?.id} onSelect={setRole} />
    {role ? <RolePermissionDetail key={role.id} role={role} catalog={catalog} onEdit={onEdit} /> : <div className="perm-detail empty-state"><h3>Select a role</h3><p className="muted">Pick a role to see which permissions it grants.</p></div>}
  </div>;
}
