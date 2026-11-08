export type BadgeTone = "success" | "warn" | "danger" | "info" | "";

export default function StatusBadge({ tone = "", children }: { tone?: BadgeTone; children: React.ReactNode }) {
  return <span className={`status-badge ${tone}`}><span className="status-badge-dot" aria-hidden="true" />{children}</span>;
}
