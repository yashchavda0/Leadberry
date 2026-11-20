"use client";

import Icon from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Tip } from "@/components/ui/tip";
import { isServiceMessage } from "@/lib/crm";

// The one error component. Outages (server down) show a calm card that refreshes itself; other errors show a red notice.
export function ErrorNotice({ error, onRetry, what = "this" }: { error: string; onRetry?: () => void; what?: string }) {
  if (!error) return null;
  const outage = isServiceMessage(error);
  if (!outage && !onRetry) return <div className="alert alert-error" role="alert">{error}</div>;
  return <div className={`load-failed${outage ? " outage" : ""}`} role={outage ? "status" : "alert"}>
    <span className="load-failed-icon"><Icon name={outage ? "refresh" : "alert"} size={22} /></span>
    <div><strong>{outage ? `Can't load ${what} right now` : `${what[0].toUpperCase()}${what.slice(1)} could not be loaded`}</strong><p className="small muted">{outage ? "The server isn't responding. This page will refresh by itself when it's back." : error}</p></div>
    {onRetry && <Button variant="outline" size="sm" onClick={onRetry}><Icon name="refresh" />Try again</Button>}
  </div>;
}
export const LoadFailed = ErrorNotice;
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
