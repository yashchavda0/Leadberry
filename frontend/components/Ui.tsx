"use client";

import Icon from "@/components/Icon";

export function ErrorNotice({ error }: { error: string }) {
  return error ? <div className="alert alert-error" role="alert">{error}</div> : null;
}
export function Loading() { return <p className="muted" role="status">Loading...</p>; }
export type PagerList = {
  page: number; previous: () => void; next: () => void; hasPrevious: boolean; loading: boolean;
  data: { data: unknown[]; next_cursor: string | null } | null; total?: number | null; pageSize?: number;
};
// Pass the object returned by usePaged. Shows "Page X of Y" once the first page reports a total.
export function Pagination({ list }: { list: PagerList }) {
  const { page, previous, next, hasPrevious, loading, data, total, pageSize = 25 } = list;
  const hasNext = Boolean(data?.next_cursor);
  const count = data?.data.length ?? 0;
  if (!hasPrevious && !hasNext && !count) return null;
  const first = (page - 1) * pageSize + 1;
  const pages = typeof total === "number" ? Math.max(1, Math.ceil(total / pageSize)) : null;
  return <nav className="pager" aria-label="Pagination">
    <span className="pager-range">{count ? `${first}–${first + count - 1}${typeof total === "number" ? ` of ${total.toLocaleString()}` : ""}` : ""}</span>
    <div className="pager-controls">
      <button type="button" aria-label="Previous" title="Previous page" disabled={loading || !hasPrevious} onClick={previous}><Icon name="chevronLeft" /></button>
      <span className="pager-page" aria-live="polite">Page <strong>{page}</strong>{pages ? <> of <strong>{pages.toLocaleString()}</strong></> : null}</span>
      <button type="button" aria-label="Next" title="Next page" disabled={loading || !hasNext} onClick={next}><Icon name="chevronRight" /></button>
    </div>
  </nav>;
}
export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="form-row"><span>{label}</span>{children}{hint && <span className="hint">{hint}</span>}</label>;
}
