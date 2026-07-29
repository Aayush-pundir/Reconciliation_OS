import type { RunStatus } from "@/types";

const CONFIG: Record<RunStatus, { label: string; classes: string }> = {
  created: { label: "Created", classes: "bg-surface-muted text-ink-muted" },
  uploaded: { label: "Uploaded", classes: "bg-surface-muted text-ink-muted" },
  queued: { label: "Queued", classes: "bg-brand-50 text-brand-700" },
  parsing: { label: "Parsing", classes: "bg-brand-50 text-brand-700" },
  validating: { label: "Validating", classes: "bg-brand-50 text-brand-700" },
  matching: { label: "Matching", classes: "bg-brand-50 text-brand-700" },
  reporting: { label: "Reporting", classes: "bg-brand-50 text-brand-700" },
  completed: { label: "Completed", classes: "bg-good/10 text-good" },
  failed: { label: "Failed", classes: "bg-bad/10 text-bad" },
};

const ACTIVE: RunStatus[] = ["queued", "parsing", "validating", "matching", "reporting"];

export default function StatusBadge({ status }: { status: RunStatus }) {
  const cfg = CONFIG[status] ?? { label: status, classes: "bg-surface-muted text-ink-muted" };
  const isActive = ACTIVE.includes(status);
  return (
    <span className={`badge ${cfg.classes}`}>
      {isActive && <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />}
      {cfg.label}
    </span>
  );
}
