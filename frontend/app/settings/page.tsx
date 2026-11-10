"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Guard, useSession } from "@/components/Session";
import { useNotify } from "@/components/Notifications";
import Icon, { type IconName } from "@/components/Icon";
import { Field } from "@/components/Ui";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { crm, errorMessage } from "@/lib/crm";
import { COMPANY_SIZES as SIZES, COUNTRIES, CURRENCIES, INDUSTRIES } from "@/lib/organization";

const SECTIONS = [
  { id: "company", label: "Company", icon: "leads" },
  { id: "contact", label: "Contact", icon: "plug" },
  { id: "address", label: "Address", icon: "filter" },
  { id: "regional", label: "Regional & tax", icon: "calendar" },
  { id: "workspace", label: "Lead setup", icon: "settings" },
] as const satisfies readonly { id: string; label: string; icon: IconName }[];

export default function SettingsPage() { return <Guard permission="settings.view"><Settings /></Guard>; }

function Settings() {
  const { organization, can, reload } = useSession();
  const notify = useNotify();
  const form = useRef<HTMLFormElement>(null);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [logoBroken, setLogoBroken] = useState(false);
  const editable = can("settings.manage");
  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try { await crm("/organizations/me", { method: "PUT", body: JSON.stringify(values) }); await reload(); setDirty(false); setLogoBroken(false); notify.success("Organization updated."); }
    catch (problem) { notify.error(errorMessage(problem), { title: "Settings could not be saved" }); }
    finally { setBusy(false); }
  }
  const value = (name: string) => (organization?.[name as keyof typeof organization] as string | null) || "";
  const text = (name: string, label: string, props: { hint?: string; max?: number; type?: string; required?: boolean; placeholder?: string; wide?: boolean } = {}) => (
    <div className={props.wide ? "span-2" : undefined}><Field label={label} hint={props.hint}><input className="input" name={name} type={props.type || "text"} maxLength={props.max || 200} required={props.required} placeholder={props.placeholder} defaultValue={value(name)} disabled={!editable} /></Field></div>
  );
  const choice = (name: string, label: string, options: [string, string][], blank?: string) => (
    <Field label={label}><select className="select" name={name} defaultValue={value(name) || (blank ? "" : options[0][0])} disabled={!editable}>{blank && <option value="">{blank}</option>}{options.map(([key, display]) => <option key={key} value={key}>{display}</option>)}</select></Field>
  );
  const initials = (organization?.name || "?").split(/\s+/).map(word => word[0]).join("").slice(0, 2).toUpperCase();
  return <>
    <div className="page-header"><div><span className="eyebrow">WORKSPACE CONFIGURATION</span><h1>Organization settings</h1><p className="muted">Your company profile, contact details and regional settings.</p></div></div>

    <Card className="org-hero">
      <div className="org-avatar" aria-hidden="true">{initials}{organization?.logo_url && !logoBroken && /* eslint-disable-next-line @next/next/no-img-element */ <img src={organization.logo_url} alt="" onError={() => setLogoBroken(true)} />}</div>
      <div className="org-hero-text">
        <h2>{organization?.name}</h2>
        <div className="org-hero-meta"><Badge variant="outline">{organization?.slug}</Badge><Badge variant={organization?.status === "active" ? "success" : "warning"} dot>{organization?.status}</Badge>{organization?.industry && <span className="small muted">{organization.industry}</span>}{organization?.city && <span className="small muted">{organization.city}</span>}</div>
      </div>
      <div className="org-hero-facts"><span><small>Timezone</small><strong>{organization?.timezone}</strong></span><span><small>Currency</small><strong>{organization?.currency}</strong></span></div>
    </Card>

    <div className="org-layout">
      <nav className="org-nav" aria-label="Settings sections">{SECTIONS.map(section => <a key={section.id} href={`#${section.id}`}><Icon name={section.icon} size={16} />{section.label}</a>)}</nav>
      <div className="org-content">
        <form ref={form} className="org-form" onSubmit={save} onChange={() => setDirty(true)} key={organization?.id}>
          <Card id="company"><CardHeader><CardTitle>Company</CardTitle><CardDescription>Shown in the app and on exports.</CardDescription></CardHeader>
            <CardContent className="org-grid">
              <Field label="Workspace slug" hint="Used to sign in. Cannot be changed."><input className="input" disabled value={organization?.slug || ""} /></Field>
              {text("name", "Organization name", { required: true })}
              {text("logo_url", "Logo address", { hint: "A hosted image link starting with https://", max: 500, type: "url", placeholder: "https://", wide: true })}
              {text("website", "Website", { max: 300, type: "url", placeholder: "https://" })}
              {choice("industry", "Industry", INDUSTRIES.map(item => [item, item]), "Select industry")}
              {choice("company_size", "Company size", SIZES.map(item => [item, `${item} people`]), "Select size")}
            </CardContent></Card>
          <Card id="contact"><CardHeader><CardTitle>Contact</CardTitle><CardDescription>Used for billing, notifications and support.</CardDescription></CardHeader>
            <CardContent className="org-grid">{text("business_email", "Business email", { type: "email", max: 320 })}{text("business_phone", "Business phone", { type: "tel", max: 20, hint: "Digits, spaces, + ( ) and -" })}</CardContent></Card>
          <Card id="address"><CardHeader><CardTitle>Address</CardTitle><CardDescription>Appears on invoices and tax documents.</CardDescription></CardHeader>
            <CardContent className="org-grid">{text("address", "Street address", { max: 500, wide: true })}{text("city", "City", { max: 100 })}{text("state", "State / province", { max: 100 })}{text("postal_code", "PIN / postal code", { max: 12 })}{choice("country", "Country", COUNTRIES)}</CardContent></Card>
          <Card id="regional"><CardHeader><CardTitle>Regional and tax</CardTitle><CardDescription>Controls dashboard days, money formatting and invoices.</CardDescription></CardHeader>
            <CardContent className="org-grid">{text("timezone", "Timezone", { required: true, hint: "IANA name, for example Asia/Kolkata." })}{choice("currency", "Currency", CURRENCIES.map(code => [code, code]))}{text("gstin", "GSTIN (optional)", { max: 15, placeholder: "22AAAAA0000A1Z5", hint: "15 characters, capital letters and digits." })}</CardContent></Card>
          {editable && <div className={`org-savebar${dirty ? " dirty" : ""}`}>
            <span className="small">{dirty ? "You have unsaved changes" : "All changes saved"}</span>
            <div><Button type="button" variant="ghost" disabled={!dirty || busy} onClick={() => { form.current?.reset(); setDirty(false); }}>Discard</Button><Button type="submit" disabled={!dirty || busy}>{busy ? "Saving..." : "Save settings"}</Button></div>
          </div>}
        </form>

        <Card id="workspace"><CardHeader><CardTitle>Lead setup</CardTitle><CardDescription>Configure how leads move through your team.</CardDescription></CardHeader>
          <CardContent className="org-tiles">
            <Link className="org-tile" href="/settings/lead-statuses"><span className="org-tile-icon"><Icon name="check" size={18} /></span><span><strong>Lead statuses</strong><small>Statuses, required fields and assignment rules</small></span><Icon name="chevronRight" size={16} /></Link>
            <Link className="org-tile" href="/settings/lead-fields"><span className="org-tile-icon"><Icon name="edit" size={18} /></span><span><strong>Custom lead fields</strong><small>Extra details to capture on every lead</small></span><Icon name="chevronRight" size={16} /></Link>
          </CardContent></Card>
      </div>
    </div>
  </>;
}
