"use client";

import Link from "next/link";
import { useSession } from "@/components/Session";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import ApiKeys from "./ApiKeys";
import AssignmentRules from "./AssignmentRules";

export default function IntakeWorkspace() {
  const { can, identity } = useSession();
  const keys = can("api_keys.manage");
  const routing = can("assignment_rules.manage");
  const fullScope = identity?.data_scope === "all";
  if (!keys && !routing) return <div className="card"><h1>Access restricted</h1><p>Contact an organization owner for access.</p><Link href="/account">View your access</Link></div>;
  return <>
    <div className="page-header"><div><span className="eyebrow">LEAD CHANNELS</span><h1>Lead intake</h1></div></div>
    {!fullScope ? <p className="muted">Organization-wide lead visibility is required to manage intake.</p> :
      <Tabs defaultValue={keys ? "keys" : "routing"}>
        <TabsList aria-label="Lead intake views">{keys && <TabsTrigger value="keys">Website API keys</TabsTrigger>}{routing && <TabsTrigger value="routing">Assignment rules</TabsTrigger>}</TabsList>
        {keys && <TabsContent value="keys">{can("leads.create") && can("leads.pii.view") ? <ApiKeys /> : <p className="muted">Lead creation and contact-data permissions are required to manage API keys.</p>}</TabsContent>}
        {routing && <TabsContent value="routing"><AssignmentRules /></TabsContent>}
      </Tabs>}
  </>;
}