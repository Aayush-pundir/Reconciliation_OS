import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import StatusBadge from "@/components/StatusBadge";

const STATUS_OPTIONS = ["", "queued", "parsing", "validating", "matching", "reporting", "completed", "failed"];

export default function RunHistory() {
  const [status, setStatus] = useState("");
  const [moduleKey, setModuleKey] = useState("");
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const runsQuery = useQuery({
    queryKey: ["runs", { status, moduleKey, page }],
    queryFn: () => api.listRuns({ status: status || undefined, module_key: moduleKey || undefined, limit: pageSize, offset: page * pageSize }),
  });

  const runs = runsQuery.data?.items ?? [];
  const total = runsQuery.data?.total ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold">Run History</h1>
        <p className="text-sm text-ink-muted mt-0.5">Every reconciliation run, across every module.</p>
      </div>

      <div className="flex items-center gap-3">
        <select className="input max-w-[200px]" value={moduleKey} onChange={(e) => { setModuleKey(e.target.value); setPage(0); }}>
          <option value="">All modules</option>
          {modulesQuery.data?.map((m) => (
            <option key={m.key} value={m.key}>
              {m.display_name}
            </option>
          ))}
        </select>
        <select className="input max-w-[160px]" value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s ? s[0].toUpperCase() + s.slice(1) : "All statuses"}
            </option>
          ))}
        </select>
      </div>

      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-surface-muted text-left text-xs font-semibold text-ink-muted uppercase tracking-wide">
            <tr>
              <th className="px-4 py-2.5">Module</th>
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Created</th>
              <th className="px-4 py-2.5">Completed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-border">
            {runs.map((r) => (
              <tr key={r.id} className="hover:bg-surface-muted">
                <td className="px-4 py-2.5">
                  <Link to={`/runs/${r.id}`} className="font-medium text-brand-700 hover:underline capitalize">
                    {r.module_key.replace(/_/g, " ")}
                  </Link>
                  <div className="text-[11px] text-ink-faint font-mono">{r.id.slice(0, 8)}</div>
                </td>
                <td className="px-4 py-2.5">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-4 py-2.5 text-ink-muted">{new Date(r.created_at).toLocaleString()}</td>
                <td className="px-4 py-2.5 text-ink-muted">{r.completed_at ? new Date(r.completed_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
            {runs.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-10 text-center text-ink-faint">
                  No runs match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-ink-faint">
        <span>
          Showing {runs.length ? page * pageSize + 1 : 0}–{page * pageSize + runs.length} of {total}
        </span>
        <div className="flex gap-2">
          <button className="btn-secondary" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>
            Previous
          </button>
          <button className="btn-secondary" disabled={(page + 1) * pageSize >= total} onClick={() => setPage((p) => p + 1)}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
