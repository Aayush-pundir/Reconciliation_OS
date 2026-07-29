import type { StatCardPayload } from "@/types";

const TONE_CLASSES: Record<string, string> = {
  neutral: "text-ink",
  good: "text-good",
  bad: "text-bad",
  warn: "text-warn",
};

export default function StatCards({ stats }: { stats: StatCardPayload[] }) {
  if (!stats.length) return null;
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      {stats.map((s, i) => (
        <div key={i} className="card px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">{s.label}</div>
          <div className={`text-xl font-bold mt-0.5 ${TONE_CLASSES[s.tone] ?? "text-ink"}`}>{s.value}</div>
          {s.sub && <div className="text-[11px] text-ink-faint mt-0.5">{s.sub}</div>}
        </div>
      ))}
    </div>
  );
}
