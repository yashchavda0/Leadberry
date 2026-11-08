"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, crm, errorMessage, type Identity, type Organization } from "@/lib/crm";
import Sidebar from "./Sidebar";

type Session = {
  identity: Identity | null; organization: Organization | null; pending: boolean; error: string;
  reload: () => Promise<Identity | null>; can: (permission: string) => boolean; logout: () => Promise<void>;
};
const Context = createContext<Session | null>(null);
const publicPaths = ["/login", "/onboarding", "/accept-invite"];

export function useSession() {
  const session = useContext(Context);
  if (!session) throw new Error("Session provider is missing");
  return session;
}

export default function SessionProvider({ children }: { children: React.ReactNode }) {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [organization, setOrganization] = useState<Organization | null>(null);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState("");
  const router = useRouter();
  const pathname = usePathname();
  const isPublic = publicPaths.includes(pathname);
  const reload = useCallback(async () => {
    setError("");
    try {
      const current = await crm<Identity>("/auth/me");
      const org = await crm<Organization>("/organizations/me");
      setIdentity(current); setOrganization(org);
      return current;
    } catch (error) {
      setIdentity(null); setOrganization(null);
      if (!(error instanceof ApiError && error.status === 401)) setError(errorMessage(error));
      return null;
    } finally { setPending(false); }
  }, []);
  useEffect(() => { void reload(); }, [reload]);
  useEffect(() => {
    const expire = () => { setIdentity(null); setOrganization(null); setError(""); setPending(false); };
    window.addEventListener("crm-session-expired", expire);
    return () => window.removeEventListener("crm-session-expired", expire);
  }, []);
  useEffect(() => {
    if (!isPublic && !pending && !identity && !error) router.replace("/login");
  }, [isPublic, pending, identity, error, router]);
  useEffect(() => {
    const focus = () => { if (!isPublic) void reload(); };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [isPublic, reload]);
  async function logout() {
    await crm<void>("/auth/logout", { method: "POST" });
    setIdentity(null); setOrganization(null); router.replace("/login");
  }
  const value: Session = { identity, organization, pending, error, reload, can: permission => Boolean(identity?.permissions.includes(permission)), logout };
  return <Context.Provider value={value}>
    {isPublic ? children : pending ? <div className="loading-screen" role="status">Loading your workspace...</div> :
      error ? <div className="auth-container"><div className="card"><h1>Workspace unavailable</h1><p role="alert">{error}</p><button className="btn" onClick={() => void reload()}>Retry</button> <Link href="/login">Sign in</Link></div></div> :
        identity ? <div className="layout"><Sidebar /><div className="workspace"><header className="topbar"><div><strong>{organization?.name}</strong><span className="muted small"> / {organization?.slug}</span></div><Link href="/account">{identity.is_owner ? "Owner" : "Member"} <span className="badge">{identity.data_scope} scope</span></Link></header><main className="main">{children}</main></div></div> :
          <div className="loading-screen">Redirecting to sign in...</div>}
  </Context.Provider>;
}

export function Guard({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { can } = useSession();
  return can(permission) ? children : <div className="card"><h1>Access restricted</h1><p>You need <code>{permission}</code> to open this page. Contact an organization Owner.</p><Link href="/account">View your access</Link></div>;
}
