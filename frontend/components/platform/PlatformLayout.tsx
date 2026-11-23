"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { crm, errorMessage, type PlatformOperatorIdentity } from "@/lib/crm";
import { Button } from "@/components/ui/button";
import Icon from "@/components/Icon";
import { Loading } from "@/components/Ui";

type PlatformSessionValue = {
  operator: PlatformOperatorIdentity | null;
  reload: () => Promise<void>;
};
const PlatformSessionContext = createContext<PlatformSessionValue | null>(null);

export function usePlatformSession() {
  const value = useContext(PlatformSessionContext);
  if (!value) throw new Error("Platform layout is missing");
  return value;
}

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const loginPage = pathname === "/platform/login";
  const [operator, setOperator] = useState<PlatformOperatorIdentity | null>(null);
  const [pending, setPending] = useState(!loginPage);
  const [error, setError] = useState("");

  async function reload() {
    setError("");
    try {
      setOperator(await crm<PlatformOperatorIdentity>("/platform/me"));
    } catch (reason) {
      setOperator(null);
      if (reason instanceof Error && "status" in reason && reason.status === 401) {
        router.replace("/platform/login");
      } else {
        setError(errorMessage(reason));
      }
    } finally {
      setPending(false);
    }
  }

  useEffect(() => {
    if (!loginPage) void reload();
  }, [loginPage]);
  useEffect(() => {
    const expire = () => { setOperator(null); router.replace("/platform/login"); };
    window.addEventListener("platform-session-expired", expire);
    return () => window.removeEventListener("platform-session-expired", expire);
  }, [router]);

  async function logout() {
    await crm<void>("/platform/logout", { method: "POST" });
    setOperator(null);
    router.replace("/platform/login");
  }

  if (loginPage) return <>{children}</>;
  if (pending) return <div className="platform-loading"><Loading /></div>;
  if (error) return <div className="platform-loading"><p role="alert">{error}</p><Button variant="outline" onClick={() => void reload()}>Retry</Button></div>;
  if (!operator) return <div className="platform-loading"><Loading /></div>;

  return <PlatformSessionContext.Provider value={{ operator, reload }}>
    <div className="platform-frame">
      <header className="platform-header">
        <Link href="/platform" className="platform-brand"><span className="platform-brand-mark">LB</span><span>Platform control</span></Link>
        <div className="platform-account"><span><strong>{operator.full_name}</strong><small>{operator.access_level} · {operator.email}</small></span><Button variant="outline" size="sm" onClick={() => void logout()}><Icon name="logout" size={16} />Sign out</Button></div>
      </header>
      <nav className="platform-nav" aria-label="Platform administration">
        <Link href="/platform" aria-current={pathname === "/platform" ? "page" : undefined}><Icon name="building" size={16} />Organizations</Link>
        <Link href="/platform/audit" aria-current={pathname.startsWith("/platform/audit") ? "page" : undefined}><Icon name="history" size={16} />Audit log</Link>
      </nav>
      <main className="platform-main">{children}</main>
    </div>
  </PlatformSessionContext.Provider>;
}