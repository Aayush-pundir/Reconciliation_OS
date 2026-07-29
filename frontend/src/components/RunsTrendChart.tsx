import type { Run } from "@/types";

interface Props {
  runs: Run[];
  days?: number;
}

function dayKey(iso: string): string {
  return iso.slice(0, 10);
}

/** Lightweight hand-rolled SVG bar chart (no charting library dependency)
 * showing completed-vs-failed run volume per day, most recent `days` days. */
export default function RunsTrendChart({ runs, days = 14 }: Props) {
  const today = new Date();
  const buckets: { key: string; label: string; completed: number; failed: number; other: number }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const key = d.toISOString().slice(0, 10);
    buckets.push({ key, label: d.toLocaleDateString(undefined, { day: "2-digit", month: "short" }), completed: 0, failed: 0, other: 0 });
  }
  const byKey = new Map(buckets.map((b) => [b.key, b]));
  for (const r of runs) {
    const b = byKey.get(dayKey(r.created_at));
    if (!b) continue;
    if (r.status === "completed") b.completed += 1;
    else if (r.status === "failed") b.failed += 1;
    else b.other += 1;
  }

  const max = Math.max(1, ...buckets.map((b) => b.completed + b.failed + b.other));
  const barWidth = 100 / buckets.length;

  if (runs.length === 0) {
    return <div className="text-sm text-ink-faint py-8 text-center">No runs yet - the trend chart fills in once you start reconciling.</div>;
  }

  return (
    <div>
      <svg viewBox="0 0 100 40" className="w-full h-32" preserveAspectRatio="none">
        {buckets.map((b, i) => {
          const total = b.completed + b.failed + b.other;
          const x = i * barWidth + barWidth * 0.15;
          const w = barWidth * 0.7;
          const completedH = (b.completed / max) * 36;
          const failedH = (b.failed / max) * 36;
          const otherH = (b.other / max) * 36;
          let y = 40;
          const segments: { h: number; color: string }[] = [
            { h: failedH, color: "#d3402e" },
            { h: otherH, color: "#3467e0" },
            { h: completedH, color: "#1a9e5c" },
          ];
          return (
            <g key={b.key}>
              {segments.map((seg, si) => {
                if (seg.h <= 0) return null;
                y -= seg.h;
                return <rect key={si} x={x} y={y} width={w} height={seg.h} fill={seg.color} rx="0.5">
                  <title>{`${b.label}: ${total} run(s)`}</title>
                </rect>;
              })}
              {total === 0 && <rect x={x} y={39.3} width={w} height={0.7} fill="#e4e7ee" />}
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-[10px] text-ink-faint mt-1 px-0.5">
        <span>{buckets[0].label}</span>
        <span>{buckets[buckets.length - 1].label}</span>
      </div>
      <div className="flex items-center gap-4 mt-2 text-[11px] text-ink-faint">
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-good inline-block" /> Completed</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-bad inline-block" /> Failed</span>
        <span className="flex items-center gap-1"><span className="h-2 w-2 rounded-sm bg-brand-500 inline-block" /> In progress</span>
      </div>
    </div>
  );
}
