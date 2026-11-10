"use client";

import ScrollArea from "@/components/ScrollArea";
import ColumnActions from "@/components/ColumnActions";

export type PickerColumn = { key: string; label: string; locked?: boolean };

export default function ColumnPicker({ columns, selected, defaults, onChange }: {
  columns: PickerColumn[]; selected: string[]; defaults: string[]; onChange: (next: string[]) => void;
}) {
  const locked = columns.filter(column => column.locked).map(column => column.key);
  return <details className="column-picker"><summary className="btn">Columns</summary><div className="column-picker-menu">
    <ColumnActions onShowAll={() => onChange(columns.map(column => column.key))} onClear={() => onChange(locked)} onReset={() => onChange(defaults)} />
    <ScrollArea maxHeight="60vh" label="Columns">
    {columns.map(column => <label key={column.key}>
      <input type="checkbox" checked={column.locked || selected.includes(column.key)} disabled={column.locked}
        onChange={event => onChange(columns.filter(item => item.locked || (item.key === column.key ? event.target.checked : selected.includes(item.key))).map(item => item.key))} />
      <span>{column.label}</span>
    </label>)}
  </ScrollArea></div></details>;
}
