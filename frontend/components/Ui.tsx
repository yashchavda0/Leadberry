"use client";

export function ErrorNotice({ error }: { error: string }) {
  return error ? <div className="alert alert-error" role="alert">{error}</div> : null;
}
export function Loading() { return <p className="muted" role="status">Loading...</p>; }
export function Pagination({ page, previous, next, hasPrevious, hasNext, loading }: {
  page: number; previous: () => void; next: () => void; hasPrevious: boolean; hasNext: boolean; loading: boolean;
}) {
  return <div className="pagination"><span className="muted small">Page {page} / cursor pagination</span><div className="actions"><button type="button" className="btn" disabled={loading || !hasPrevious} onClick={previous}>Previous</button><button type="button" className="btn" disabled={loading || !hasNext} onClick={next}>Next</button></div></div>;
}
export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="form-row"><span>{label}</span>{children}{hint && <span className="hint">{hint}</span>}</label>;
}
