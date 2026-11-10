"use client";

import { useEffect, useId, useState } from "react";
import { usePaged } from "@/lib/hooks";
import { Button } from "./ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "./ui/dialog";
import { ErrorNotice, Loading, Pagination } from "./Ui";
import Icon from "./Icon";

type Choice = { id: string; name?: string; display_name?: string; status?: string; is_active?: boolean };

export default function LeadAssignmentPicker({ path, label, value, onChange, initialLabel, emptyLabel = "Unassigned" }: {
  path: string; label: string; value: string; onChange: (id: string, name: string) => void; initialLabel?: string; emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const labelId = useId();
  useEffect(() => {
    const timer = setTimeout(() => setSearch(text.trim()), 250);
    return () => clearTimeout(timer);
  }, [text]);
  const list = usePaged<Choice>(open ? `${path}?q=${encodeURIComponent(search)}` : null);
  const current = list.data?.data.find(item => item.id === value);
  const name = !value ? emptyLabel : selected?.id === value ? selected.name : current?.display_name || current?.name || initialLabel || "Selected";
  function choose(id: string, name: string) {
    setSelected({ id, name }); onChange(id, name); setOpen(false); setText(""); setSearch("");
  }
  return <div className="lead-assignment-picker"><span id={labelId}>{label}</span><Button type="button" variant="outline" aria-labelledby={labelId} onClick={() => setOpen(true)}><span>{name}</span><Icon name="chevron" /></Button>
    <Dialog open={open} onOpenChange={setOpen}><DialogContent aria-describedby={undefined}>
      <DialogHeader><DialogTitle>{label}</DialogTitle></DialogHeader>
      <label className="form-row">Search {label.toLowerCase()}<input className="input" type="search" maxLength={200} value={text} onChange={event => setText(event.target.value)} /></label>
      <Button type="button" variant="outline" onClick={() => choose("", "")}>{emptyLabel}</Button>
      <ErrorNotice error={list.error} />{list.error && <Button type="button" variant="outline" onClick={list.reload}>Retry</Button>}
      <div className="lead-assignment-options" aria-label={`${label} options`}>
        {list.loading ? <Loading /> : list.data?.data.length ? list.data.data.map(item => <button type="button" className="lead-assignment-option" key={item.id} aria-pressed={item.id === value} disabled={item.status ? item.status !== "active" : item.is_active === false} onClick={() => choose(item.id, item.display_name || item.name || item.id)}><span>{item.display_name || item.name || item.id}</span>{item.id === value && <Icon name="check" />}{item.is_active === false && <span className="small muted">Inactive</span>}</button>) : !list.error && <p className="muted">No matches found.</p>}
      </div><Pagination list={list} />
    </DialogContent></Dialog>
  </div>;
}