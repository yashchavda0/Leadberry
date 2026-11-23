"use client";

import { useState } from "react";
import LeadAssignmentPicker from "@/components/LeadAssignmentPicker";
import { useNotify } from "@/components/Notifications";
import { ErrorNotice, Loading } from "@/components/Ui";
import { Button } from "@/components/ui/button";
import { crm, errorMessage } from "@/lib/crm";
import { useResource } from "@/lib/hooks";

type Source = "website" | "indiamart" | "tradeindia";
type Rule = { source: Source; team_id: string; team_name: string; team_active: boolean; enabled: boolean };
type Preview = { reason: "no_rule" | "team_inactive" | "no_eligible_member" | "assigned"; member_name?: string };
const sources: { id: Source; name: string }[] = [{ id: "website", name: "Website API" }, { id: "indiamart", name: "IndiaMART" }, { id: "tradeindia", name: "TradeIndia" }];

export default function AssignmentRules() {
  const rules = useResource<{ data: Rule[] }>("/assignment-rules");
  return <section className="intake-section"><div className="intake-section-header"><h2>Source assignment</h2></div><ErrorNotice error={rules.error} />
    {rules.loading ? <Loading /> : <div className="routing-list">{sources.map(source => {
      const rule = rules.data?.data.find(item => item.source === source.id);
      return <SourceRule key={`${source.id}-${rule?.team_id || "none"}-${rule?.enabled}`} source={source} rule={rule} onSaved={rules.reload} />;
    })}</div>}
  </section>;
}

function SourceRule({ source, rule, onSaved }: { source: { id: Source; name: string }; rule?: Rule; onSaved: () => void }) {
  const notify = useNotify();
  const [team, setTeam] = useState(rule?.team_id || "");
  const [enabled, setEnabled] = useState(rule?.enabled ?? true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try { await crm(`/assignment-rules/${source.id}`, { method: "PUT", body: JSON.stringify({ team_id: team, enabled }) }); setPreview(null); onSaved(); notify.success(`${source.name} assignment saved.`); }
    catch (error) { notify.error(errorMessage(error), { title: "Assignment rule could not be saved" }); }
    finally { setBusy(false); }
  }
  async function inspect() {
    setBusy(true);
    try { setPreview(await crm<Preview>(`/assignment-rules/${source.id}/preview`)); }
    catch (error) { notify.error(errorMessage(error), { title: "Preview unavailable" }); }
    finally { setBusy(false); }
  }
  const text = preview?.reason === "assigned" ? `Next: ${preview.member_name}` : preview?.reason === "team_inactive" ? "Team inactive; leads remain unassigned." : preview?.reason === "no_eligible_member" ? "No eligible team member; leads remain unassigned." : preview ? "No active rule; leads remain unassigned." : "";
  return <div className="routing-row"><div><h3>{source.name}</h3><span className="small muted">{rule ? rule.enabled ? rule.team_active ? "Active" : "Team inactive" : "Disabled" : "Not configured"}</span></div>
    <LeadAssignmentPicker path="/assignment-rules/teams" label={`${source.name} team`} value={team} initialLabel={rule?.team_name} emptyLabel="Choose team" onChange={setTeam} />
    <label className="routing-enabled"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /> Enabled</label>
    <div className="routing-actions"><Button variant="outline" size="sm" disabled={!rule || busy} onClick={() => void inspect()}>Preview</Button><Button size="sm" disabled={!team || busy} onClick={() => void save()}>Save</Button></div>
    {preview && <p className="small muted routing-preview" role="status">{text}</p>}
  </div>;
}