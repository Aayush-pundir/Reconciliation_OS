import type { ValidationFindingPayload } from "@/types";

const LEVEL_STYLE: Record<string, { icon: string; classes: string }> = {
  ok: { icon: "✔", classes: "border-good/30 bg-good/5 text-good" },
  warn: { icon: "⚠", classes: "border-warn/30 bg-warn/5 text-warn" },
  err: { icon: "✘", classes: "border-bad/30 bg-bad/5 text-bad" },
};

export default function ValidationPanel({ findings }: { findings: ValidationFindingPayload[] }) {
  if (!findings.length) return null;

  const grouped = findings.reduce<Record<string, ValidationFindingPayload[]>>((acc, f) => {
    (acc[f.pass_name] ??= []).push(f);
    return acc;
  }, {});

  return (
    <div className="flex flex-col gap-4">
      {Object.entries(grouped).map(([passName, items]) => {
        const worst = items.some((i) => i.level === "err") ? "err" : items.some((i) => i.level === "warn") ? "warn" : "ok";
        const style = LEVEL_STYLE[worst];
        return (
          <div key={passName} className="card overflow-hidden">
            <div className={`px-4 py-2.5 font-semibold text-sm flex items-center gap-2 border-b ${style.classes}`}>
              <span>{style.icon}</span>
              {passName}
            </div>
            <div className="divide-y divide-surface-border">
              {items.map((item, i) => {
                const s = LEVEL_STYLE[item.level];
                return (
                  <div key={i} className="px-4 py-2 flex items-start gap-2 text-sm">
                    <span className={s.classes.split(" ")[2]}>{s.icon}</span>
                    <div>
                      <span className="font-medium">{item.check}</span>
                      <span className="text-ink-muted"> — {item.message}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
