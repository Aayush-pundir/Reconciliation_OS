import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import StatusBadge from "@/components/StatusBadge";
import ProgressStages from "@/components/ProgressStages";
import StatCards from "@/components/StatCards";
import ValidationPanel from "@/components/ValidationPanel";
import DataTable from "@/components/DataTable";
import type { StatCardPayload, ValidationFindingPayload } from "@/types";

const ACTIVE_STATUSES = new Set(["queued", "parsing", "validating", "matching", "reporting"]);

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<string | null>(null);

  const runQuery = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId!),
    enabled: !!runId,
    refetchInterval: (query) => (query.state.data && ACTIVE_STATUSES.has(query.state.data.status) ? 1500 : false),
  });

  const isDone = runQuery.data?.status === "completed";

  const sheetsQuery = useQuery({
    queryKey: ["run", runId, "sheets"],
    queryFn: () => api.listSheets(runId!),
    enabled: !!runId && isDone,
  });

  const summaryQuery = useQuery({
    queryKey: ["run", runId, "results", "summary"],
    queryFn: () => api.getResults(runId!, { kind: "stats", limit: 100 }),
    enabled: !!runId && isDone,
  });

  const validationQuery = useQuery({
    queryKey: ["run", runId, "results", "validation"],
    queryFn: () => api.getResults(runId!, { kind: "validation", limit: 500 }),
    enabled: !!runId && isDone,
  });

  const sheets = sheetsQuery.data?.filter((s) => s !== "stats") ?? [];

  useEffect(() => {
    if (!activeTab && sheets.length) setActiveTab(sheets[0]);
  }, [sheets, activeTab]);

  const sheetQuery = useQuery({
    queryKey: ["run", runId, "results", "sheet", activeTab],
    queryFn: () => api.getResults(runId!, { sheet_name: activeTab!, limit: 5000 }),
    enabled: !!runId && !!activeTab && isDone,
  });

  const rerunMutation = useMutation({
    mutationFn: () => api.rerun(runId!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["runs"] }),
  });

  const annotateMutation = useMutation({
    mutationFn: ({ resultId, status, note }: { resultId: string; status: string; note: string }) =>
      api.annotateResult(runId!, resultId, status, note),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["run", runId, "results", "sheet", activeTab] }),
  });

  const run = runQuery.data;
  if (!run) return <div className="text-sm text-ink-faint">Loading…</div>;

  const stats: StatCardPayload[] = (summaryQuery.data?.items ?? []).map((i) => i.payload as unknown as StatCardPayload);
  const findings: ValidationFindingPayload[] = (validationQuery.data?.items ?? []).map(
    (i) => i.payload as unknown as ValidationFindingPayload
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/runs" className="text-xs text-ink-faint hover:text-brand-600">
            ← Run History
          </Link>
          <div className="flex items-center gap-3 mt-1">
            <h1 className="text-xl font-bold capitalize">{run.module_key.replace(/_/g, " ")}</h1>
            <StatusBadge status={run.status} />
          </div>
          <p className="text-xs text-ink-faint mt-0.5">
            Run {run.id.slice(0, 8)} · started {run.started_at ? new Date(run.started_at).toLocaleString() : "—"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {run.has_report && (
            <a href={api.downloadReportUrl(run.id)} className="btn-primary" download>
              ⬇ Download Excel
            </a>
          )}
          <button onClick={() => rerunMutation.mutate()} className="btn-secondary" disabled={rerunMutation.isPending}>
            ↺ {rerunMutation.isPending ? "Re-queuing…" : "Re-run"}
          </button>
        </div>
      </div>

      <div className="card p-5">
        <ProgressStages status={run.status} />
      </div>

      {run.status === "failed" && run.error_message && (
        <div className="card p-4 border-bad/30 bg-bad/5">
          <div className="text-sm font-semibold text-bad mb-1">Run failed</div>
          <pre className="text-xs text-bad/80 whitespace-pre-wrap font-mono">{run.error_message}</pre>
        </div>
      )}

      {isDone && (
        <>
          <StatCards stats={stats} />

          {findings.length > 0 && (
            <div>
              <h2 className="text-sm font-bold text-ink-muted mb-3 uppercase tracking-wide">Validation</h2>
              <ValidationPanel findings={findings} />
            </div>
          )}

          {sheets.length > 0 && (
            <div>
              <div className="flex items-center gap-1 border-b border-surface-border mb-4">
                {sheets.map((sheet) => (
                  <button
                    key={sheet}
                    onClick={() => setActiveTab(sheet)}
                    className={`px-3.5 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
                      activeTab === sheet
                        ? "border-brand-500 text-brand-700"
                        : "border-transparent text-ink-muted hover:text-ink"
                    }`}
                  >
                    {sheet}
                  </button>
                ))}
              </div>
              {sheetQuery.data && (
                <DataTable
                  columns={sheetQuery.data.items[0]?.columns ?? Object.keys(sheetQuery.data.items[0]?.payload ?? {})}
                  items={sheetQuery.data.items}
                  statusColumn="Status"
                  annotatable={sheetQuery.data.items[0]?.kind === "exception"}
                  onAnnotate={(resultId, status, note) => annotateMutation.mutate({ resultId, status, note })}
                />
              )}
            </div>
          )}
        </>
      )}

      <div>
        <h2 className="text-sm font-bold text-ink-muted mb-2 uppercase tracking-wide">Input Files</h2>
        <div className="card divide-y divide-surface-border">
          {run.files.map((f) => (
            <div key={f.id} className="flex items-center justify-between px-4 py-2 text-sm">
              <span className="font-mono">{f.original_filename}</span>
              <span className="text-ink-faint text-xs">
                {f.slot} · {(f.size_bytes / 1024).toFixed(0)} KB
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
