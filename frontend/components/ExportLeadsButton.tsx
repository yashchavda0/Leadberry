"use client";

import { useState } from "react";
import Icon from "@/components/Icon";
import { useNotify } from "@/components/Notifications";
import { useSession } from "@/components/Session";
import { IconButton } from "@/components/ui/icon-button";
import { download, errorMessage } from "@/lib/crm";

/** Downloads the leads matching `query` (same filters as GET /leads) as an Excel workbook. */
export default function ExportLeadsButton({ query = "", label = "Export to Excel", className = "btn", fileName = "leads.xlsx", iconOnly = false }: {
  query?: string; label?: string; className?: string; fileName?: string; iconOnly?: boolean;
}) {
  const { can } = useSession();
  const notify = useNotify();
  const [busy, setBusy] = useState(false);
  if (!can("leads.export") || !can("leads.view")) return null;
  async function run() {
    setBusy(true);
    try {
      const name = await download(`/leads/export${query ? `?${query}` : ""}`, fileName);
      notify.success(`${name} downloaded.`);
    } catch (problem) { notify.error(errorMessage(problem), { title: "Export failed" }); }
    finally { setBusy(false); }
  }
  if (iconOnly) return <IconButton label={label} disabled={busy} onClick={() => void run()}><span className={busy ? "spin" : undefined}><Icon name="download" /></span></IconButton>;
  return <button type="button" className={className} disabled={busy} onClick={() => void run()}><Icon name="download" />{busy ? "Preparing..." : label}</button>;
}
