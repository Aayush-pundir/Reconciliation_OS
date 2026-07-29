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

function matchesAccept(name: string, accept: string[]): boolean {
  if (accept.length === 0) return true;
  const lower = name.toLowerCase();
  return accept.some((ext) => lower.endsWith(ext.toLowerCase()));
}

// Folders (via webkitdirectory or a dropped directory) surface every file
// underneath, including junk like .DS_Store or unrelated siblings - unlike a
// manual OS file-picker selection, so only folder-sourced files get
// extension-filtered against the slot's accept list.
function filterFolderFiles(incoming: File[], accept: string[]): File[] {
  return incoming.filter((f) => matchesAccept(f.name, accept));
}

// Recursively walks a dropped folder's FileSystemEntry tree (drag-and-drop
// only exposes this API, not File[], for directories) and resolves every
// leaf file it finds.
async function readEntry(entry: FileSystemEntry): Promise<File[]> {
  if (entry.isFile) {
    return new Promise((resolve) => {
      (entry as FileSystemFileEntry).file(
        (file) => resolve([file]),
        () => resolve([])
      );
    });
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    const entries: FileSystemEntry[] = await new Promise((resolve) => {
      const all: FileSystemEntry[] = [];
      const readBatch = () => {
        reader.readEntries((batch) => {
          if (batch.length === 0) {
            resolve(all);
          } else {
            all.push(...batch);
            readBatch();
          }
        }, () => resolve(all));
      };
      readBatch();
    });
    const nested = await Promise.all(entries.map(readEntry));
    return nested.flat();
  }
  return [];
}

export default function FileDropzone({ slot, files, onChange }: Props) {
  const [dragOver, setDragOver] = useState(false);
  const [isScanning, setIsScanning] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback(
    (incoming: File[]) => {
      if (incoming.length === 0) return;
      const next = slot.multiple ? [...files, ...incoming] : [incoming[0]];
      const seen = new Set<string>();
      const deduped = next.filter((f) => (seen.has(f.name) ? false : seen.add(f.name)));
      onChange(deduped);
    },
    [files, onChange, slot.multiple]
  );

  const removeFile = (name: string) => onChange(files.filter((f) => f.name !== name));

  const handleDrop = useCallback(
    async (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      setDragOver(false);

      const items = e.dataTransfer.items;
      const hasEntryApi = items.length > 0 && typeof items[0]?.webkitGetAsEntry === "function";
      if (!hasEntryApi) {
        addFiles(Array.from(e.dataTransfer.files));
        return;
      }

      setIsScanning(true);
      try {
        const entries = Array.from(items)
          .map((item) => item.webkitGetAsEntry())
          .filter((entry): entry is FileSystemEntry => entry !== null);
        const isFolderDrop = entries.some((entry) => entry.isDirectory);
        const nested = await Promise.all(entries.map(readEntry));
        const collected = nested.flat();
        addFiles(isFolderDrop ? filterFolderFiles(collected, slot.accept) : collected);
      } finally {
        setIsScanning(false);
      }
    },
    [addFiles, slot.accept]
  );

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
        onDrop={handleDrop}
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
          onChange={(e) => addFiles(Array.from(e.target.files ?? []))}
        />
        {slot.multiple && (
          <input
            ref={folderInputRef}
            type="file"
            // @ts-expect-error non-standard attributes, Chrome/Safari/Firefox all support them
            webkitdirectory=""
            directory=""
            multiple
            className="hidden"
            onChange={(e) => {
              addFiles(filterFolderFiles(Array.from(e.target.files ?? []), slot.accept));
              e.target.value = "";
            }}
          />
        )}
        <div className="text-2xl mb-1">{isScanning ? "⏳" : "📄"}</div>
        <div className="text-sm font-medium text-ink-muted">
          {isScanning
            ? "Scanning folder…"
            : `Click to select ${slot.multiple ? "file(s)" : "a file"} or drag & drop`}
        </div>
        <div className="text-[11px] text-ink-faint mt-1">Accepts {slot.accept.join(", ")} — folders supported</div>
        {slot.multiple && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              folderInputRef.current?.click();
            }}
            className="mt-2 text-xs font-medium text-brand-600 hover:text-brand-700 underline underline-offset-2"
          >
            or select a whole folder
          </button>
        )}
      </div>
      {files.length > 0 && (
        <div className="mt-2 flex flex-col gap-1 max-h-40 overflow-y-auto">
          <div className="text-[11px] text-ink-faint px-0.5">{files.length} file(s) selected</div>
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
