"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "./Session";

const links = [
  { href: "/", label: "Overview", permission: "dashboard.view" },
  { href: "/leads", label: "Leads", permission: "leads.view" },
  { href: "/users", label: "User management", permission: "users.view" },
  { href: "/marketplace", label: "Marketplace", permission: "marketplace.view" },
  { href: "/settings", label: "Organization", permission: "settings.view" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { can } = useSession();
  return (
    <aside className="sidebar">
      <div className="brand">
        Lead<span>Berry</span>
      </div>
      <nav className="nav">
        {links.filter(l => can(l.permission) || l.href === "/users" && can("roles.view")).map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link key={l.href} href={l.href} className={active ? "active" : ""}>
              {l.label}
            </Link>
          );
        })}
        <Link href="/account" className={pathname === "/account" ? "active" : ""}>My account</Link>
      </nav>
      <div className="sidebar-footer"><span className="badge">PostgreSQL workspace</span><p className="small">Tenant-isolated data.<br />Access enforced by the API.</p></div>
    </aside>
  );
}
