"use client";

import Icon from "@/components/Icon";
import { Tip } from "@/components/ui/tip";

export function ErrorNotice({ error }: { error: string }) {
  return error ? <div className="alert alert-error" role="alert">{error}</div> : null;
}
export function Loading() { return <p className="muted" role="status">Loading...</p>; }
export type PagerList = {
  page: number; previous: () => void; next: () => void; hasPrevious: boolean; loading: boolean;
  data: { data: unknown[]; next_cursor: string | null } | null; total?: number | null; pageSize?: number;
};
// Pass the object returned by usePaged. Shows "Page X of Y" once the first page reports a total.
export function Pagination({ list, pageSizes, onPageSizeChange }: { list: PagerList; pageSizes?: number[]; onPageSizeChange?: (size: number) => void }) {
  const { page, previous, next, hasPrevious, loading, data, total, pageSize = 25 } = list;
  const hasNext = Boolean(data?.next_cursor);
  const count = data?.data.length ?? 0;
  if (!hasPrevious && !hasNext && !count) return null;
  const first = (page - 1) * pageSize + 1;
  const pages = typeof total === "number" ? Math.max(1, Math.ceil(total / pageSize)) : null;
  return <nav className="pager" aria-label="Pagination">
    <span className="pager-range">{count ? `${first}–${first + count - 1}${typeof total === "number" ? ` of ${total.toLocaleString()}` : ""}` : ""}</span>
    <div className="pager-controls">
      {pageSizes && onPageSizeChange && <label className="pager-page-size">Rows per page <select className="select" aria-label="Rows per page" value={pageSize} onChange={event => onPageSizeChange(Number(event.target.value))} disabled={loading}>{pageSizes.map(size => <option key={size} value={size}>{size}</option>)}</select></label>}
      <Tip label="Previous page" disabled={loading || !hasPrevious}><button type="button" aria-label="Previous" disabled={loading || !hasPrevious} onClick={previous}><Icon name="chevronLeft" /></button></Tip>
      <span className="pager-page" aria-live="polite">Page <strong>{page}</strong>{pages ? <> of <strong>{pages.toLocaleString()}</strong></> : null}</span>
      <Tip label="Next page" disabled={loading || !hasNext}><button type="button" aria-label="Next" disabled={loading || !hasNext} onClick={next}><Icon name="chevronRight" /></button></Tip>
    </div>
  </nav>;
}
export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="form-row"><span>{label}</span>{children}{hint && <span className="hint">{hint}</span>}</label>;
}
