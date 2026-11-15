"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import Icon, { type IconName } from "./Icon";
import { useSession } from "./Session";
import { Tip } from "./ui/tip";

export const NAV: { href: string; label: string; permission: string; icon: IconName }[] = [
  { href: "/", label: "Overview", permission: "dashboard.view", icon: "dashboard" },
  { href: "/leads", label: "Leads", permission: "leads.view", icon: "target" },
  { href: "/settings/lead-statuses", label: "Lead statuses", permission: "settings.view", icon: "check" },
  { href: "/settings/lead-fields", label: "Custom fields", permission: "settings.view", icon: "panel" },
  { href: "/users", label: "User management", permission: "users.view", icon: "leads" },
  { href: "/marketplace", label: "Marketplace", permission: "marketplace.view", icon: "store" },
  { href: "/reports", label: "Reports", permission: "reports.view", icon: "chart" },
  { href: "/settings", label: "Organization", permission: "settings.view", icon: "building" },
];
const STORAGE_KEY = "crm.sidebar-collapsed";

export default function Sidebar() {
  const pathname = usePathname();
  const { can, identity } = useSession();
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => { try { setCollapsed(localStorage.getItem(STORAGE_KEY) === "1"); } catch { /* preference unavailable */ } }, []);
  function toggle() {
    setCollapsed(value => { try { localStorage.setItem(STORAGE_KEY, value ? "0" : "1"); } catch { /* ignore */ } return !value; });
  }
  const item = (href: string, label: string, icon: IconName, active: boolean) => {
    const link = <Link key={href} href={href} className={`nav-link${active ? " active" : ""}`} aria-label={collapsed ? label : undefined} aria-current={active ? "page" : undefined}><Icon name={icon} size={20} /><span className="nav-label">{label}</span></Link>;
    return collapsed ? <Tip key={href} label={label} side="right">{link}</Tip> : link;
  };
  const links = NAV.filter(link => can(link.permission) || link.href === "/users" && can("roles.view"));
  const activeHref = links.filter(link => pathname === link.href || link.href !== "/" && pathname.startsWith(`${link.href}/`)).sort((first, second) => second.href.length - first.href.length)[0]?.href;
  return (
    <aside className={`sidebar${collapsed ? " collapsed" : ""}`}>
      <div className="sidebar-head">
        <Link href="/" className="brand" aria-label="LeadBerry home"><span className="brand-mark">LB</span><span className="brand-text nav-label">Lead<span>Berry</span></span></Link>
      </div>
      <span className="nav-section nav-label">Menu</span>
      <nav className="nav" aria-label="Main">
        {links.map(link => item(link.href, link.label, link.icon, link.href === activeHref))}
      </nav>
      <div className="sidebar-footer">
        <span className="nav-section nav-label">Account</span>
        {item("/account", "My account", "user", pathname === "/account")}
        <div className="sidebar-user">
          <span className="sidebar-user-badge">{identity?.is_owner ? "Owner" : "Member"}</span>
          <span className="sidebar-user-text nav-label">{identity?.is_owner ? "Full access" : "Access by role"}</span>
        </div>
        <Tip label={collapsed ? "Expand sidebar" : "Collapse sidebar"} side="right">
          <button type="button" className="sidebar-toggle" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={toggle}><Icon name="chevronLeft" size={18} /><span className="nav-label">Collapse</span></button>
        </Tip>
      </div>
    </aside>
  );
}
