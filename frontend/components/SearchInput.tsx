"use client";

import Icon from "@/components/Icon";

export default function SearchInput({ value, onChange, placeholder = "Search", label, className = "" }: {
  value: string; onChange: (value: string) => void; placeholder?: string; label?: string; className?: string;
}) {
  return <div className={`search-input ${className}`}>
    <span className="search-input-icon"><Icon name="search" size={16} /></span>
    <input type="text" role="searchbox" autoComplete="off" aria-label={label || placeholder} placeholder={placeholder} value={value} onChange={event => onChange(event.target.value)} onKeyDown={event => { if (event.key === "Escape" && value) { event.stopPropagation(); onChange(""); } }} />
    {value && <button type="button" className="search-input-clear" aria-label="Clear search" onClick={() => onChange("")}><Icon name="close" size={14} /></button>}
  </div>;
}
