import type { RunStatus } from "@/types";

const STAGES: { key: RunStatus; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "parsing", label: "Parsing" },
  { key: "validating", label: "Validating" },
  { key: "matching", label: "Matching" },
  { key: "reporting", label: "Reporting" },
  { key: "completed", label: "Complete" },
];

export default function ProgressStages({ status }: { status: RunStatus }) {
  if (status === "failed") {
    return (
      <div className="flex items-center gap-2 text-bad text-sm font-medium">
        <span className="h-2 w-2 rounded-full bg-bad" /> Run failed
      </div>
    );
  }

  const currentIndex = STAGES.findIndex((s) => s.key === status);

  return (
    <div className="flex items-center">
      {STAGES.map((stage, i) => {
        const done = currentIndex > i || status === "completed";
        const active = i === currentIndex && status !== "completed";
        return (
          <div key={stage.key} className="flex items-center flex-1 last:flex-none">
            <div className="flex flex-col items-center gap-1">
              <div
                className={`h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  done ? "bg-good text-white" : active ? "bg-brand-500 text-white animate-pulse" : "bg-surface-border text-ink-faint"
                }`}
              >
                {done ? "✓" : i + 1}
              </div>
              <span className={`text-[10px] font-medium ${active ? "text-brand-700" : "text-ink-faint"}`}>{stage.label}</span>
            </div>
            {i < STAGES.length - 1 && (
              <div className={`h-0.5 flex-1 mx-1 ${currentIndex > i ? "bg-good" : "bg-surface-border"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}
