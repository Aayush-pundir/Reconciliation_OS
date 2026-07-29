import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import StatusBadge from "@/components/StatusBadge";
import ProgressStages from "@/components/ProgressStages";
import StatCards from "@/components/StatCards";
import ValidationPanel from "@/components/ValidationPanel";
import DataTable from "@/components/DataTable";
import { useToast } from "@/context/ToastContext";
import { Skeleton, SkeletonCard } from "@/components/Skeleton";
import type { StatCardPayload, ValidationFindingPayload } from "@/types";

const ACTIVE_STATUSES = new Set(["queued", "parsing", "validating", "matching", "reporting"]);

export default function RunDetail() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [showScheduleForm, setShowScheduleForm] = useState(false);
  const [scheduleName, setScheduleName] = useState("");
  const [scheduleInterval, setScheduleInterval] = useState(1440);

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
    onSuccess: (run) => {
      toast.success("Re-run queued.");
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      navigate(`/runs/${run.id}`);
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to queue re-run"),
  });

  const annotateMutation = useMutation({
    mutationFn: ({ resultId, status, note }: { resultId: string; status: string; note: string }) =>
      api.annotateResult(runId!, resultId, status, note),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["run", runId, "results", "sheet", activeTab] }),
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to save annotation"),
  });

  const scheduleMutation = useMutation({
    mutationFn: () => api.createSchedule(scheduleName.trim(), runId!, scheduleInterval),
    onSuccess: () => {
      toast.success("Recurring schedule created - manage it from Admin.");
      setShowScheduleForm(false);
      setScheduleName("");
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to create schedule"),
  });

  const run = runQuery.data;
  if (!run)
    return (
      <div className="flex flex-col gap-6">
        <Skeleton className="h-6 w-1/3" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
        <Skeleton className="h-40 w-full" />
      </div>
    );

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
          {run.status === "completed" && (
            <button onClick={() => setShowScheduleForm((v) => !v)} className="btn-secondary">
              🔁 Schedule
            </button>
          )}
        </div>
      </div>

      {showScheduleForm && (
        <div className="card p-4 flex items-center gap-3">
          <input
            className="input flex-1"
            placeholder="Schedule name (e.g. Nightly NFS recon)"
            value={scheduleName}
            onChange={(e) => setScheduleName(e.target.value)}
          />
          <select
            className="input max-w-[160px]"
            value={scheduleInterval}
            onChange={(e) => setScheduleInterval(Number(e.target.value))}
          >
            <option value={60}>Hourly</option>
            <option value={1440}>Daily</option>
            <option value={10080}>Weekly</option>
          </select>
          <button
            onClick={() => scheduleMutation.mutate()}
            disabled={!scheduleName.trim() || scheduleMutation.isPending}
            className="btn-primary shrink-0"
          >
            {scheduleMutation.isPending ? "Creating…" : "Create"}
          </button>
        </div>
      )}

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
                  sheetName={`${run.module_key}_${activeTab}`}
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
