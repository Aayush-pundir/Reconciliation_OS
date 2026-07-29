import { useMemo, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import FileDropzone from "@/components/FileDropzone";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/context/ToastContext";

export default function ModuleRun() {
  const { moduleKey } = useParams<{ moduleKey: string }>();
  const navigate = useNavigate();
  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const module = modulesQuery.data?.find((m) => m.key === moduleKey);

  const toast = useToast();
  const [filesBySlot, setFilesBySlot] = useState<Record<string, File[]>>({});
  const [options, setOptions] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const optionFields = useMemo(
    () => Object.entries(module?.options_schema.properties ?? {}),
    [module]
  );

  const runMutation = useMutation({
    mutationFn: () => api.createRun(module!.key, options, filesBySlot),
    onSuccess: (run) => {
      toast.success("Reconciliation started.");
      navigate(`/runs/${run.id}`);
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : "Failed to start run";
      setError(message);
      toast.error(message);
    },
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => api.importReport(module!.key, file),
    onSuccess: (run) => {
      toast.success("Report imported.");
      navigate(`/runs/${run.id}`);
    },
    onError: (err) => {
      const message = err instanceof ApiError ? err.message : "Failed to import report";
      setImportError(message);
      toast.error(message);
    },
  });

  if (modulesQuery.isLoading)
    return (
      <div className="max-w-3xl flex flex-col gap-6">
        <Skeleton className="h-5 w-1/3" />
        <div className="card p-5 flex flex-col gap-4">
          <Skeleton className="h-4 w-1/4" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    );
  if (!module) return <div className="text-sm text-bad">Unknown module.</div>;

  const ready = module.input_slots
    .filter((s) => s.required)
    .every((s) => (filesBySlot[s.key]?.length ?? 0) > 0);

  return (
    <div className="max-w-3xl flex flex-col gap-6">
      <div>
        <Link to="/" className="text-xs text-ink-faint hover:text-brand-600">
          ← Dashboard
        </Link>
        <h1 className="text-xl font-bold mt-1">{module.display_name}</h1>
        <p className="text-sm text-ink-muted mt-0.5">{module.description}</p>
      </div>

      <div className="card p-5 flex flex-col gap-5">
        <div className="text-xs font-bold uppercase tracking-wide text-ink-faint">Step 1 — Upload Files</div>
        {module.input_slots.map((slot) => (
          <FileDropzone
            key={slot.key}
            slot={slot}
            files={filesBySlot[slot.key] ?? []}
            onChange={(files) => setFilesBySlot((prev) => ({ ...prev, [slot.key]: files }))}
          />
        ))}
      </div>

      {optionFields.length > 0 && (
        <div className="card p-5 flex flex-col gap-4">
          <div className="text-xs font-bold uppercase tracking-wide text-ink-faint">Step 2 — Options</div>
          <div className="grid sm:grid-cols-2 gap-4">
            {optionFields.map(([key, schema]) => (
              <div key={key}>
                <label className="label mb-1.5 block">{schema.title ?? key}</label>
                <input
                  className="input"
                  type={schema.type === "number" ? "number" : "text"}
                  placeholder={schema.default !== undefined ? String(schema.default) : ""}
                  onChange={(e) =>
                    setOptions((prev) => ({
                      ...prev,
                      [key]: schema.type === "number" ? Number(e.target.value) : e.target.value,
                    }))
                  }
                />
                {schema.description && <div className="text-[11px] text-ink-faint mt-1">{schema.description}</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {error && <div className="text-xs text-bad bg-bad/5 border border-bad/20 rounded-lg px-3 py-2">{error}</div>}

      <div className="flex items-center gap-3">
        <button
          onClick={() => runMutation.mutate()}
          disabled={!ready || runMutation.isPending}
          className="btn-primary"
        >
          {runMutation.isPending ? "Starting…" : "⚡ Run Reconciliation"}
        </button>
        {!ready && <span className="text-xs text-ink-faint">Upload all required files to enable.</span>}
      </div>

      <div className="card p-5 flex flex-col gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-wide text-ink-faint">Import a Past Report</div>
          <p className="text-xs text-ink-faint mt-1">
            Already have a report exported from Recon OS (or the original standalone tool)? Import it to archive
            its numbers as a completed run - no re-parsing or re-reconciling.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="btn-ghost text-xs cursor-pointer">
            {importMutation.isPending ? "Importing…" : "Choose Excel file…"}
            <input
              type="file"
              accept=".xlsx,.xls,.xlsm"
              className="hidden"
              disabled={importMutation.isPending}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setImportError(null);
                  importMutation.mutate(file);
                }
                e.target.value = "";
              }}
            />
          </label>
        </div>
        {importError && <div className="text-xs text-bad bg-bad/5 border border-bad/20 rounded-lg px-3 py-2">{importError}</div>}
      </div>
    </div>
  );
}
