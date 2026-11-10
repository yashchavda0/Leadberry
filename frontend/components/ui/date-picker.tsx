"use client";

import { useState } from "react";
import Icon from "@/components/Icon";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const pad = (value: number) => String(value).padStart(2, "0");
const toIso = (year: number, month: number, day: number) => `${year}-${pad(month + 1)}-${pad(day)}`;
function parse(value?: string) {
  const match = value && /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? { year: Number(match[1]), month: Number(match[2]) - 1, day: Number(match[3]) } : null;
}
const label = (value: string) => { const date = parse(value); return date ? `${date.day} ${MONTHS[date.month].slice(0, 3)} ${date.year}` : ""; };

// Compact date picker: value is "YYYY-MM-DD" (same as <input type="date">) but shown as "8 Nov 2026".
export default function DatePicker({ value, onChange, placeholder = "Pick date", min, max, ariaLabel, className }: {
  value: string; onChange: (value: string) => void; placeholder?: string; min?: string; max?: string; ariaLabel: string; className?: string;
}) {
  const today = new Date();
  const selected = parse(value);
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => ({ year: selected?.year ?? today.getFullYear(), month: selected?.month ?? today.getMonth() }));
  const first = (new Date(view.year, view.month, 1).getDay() + 6) % 7;
  const total = new Date(view.year, view.month + 1, 0).getDate();
  const cells = [...Array(first).fill(null), ...Array.from({ length: total }, (_, index) => index + 1)];
  const move = (step: number) => setView(current => { const date = new Date(current.year, current.month + step, 1); return { year: date.getFullYear(), month: date.getMonth() }; });
  const disabled = (day: number) => { const iso = toIso(view.year, view.month, day); return Boolean((min && iso < min) || (max && iso > max)); };
  return <Popover open={open} onOpenChange={next => { setOpen(next); if (next) setView({ year: selected?.year ?? today.getFullYear(), month: selected?.month ?? today.getMonth() }); }}>
    <PopoverTrigger asChild>
      <button type="button" aria-label={ariaLabel} className={cn("date-trigger", !value && "empty", className)}>
        <Icon name="calendar" size={14} /><span>{value ? label(value) : placeholder}</span>
      </button>
    </PopoverTrigger>
    <PopoverContent className="date-popover" onOpenAutoFocus={event => event.preventDefault()}>
      <div className="date-head">
        <button type="button" className="date-nav" aria-label="Previous month" onClick={() => move(-1)}><Icon name="chevronLeft" size={16} /></button>
        <strong>{MONTHS[view.month]} {view.year}</strong>
        <button type="button" className="date-nav" aria-label="Next month" onClick={() => move(1)}><Icon name="chevronRight" size={16} /></button>
      </div>
      <div className="date-grid" role="grid">
        {DAYS.map(day => <span key={day} className="date-dow">{day}</span>)}
        {cells.map((day, index) => day === null ? <span key={`b${index}`} /> : <button key={day} type="button" disabled={disabled(day)}
          className={cn("date-day", value === toIso(view.year, view.month, day) && "selected", today.getFullYear() === view.year && today.getMonth() === view.month && today.getDate() === day && "today")}
          onClick={() => { onChange(toIso(view.year, view.month, day)); setOpen(false); }}>{day}</button>)}
      </div>
      <div className="date-foot">
        <button type="button" className="date-link" onClick={() => { onChange(""); setOpen(false); }} disabled={!value}>Clear</button>
        <button type="button" className="date-link" onClick={() => { onChange(toIso(today.getFullYear(), today.getMonth(), today.getDate())); setOpen(false); }}>Today</button>
      </div>
    </PopoverContent>
  </Popover>;
}
