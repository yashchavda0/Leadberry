"use client";

import DatePicker from "@/components/ui/date-picker";
import { Button } from "@/components/ui/button";

export type DateRange = { start: string; end: string };
const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const daysAgo = (count: number) => { const date = new Date(); date.setDate(date.getDate() - count); return iso(date); };

export function lastDays(count: number): DateRange { return { start: daysAgo(count - 1), end: daysAgo(0) }; }

const PRESETS: { label: string; range: () => DateRange }[] = [
  { label: "Today", range: () => lastDays(1) },
  { label: "7 days", range: () => lastDays(7) },
  { label: "30 days", range: () => lastDays(30) },
  { label: "This month", range: () => { const now = new Date(); return { start: iso(new Date(now.getFullYear(), now.getMonth(), 1)), end: iso(now) }; } },
];

export default function DateRangeFilter({ value, onChange }: { value: DateRange; onChange: (range: DateRange) => void }) {
  return <div className="date-range-filter">
    <div className="date-range-presets" role="group" aria-label="Quick ranges">
      {PRESETS.map(preset => { const range = preset.range(); const active = range.start === value.start && range.end === value.end; return <Button key={preset.label} size="sm" variant={active ? "default" : "outline"} onClick={() => onChange(range)}>{preset.label}</Button>; })}
    </div>
    <div className="date-range-pickers">
      <DatePicker ariaLabel="From date" value={value.start} max={value.end} onChange={start => start && onChange({ ...value, start })} />
      <span className="small muted">to</span>
      <DatePicker ariaLabel="To date" value={value.end} min={value.start} onChange={end => end && onChange({ ...value, end })} />
    </div>
  </div>;
}
