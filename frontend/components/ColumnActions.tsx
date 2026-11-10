"use client";

// Shared Show all / Clear / Reset row for column pickers.
export default function ColumnActions({ onShowAll, onClear, onReset, disabled }: { onShowAll: () => void; onClear: () => void; onReset: () => void; disabled?: boolean }) {
  return <div className="column-actions">
    <button type="button" className="permission-group-action" disabled={disabled} onClick={onShowAll}>Show all</button>
    <button type="button" className="permission-group-action" disabled={disabled} onClick={onClear}>Clear</button>
    <button type="button" className="permission-group-action" disabled={disabled} onClick={onReset}>Reset</button>
  </div>;
}
