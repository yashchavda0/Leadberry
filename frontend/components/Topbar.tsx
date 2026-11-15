"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Icon from "./Icon";
import { NAV } from "./Sidebar";
import { useSession } from "./Session";
import { Badge } from "./ui/badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./ui/dropdown-menu";

const TITLES: Record<string, string> = { "/account": "My account" };

export default function Topbar() {
  const { identity, organization, can, logout } = useSession();
  const pathname = usePathname();
  const title = TITLES[pathname] || NAV.find(link => (link.href === "/" ? pathname === "/" : pathname.startsWith(link.href)))?.label || "Workspace";
  const today = new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  const initials = (organization?.name || "?").split(/\s+/).map(word => word[0]).join("").slice(0, 2).toUpperCase();
  return <header className="topbar topbar-v2">
    <div className="topbar-title"><h2>{title}</h2><span className="small muted">{today}</span></div>
    <div className="topbar-right">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" className="topbar-user" aria-label="Account menu">
            <span className="topbar-avatar" aria-hidden="true">{initials}</span>
            <span className="topbar-user-text"><strong>{organization?.name}</strong><small>{organization?.slug}</small></span>
            <Badge variant={identity?.is_owner ? "default" : "outline"}>{identity?.is_owner ? "Owner" : "Member"}</Badge>
            <Icon name="chevron" size={14} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuLabel>{organization?.name}</DropdownMenuLabel>
          <DropdownMenuItem asChild><Link href="/account"><Icon name="user" size={16} />My account</Link></DropdownMenuItem>
          {can("settings.view") && <DropdownMenuItem asChild><Link href="/settings"><Icon name="building" size={16} />Organization settings</Link></DropdownMenuItem>}
          <DropdownMenuSeparator />
          <DropdownMenuItem destructive onSelect={() => void logout()}><Icon name="logout" size={16} />Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  </header>;
}
