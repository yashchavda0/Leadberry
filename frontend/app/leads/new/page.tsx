"use client";
import LeadForm from "@/components/LeadForm";
import { Guard } from "@/components/Session";
export default function NewLeadPage() {
  return <Guard permission="leads.view"><Guard permission="leads.create"><div className="page-header"><div><span className="eyebrow">GROW YOUR PIPELINE</span><h1>New lead</h1></div></div><LeadForm /></Guard></Guard>;
}
