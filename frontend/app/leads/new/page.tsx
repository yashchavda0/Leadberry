"use client";
import LeadForm from "@/components/LeadForm";
import Link from "next/link";
import Icon from "@/components/Icon";
import { Guard } from "@/components/Session";
export default function NewLeadPage() {
  return <Guard permission="leads.view"><Guard permission="leads.create"><div className="page-header leads-header"><div><Link className="lead-back-link" href="/leads"><Icon name="chevronLeft" />Leads</Link><h1>New lead</h1></div></div><LeadForm /></Guard></Guard>;
}
