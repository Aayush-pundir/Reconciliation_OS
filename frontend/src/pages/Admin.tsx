import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useToast } from "@/context/ToastContext";
import { SkeletonCard } from "@/components/Skeleton";

function ApiKeysSection() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const keysQuery = useQuery({ queryKey: ["admin", "api-keys"], queryFn: api.listApiKeys });
  const [name, setName] = useState("");
  const [justCreated, setJustCreated] = useState<{ name: string; api_key: string } | null>(null);

  const createMutation = useMutation({
    mutationFn: () => api.createApiKey(name.trim()),
    onSuccess: (key) => {
      setJustCreated({ name: key.name, api_key: key.api_key });
      setName("");
      queryClient.invalidateQueries({ queryKey: ["admin", "api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to create API key"),
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => api.revokeApiKey(id),
    onSuccess: () => {
      toast.success("API key revoked.");
      queryClient.invalidateQueries({ queryKey: ["admin", "api-keys"] });
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : "Failed to revoke API key"),
  });

  const keys = keysQuery.data ?? [];

  return (
    <div className="card p-4 flex flex-col gap-4">
      <div>
        <div className="font-semibold text-sm">Service-to-Service API Keys</div>
        <p className="text-xs text-ink-faint mt-1">
          For triggering runs programmatically. Only used when AUTH_REQUIRED is turned on server-side - with auth
          optional (the default), these aren't needed.
        </p>
      </div>

      {justCreated && (
        <div className="rounded-lg border border-warn/30 bg-warn/5 px-3 py-2.5 text-xs">
          <div className="font-semibold text-warn mb-1">
            Copy this key now - "{justCreated.name}" won't be shown again.
          </div>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono bg-white rounded px-2 py-1 border border-surface-border break-all">
              {justCreated.api_key}
            </code>
            <button
              className="btn-ghost text-xs shrink-0"
              onClick={() => {
                navigator.clipboard.writeText(justCreated.api_key);
                toast.success("Copied to clipboard.");
              }}
            >
              Copy
            </button>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <input
          className="input flex-1"
          placeholder="Key name (e.g. nightly-batch-job)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button
          className="btn-secondary text-xs shrink-0"
          disabled={!name.trim() || createMutation.isPending}
          onClick={() => createMutation.mutate()}
        >
          {createMutation.isPending ? "Creating…" : "+ New Key"}
        </button>
      </div>

      <div className="divide-y divide-surface-border -mx-4">
        {keysQuery.isLoading && <div className="px-4 py-3 text-xs text-ink-faint">Loading…</div>}
        {!keysQuery.isLoading && keys.length === 0 && (
          <div className="px-4 py-3 text-xs text-ink-faint">No API keys yet.</div>
        )}
        {keys.map((k) => (
          <div key={k.id} className="px-4 py-2.5 flex items-center justify-between text-xs">
            <div>
              <span className="font-medium">{k.name}</span>{" "}
              <span className="font-mono text-ink-faint">{k.key_prefix}…</span>
              {k.revoked_at && <span className="ml-2 text-bad font-semibold">REVOKED</span>}
            </div>
            <div className="flex items-center gap-3 text-ink-faint">
              <span>{new Date(k.created_at).toLocaleDateString()}</span>
              {!k.revoked_at && (
                <button
                  onClick={() => revokeMutation.mutate(k.id)}
                  disabled={revokeMutation.isPending}
                  className="text-bad hover:underline"
                >
                  Revoke
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

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

      <div>
        <h2 className="text-sm font-bold text-ink-muted mb-3 uppercase tracking-wide">Module Defaults</h2>
        <div className="flex flex-col gap-4">
          {(modulesQuery.isLoading || configsQuery.isLoading) &&
            Array.from({ length: 3 }).map((_, i) => <SkeletonCard key={i} />)}
          {modulesQuery.data?.map((m) => (
            <ModuleConfigCard key={m.key} module={m} defaultOptions={configByKey.get(m.key)?.default_options ?? {}} />
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-bold text-ink-muted mb-3 uppercase tracking-wide">API Keys</h2>
        <ApiKeysSection />
      </div>
    </div>
  );
}
