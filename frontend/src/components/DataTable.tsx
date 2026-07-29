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

interface Props {
  columns: string[];
  rows: Record<string, unknown>[];
  statusColumn?: string;
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

export default function DataTable({ columns, rows, statusColumn }: Props) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  const colDefs = useMemo<ColumnDef<Record<string, unknown>>[]>(
    () =>
      columns.map((c) => ({
        accessorKey: c,
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
      })),
    [columns, statusColumn]
  );

  const table = useReactTable({
    data: rows,
    columns: colDefs,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
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
          {table.getFilteredRowModel().rows.length} / {rows.length} rows
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
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-ink-faint">
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
