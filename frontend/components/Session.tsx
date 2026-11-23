"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, crm, errorMessage, isServiceError, type Identity, type Organization } from "@/lib/crm";
import ServiceUnavailable from "./ServiceUnavailable";
import PageLoader from "./PageLoader";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";

type Session = {
  identity: Identity | null; organization: Organization | null; pending: boolean; error: string;
  reload: () => Promise<Identity | null>; can: (permission: string) => boolean; logout: () => Promise<void>;
};
const Context = createContext<Session | null>(null);
const publicPaths = ["/login", "/onboarding", "/accept-invite", "/platform/login"];

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
  const [outage, setOutage] = useState<{ offline: boolean } | null>(null);
  const [retrying, setRetrying] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const isPublic = publicPaths.includes(pathname);
  const isPlatform = pathname.startsWith("/platform");
  const reload = useCallback(async () => {
    setError(""); setOutage(null);
    try {
      const current = await crm<Identity>("/auth/me");
      setIdentity(current);
      if (current.password_change_required) {
        setOrganization(null);
        return current;
      }
      const org = await crm<Organization>("/organizations/me");
      setIdentity(current); setOrganization(org);
      return current;
    } catch (error) {
      setIdentity(null); setOrganization(null);
      if (!(error instanceof ApiError && error.status === 401)) setError(errorMessage(error));
      if (isServiceError(error)) setOutage({ offline: (error as ApiError).status === 0 });
      return null;
    } finally { setPending(false); }
  }, []);
  useEffect(() => { if (!isPlatform) void reload(); else setPending(false); }, [isPlatform, reload]);
  useEffect(() => {
    const expire = () => { setIdentity(null); setOrganization(null); setError(""); setPending(false); };
    window.addEventListener("crm-session-expired", expire);
    return () => window.removeEventListener("crm-session-expired", expire);
  }, []);
  async function retry() { setRetrying(true); await reload(); setRetrying(false); }
  useEffect(() => {
    if (!isPublic && !isPlatform && !pending && !identity && !error) router.replace("/login");
  }, [isPublic, isPlatform, pending, identity, error, router]);
  useEffect(() => {
    if (!isPublic && !isPlatform && !pending && identity?.password_change_required && pathname !== "/password-change") {
      router.replace("/password-change");
    }
  }, [isPublic, isPlatform, pending, identity, pathname, router]);
  useEffect(() => {
    const focus = () => { if (!isPublic && !isPlatform) void reload(); };
    window.addEventListener("focus", focus);
    return () => window.removeEventListener("focus", focus);
  }, [isPublic, isPlatform, reload]);
  async function logout() {
    await crm<void>("/auth/logout", { method: "POST" });
    setIdentity(null); setOrganization(null); router.replace("/login");
  }
  const value: Session = { identity, organization, pending, error, reload, can: permission => Boolean(identity?.permissions.includes(permission)), logout };
  return <Context.Provider value={value}>
    {isPlatform || isPublic ? children : pending ? <PageLoader label="Loading your workspace..." /> :
      error ? (outage ? <ServiceUnavailable message={error} offline={outage.offline} retrying={retrying} onRetry={() => void retry()} /> : <div className="auth-container"><div className="card"><h1>Organization access unavailable</h1><p role="alert">{error}</p><button className="btn" onClick={() => void reload()}>Retry</button> <Link href="/login">Sign in</Link></div></div>) :
        identity ? <div className="layout"><Sidebar /><div className="workspace"><Topbar />{identity.access_mode === "export_only" && <div className="subscription-readonly" role="status">Subscription ended. Your organization is in read-only mode; data export remains available.</div>}<main className="main">{children}</main></div></div> :
          <PageLoader label="Redirecting to sign in..." />}
  </Context.Provider>;
}

export function Guard({ permission, children }: { permission: string; children: React.ReactNode }) {
  const { can } = useSession();
  return can(permission) ? children : <div className="card"><h1>Access restricted</h1><p>You need <code>{permission}</code> to open this page. Contact an organization Owner.</p><Link href="/account">View your access</Link></div>;
}
