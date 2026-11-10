"use client";

import { usePaged } from "@/lib/hooks";
import { ErrorNotice, Loading, Pagination } from "./Ui";

type Choice = { id: string; name?: string; display_name?: string; status?: string; is_active?: boolean };

export default function SelectionPicker({ path, values, onChange, single = false, label, excludeIds = [], includeInactive = false }: {
  path: string; values: string[]; onChange: (values: string[]) => void; single?: boolean; label: string; excludeIds?: string[]; includeInactive?: boolean;
}) {
  const resource = usePaged<Choice>(path);
  return <fieldset className="selection-picker"><legend>{label}</legend><ErrorNotice error={resource.error} />
    <div className="selected-summary">{values.length ? <span className="small muted">{values.length} selected (preserved across pages)</span> : <span className="small muted">None selected</span>}{values.length > 0 && <button className="btn small" type="button" onClick={() => onChange([])}>Clear selection</button>}</div>
    {resource.loading ? <Loading /> : resource.data?.data.filter(item => !excludeIds.includes(item.id)).map(item => <label className="check-row" key={item.id}><input type="checkbox" checked={values.includes(item.id)} disabled={!includeInactive && (item.status ? item.status !== "active" : item.is_active === false)} onChange={event => onChange(event.target.checked ? single ? [item.id] : [...values, item.id] : values.filter(id => id !== item.id))} /><span>{item.name || item.display_name || item.id}</span>{(item.status && item.status !== "active" || item.is_active === false) && <span className="muted small">Inactive</span>}</label>)}
    <Pagination list={resource} />
  </fieldset>;
}
