import { useCallback, useRef, useState } from "react";
import type { InputSlot } from "@/types";

interface Props {
  slot: InputSlot;
  files: File[];
  onChange: (files: File[]) => void;
}

function matchesPattern(name: string, pattern: string | null): boolean {
  if (!pattern) return true;
  try {
    return new RegExp(pattern, "i").test(name);
  } catch {
    return true;
  }
}

export default function FileDropzone({ slot, files, onChange }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback(
    (incoming: FileList | null) => {
      if (!incoming) return;
      const next = slot.multiple ? [...files, ...Array.from(incoming)] : [Array.from(incoming)[0]];
      const seen = new Set<string>();
      const deduped = next.filter((f) => (seen.has(f.name) ? false : seen.add(f.name)));
      onChange(deduped);
    },
    [files, onChange, slot.multiple]
  );

  const removeFile = (name: string) => onChange(files.filter((f) => f.name !== name));

  return (
    <div>
      <div className="flex items-baseline justify-between mb-1.5">
        <label className="label">
          {slot.label} {slot.required && <span className="text-bad">*</span>}
        </label>
        {slot.help_text && <span className="text-[11px] text-ink-faint">{slot.help_text}</span>}
      </div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          addFiles(e.dataTransfer.files);
        }}
        className={`rounded-xl border-2 border-dashed px-4 py-6 text-center cursor-pointer transition-colors ${
          dragOver ? "border-brand-400 bg-brand-50" : "border-surface-border hover:border-brand-400 hover:bg-surface-muted"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple={slot.multiple}
          accept={slot.accept.join(",")}
          className="hidden"
          onChange={(e) => addFiles(e.target.files)}
        />
        <div className="text-2xl mb-1">📄</div>
        <div className="text-sm font-medium text-ink-muted">
          Click to select {slot.multiple ? "file(s)" : "a file"} or drag &amp; drop
        </div>
        <div className="text-[11px] text-ink-faint mt-1">Accepts {slot.accept.join(", ")}</div>
      </div>
      {files.length > 0 && (
        <div className="mt-2 flex flex-col gap-1 max-h-40 overflow-y-auto">
          {files.map((f) => {
            const ok = matchesPattern(f.name, slot.filename_pattern);
            return (
              <div
                key={f.name}
                className="flex items-center gap-2 rounded-md bg-surface-muted px-2.5 py-1.5 text-xs"
              >
                <span className={ok ? "text-good" : "text-bad"}>{ok ? "✓" : "✗"}</span>
                <span className="flex-1 truncate font-mono">{f.name}</span>
                <span className="text-ink-faint">{(f.size / 1024).toFixed(0)} KB</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    removeFile(f.name);
                  }}
                  className="text-ink-faint hover:text-bad"
                >
                  ✕
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
