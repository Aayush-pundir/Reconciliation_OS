import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import StatusBadge from "@/components/StatusBadge";
import { Skeleton, SkeletonCard, SkeletonRow } from "@/components/Skeleton";
import RunsTrendChart from "@/components/RunsTrendChart";

const MODULE_ICONS: Record<string, string> = {
  nfs: "🏧",
  rupay: "💳",
  upi: "📲",
  fastag: "🚗",
  pg_recon: "🔀",
  bank_addmoney: "🏦",
  data_prep_6f: "📊",
};

export default function Dashboard() {
  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  // Fetch a wider recent window for the trend chart's daily aggregation;
  // the activity feed below just shows the first 8 of these.
  const runsQuery = useQuery({ queryKey: ["runs", "recent"], queryFn: () => api.listRuns({ limit: 200 }) });

  const allRuns = runsQuery.data?.items ?? [];
  const runs = allRuns.slice(0, 8);
  const openExceptions = allRuns.filter((r) => r.status === "failed").length;

  return (
    <div className="flex flex-col gap-8">
      <div>
        <h1 className="text-xl font-bold">Dashboard</h1>
        <p className="text-sm text-ink-muted mt-0.5">All reconciliation modules in one place.</p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="card px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Modules</div>
          <div className="text-xl font-bold mt-0.5">{modulesQuery.data?.length ?? "—"}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Recent Runs</div>
          <div className="text-xl font-bold mt-0.5">{runsQuery.data?.total ?? "—"}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">Failed Runs</div>
          <div className={`text-xl font-bold mt-0.5 ${openExceptions ? "text-bad" : "text-good"}`}>{openExceptions}</div>
        </div>
        <div className="card px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-ink-faint">In Progress</div>
          <div className="text-xl font-bold mt-0.5 text-brand-600">
            {allRuns.filter((r) => !["completed", "failed"].includes(r.status)).length}
          </div>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-bold text-ink-muted mb-3 uppercase tracking-wide">Run Activity — Last 14 Days</h2>
        <div className="card p-5">
          {runsQuery.isLoading ? <Skeleton className="h-32 w-full" /> : <RunsTrendChart runs={allRuns} />}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-bold text-ink-muted mb-3 uppercase tracking-wide">Reconciliation Modules</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {modulesQuery.isLoading &&
            Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
          {modulesQuery.data?.map((m) => (
            <Link key={m.key} to={`/modules/${m.key}`} className="card p-4 hover:border-brand-400 transition-colors group">
              <div className="flex items-start gap-3">
                <div className="h-10 w-10 rounded-lg bg-surface-muted flex items-center justify-center text-lg">
                  {MODULE_ICONS[m.key] ?? "🧮"}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold text-sm group-hover:text-brand-700">{m.display_name}</div>
                  <div className="text-xs text-ink-faint mt-0.5 line-clamp-2">{m.description}</div>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between text-[11px] text-ink-faint">
                <span>v{m.version}</span>
                <span className="text-brand-600 font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                  Run →
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-bold text-ink-muted uppercase tracking-wide">Recent Activity</h2>
          <Link to="/runs" className="text-xs font-medium text-brand-600 hover:underline">
            View all →
          </Link>
        </div>
        <div className="card divide-y divide-surface-border">
          {runsQuery.isLoading && Array.from({ length: 4 }).map((_, i) => <SkeletonRow key={i} cols={3} />)}
          {!runsQuery.isLoading && runs.length === 0 && (
            <div className="px-4 py-6 text-sm text-ink-faint text-center">No runs yet.</div>
          )}
          {runs.map((r) => (
            <Link key={r.id} to={`/runs/${r.id}`} className="flex items-center justify-between px-4 py-3 hover:bg-surface-muted">
              <div className="flex items-center gap-3">
                <span className="text-lg">{MODULE_ICONS[r.module_key] ?? "🧮"}</span>
                <div>
                  <div className="text-sm font-medium">{r.module_key}</div>
                  <div className="text-[11px] text-ink-faint">{new Date(r.created_at).toLocaleString()}</div>
                </div>
              </div>
              <StatusBadge status={r.status} />
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
