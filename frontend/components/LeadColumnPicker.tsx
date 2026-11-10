"use client";

import * as Menu from "@radix-ui/react-dropdown-menu";
import { DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuTrigger } from "./ui/dropdown-menu";
import { Button } from "./ui/button";
import Icon from "./Icon";
import { getLeadColumns, isPiiLeadColumn } from "./LeadsTable";
import { type LeadCustomField } from "@/lib/crm";
import ScrollArea from "./ScrollArea";
import ColumnActions from "./ColumnActions";

export const DEFAULT_LEAD_COLUMNS: string[] = ["company", "email", "phone", "name", "status_changed_at", "status", "source_name", "received_at"];

export default function LeadColumnPicker({ columns, onChange, busy, pii, customFields }: {
  customFields?: LeadCustomField[];
  columns: string[]; onChange: (columns: string[]) => void; busy: boolean; pii: boolean;
}) {
  const available = getLeadColumns(customFields);
  const selectedCount = available.filter(column => columns.includes(column.key) && (pii || !isPiiLeadColumn(column.key))).length;
  const allowed = (key: string) => pii || !isPiiLeadColumn(key);
  const defaults = DEFAULT_LEAD_COLUMNS.filter(allowed);
  return <DropdownMenu modal={false}><DropdownMenuTrigger asChild><Button variant="outline"><Icon name="settings" />Columns</Button></DropdownMenuTrigger>
    <DropdownMenuContent className="lead-column-menu"><DropdownMenuLabel>Visible columns</DropdownMenuLabel>
      <ColumnActions disabled={busy}
        onShowAll={() => onChange(available.map(column => column.key).filter(allowed))}
        onClear={() => onChange(defaults.slice(0, 1))}
        onReset={() => onChange(defaults)} />
      <ScrollArea direction="both" maxHeight="min(280px, 40vh)" label="Lead columns">
      <div className="lead-column-grid">
      {available.map(column => <Menu.CheckboxItem className="ui-menu-item lead-column-option" key={column.key} checked={columns.includes(column.key) && (pii || !isPiiLeadColumn(column.key))} disabled={busy || (columns.includes(column.key) && selectedCount <= 1) || (!pii && isPiiLeadColumn(column.key))} onSelect={event => event.preventDefault()} onCheckedChange={checked => onChange(checked ? [...new Set([...columns, column.key])] : columns.filter(key => key !== column.key))}>
        <span className="lead-column-check"><Menu.ItemIndicator><Icon name="check" size={13} /></Menu.ItemIndicator></span><span>{column.label}</span>
      </Menu.CheckboxItem>)}
      </div>
      </ScrollArea>
    </DropdownMenuContent></DropdownMenu>;
}