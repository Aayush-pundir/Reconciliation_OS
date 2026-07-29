import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useToast } from "@/context/ToastContext";
import { SkeletonCard } from "@/components/Skeleton";

function ModuleConfigCard({
  module,
  defaultOptions,
}: {
  module: { key: string; display_name: string; options_schema: { properties?: Record<string, { type?: string; default?: unknown; description?: string; title?: string }> } };
  defaultOptions: Record<string, unknown>;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [values, setValues] = useState<Record<string, unknown>>(defaultOptions);

  useEffect(() => setValues(defaultOptions), [defaultOptions]);

  const fields = Object.entries(module.options_schema.properties ?? {});

  const saveMutation = useMutation({
    mutationFn: () => api.updateModuleConfig(module.key, values),
    onSuccess: () => {
      toast.success(`${module.display_name} defaults saved.`);
      queryClient.invalidateQueries({ queryKey: ["admin", "module-configs"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to save defaults"),
  });

  if (fields.length === 0) {
    return (
      <div className="card p-4">
        <div className="font-semibold text-sm">{module.display_name}</div>
        <div className="text-xs text-ink-faint mt-1">This module has no configurable options.</div>
      </div>
    );
  }

  return (
    <div className="card p-4 flex flex-col gap-3">
      <div className="font-semibold text-sm">{module.display_name}</div>
      <div className="grid sm:grid-cols-2 gap-3">
        {fields.map(([key, schema]) => (
          <div key={key}>
            <label className="label mb-1 block">{schema.title ?? key}</label>
            <input
              className="input"
              type={schema.type === "number" ? "number" : "text"}
              value={values[key] !== undefined ? String(values[key]) : ""}
              placeholder={schema.default !== undefined ? String(schema.default) : ""}
              onChange={(e) =>
                setValues((prev) => ({
                  ...prev,
                  [key]: schema.type === "number" ? Number(e.target.value) : e.target.value,
                }))
              }
            />
            {schema.description && <div className="text-[11px] text-ink-faint mt-1">{schema.description}</div>}
          </div>
        ))}
      </div>
      <div>
        <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending} className="btn-secondary text-xs">
          {saveMutation.isPending ? "Saving…" : "Save Defaults"}
        </button>
      </div>
    </div>
  );
}

export default function Admin() {
  const modulesQuery = useQuery({ queryKey: ["modules"], queryFn: api.listModules });
  const configsQuery = useQuery({ queryKey: ["admin", "module-configs"], queryFn: api.listModuleConfigs });

  const configByKey = new Map((configsQuery.data ?? []).map((c) => [c.module_key, c]));

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-bold">Admin — Module Defaults</h1>
        <p className="text-sm text-ink-muted mt-0.5">
          Org-level default options per module. A run's own options (set on the Run page) override these.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {(modulesQuery.isLoading || configsQuery.isLoading) &&
          Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
        {modulesQuery.data?.map((m) => (
          <ModuleConfigCard key={m.key} module={m} defaultOptions={configByKey.get(m.key)?.default_options ?? {}} />
        ))}
      </div>
    </div>
  );
}
