import Link from "next/link";
import Icon, { type IconName } from "@/components/Icon";
import { Button } from "@/components/ui/button";

// Shown when the Leads page was opened from a connection or a history import.
export default function LeadContextBar({ kind, value, clearHref, clearLabel, icon = "filter" }: { kind: string; value: string; clearHref: string; clearLabel: string; icon?: IconName }) {
  return <div className="lead-context" role="status">
    <span className="lead-context-icon"><Icon name={icon} size={16} /></span>
    <div className="lead-context-text"><span className="lead-context-kind">{kind}</span><strong>{value}</strong></div>
    <Button variant="ghost" size="sm" asChild><Link href={clearHref}><Icon name="close" size={14} />{clearLabel}</Link></Button>
  </div>;
}
