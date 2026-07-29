import { useMemo, useState } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import type { RunResultItem } from "@/types";

interface Props {
  columns: string[];
  items: RunResultItem[];
  statusColumn?: string;
  annotatable?: boolean;
  onAnnotate?: (resultId: string, status: string, note: string) => void;
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
  return String(value);
}

const STATUS_TONES: Record<string, string> = {
  MATCHED: "text-good",
  Matched: "text-good",
  "Successfully Completed": "text-good",
  "AMOUNT MISMATCH": "text-bad",
  DEFICIT: "text-bad",
  "EXCESS DEBIT": "text-bad",
  Failed: "text-bad",
  "NOT IN BANK": "text-bad",
  "NOT IN OPS": "text-warn",
  PENDING: "text-warn",
  Refund: "text-warn",
  "To Check": "text-warn",
  "Manual Check Required": "text-warn",
  Cancelled: "text-ink-muted",
};

const ANNOTATION_LABEL: Record<string, string> = {
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

function AnnotationCell({
  item,
  onAnnotate,
}: {
  item: RunResultItem;
  onAnnotate: (resultId: string, status: string, note: string) => void;
}) {
  const [editingNote, setEditingNote] = useState(false);
  const [note, setNote] = useState(item.annotation_note ?? "");

  if (!item.id) return null;
  const id = item.id;
  const status = item.annotation_status;

  if (status) {
    return (
      <div className="flex items-center gap-1.5 whitespace-nowrap">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded ${
            status === "resolved" ? "bg-good/10 text-good" : "bg-warn/10 text-warn"
          }`}
        >
          {ANNOTATION_LABEL[status] ?? status}
        </span>
        {editingNote ? (
          <input
            autoFocus
            className="input !py-0.5 !px-1.5 text-[11px] w-32"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => {
              setEditingNote(false);
              onAnnotate(id, status, note);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
          />
        ) : (
          <button
            onClick={() => setEditingNote(true)}
            className="text-[11px] text-ink-faint hover:text-ink underline underline-offset-2 truncate max-w-[8rem]"
            title={item.annotation_note ?? "Add a note"}
          >
            {item.annotation_note || "+ note"}
          </button>
        )}
        <button onClick={() => onAnnotate(id, "", "")} className="text-ink-faint hover:text-bad text-[11px]" title="Clear">
          ✕
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-1 whitespace-nowrap">
      <button
        onClick={() => onAnnotate(id, "acknowledged", note)}
        className="text-[11px] px-1.5 py-0.5 rounded border border-surface-border text-ink-muted hover:border-warn hover:text-warn"
      >
        Acknowledge
      </button>
      <button
        onClick={() => onAnnotate(id, "resolved", note)}
        className="text-[11px] px-1.5 py-0.5 rounded border border-surface-border text-ink-muted hover:border-good hover:text-good"
      >
        Resolve
      </button>
    </div>
  );
}

export default function DataTable({ columns, items, statusColumn, annotatable, onAnnotate }: Props) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const colDefs = useMemo<ColumnDef<RunResultItem>[]>(() => {
    const dataCols: ColumnDef<RunResultItem>[] = columns.map((c) => ({
      id: c,
      accessorFn: (row) => row.payload[c],
      header: c,
      cell: (info) => {
        const value = info.getValue();
        const text = formatCell(value);
        if (c === statusColumn) {
          const tone = STATUS_TONES[text] ?? "text-ink";
          return <span className={`font-semibold ${tone}`}>{text}</span>;
        }
        return <span>{text}</span>;
      },
    }));
    if (annotatable && onAnnotate) {
      dataCols.push({
        id: "__annotation",
        header: "Exception Action",
        cell: (info) => <AnnotationCell item={info.row.original} onAnnotate={onAnnotate} />,
      });
    }
    return dataCols;
  }, [columns, statusColumn, annotatable, onAnnotate]);

  const table = useReactTable({
    data: items,
    columns: colDefs,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
    globalFilterFn: (row, _columnId, filterValue) => {
      const needle = String(filterValue).toLowerCase();
      return columns.some((c) => formatCell(row.original.payload[c]).toLowerCase().includes(needle));
    },
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <input
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          placeholder="Search…"
          className="input max-w-xs"
        />
        <span className="text-xs text-ink-faint">
          {table.getFilteredRowModel().rows.length} / {items.length} rows
        </span>
      </div>
      <div className="overflow-auto max-h-[520px] rounded-lg border border-surface-border">
        <table className="w-full text-xs border-collapse">
          <thead className="sticky top-0 bg-surface-muted z-10">
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th
                    key={h.id}
                    onClick={h.column.getToggleSortingHandler()}
                    className="text-left font-semibold text-ink-muted px-3 py-2 whitespace-nowrap cursor-pointer select-none border-b border-surface-border"
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                    {{ asc: " ↑", desc: " ↓" }[h.column.getIsSorted() as string] ?? ""}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-surface-border last:border-0 hover:bg-surface-muted/60">
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-1.5 whitespace-nowrap font-mono">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={columns.length + (annotatable ? 1 : 0)} className="px-3 py-8 text-center text-ink-faint">
                  No rows.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
