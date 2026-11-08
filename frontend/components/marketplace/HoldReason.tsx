"use client";

import Icon from "@/components/Icon";
import { holdReasonText } from "@/lib/crm";

export default function HoldReason({ reason, until, provider, className = "" }: { reason: string | null; until: string | null; provider: string; className?: string }) {
  if (!reason) return null;
  return <p className={`hold-reason small ${className}`} role="status" data-reason={reason}>
    <Icon name="clock" size={14} /><span>{holdReasonText(reason, provider, until)}</span>
  </p>;
}
