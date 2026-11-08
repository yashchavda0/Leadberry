"use client";

import { useState } from "react";
import Link from "next/link";
import { Guard, useSession } from "@/components/Session";
import { ErrorNotice, Field } from "@/components/Ui";
import { crm, errorMessage } from "@/lib/crm";

export default function SettingsPage() { return <Guard permission="settings.view"><Settings /></Guard>; }
function Settings() {
  const { organization, can, reload } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSaved(false);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try { await crm("/organizations/me", { method: "PUT", body: JSON.stringify(values) }); await reload(); setSaved(true); }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <><div className="page-header"><div><span className="eyebrow">WORKSPACE CONFIGURATION</span><h1>Organization settings</h1><p className="muted">Keep your organization profile and reporting timezone accurate.</p></div></div><form className="card narrow-card" onSubmit={save}><ErrorNotice error={error} />{saved && <div className="alert alert-success" role="status">Organization updated.</div>}<Field label="Workspace slug" hint="Immutable in this phase."><input className="input" disabled value={organization?.slug || ""} /></Field><Field label="Organization name"><input className="input" name="name" required maxLength={200} defaultValue={organization?.name || ""} disabled={!can("settings.manage")} /></Field><Field label="IANA timezone" hint="For example Asia/Kolkata, Europe/London or America/New_York. Used for dashboard day boundaries."><input className="input" name="timezone" defaultValue={organization?.timezone || "Asia/Kolkata"} required disabled={!can("settings.manage")} /></Field>{can("settings.manage") && <button className="btn btn-primary" disabled={busy}>{busy ? "Saving..." : "Save settings"}</button>}</form><div className="settings-link-list"><Link className="btn" href="/settings/lead-statuses">Lead statuses and assignment rules</Link><Link className="btn" href="/settings/lead-fields">Custom lead fields</Link></div></>;
}
