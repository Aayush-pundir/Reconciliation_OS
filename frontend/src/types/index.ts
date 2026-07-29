export type FindingLevel = "ok" | "warn" | "err";
export type SheetKind = "summary" | "detail" | "exception" | "validation";
export type StatTone = "neutral" | "good" | "bad" | "warn";

export type RunStatus =
  | "created"
  | "uploaded"
  | "queued"
  | "parsing"
  | "validating"
  | "matching"
  | "reporting"
  | "completed"
  | "failed";

export interface InputSlot {
  key: string;
  label: string;
  accept: string[];
  multiple: boolean;
  required: boolean;
  filename_pattern: string | null;
  help_text: string | null;
}

export interface ModuleSchema {
  key: string;
  display_name: string;
  description: string;
  version: string;
  input_slots: InputSlot[];
  options_schema: {
    properties?: Record<string, { type?: string; default?: unknown; description?: string; title?: string }>;
  };
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: "analyst" | "admin";
}

export interface RunFile {
  id: string;
  slot: string;
  original_filename: string;
  size_bytes: number;
  validation_ok: boolean;
  validation_note: string | null;
}

export interface RunEvent {
  from_status: string;
  to_status: string;
  message: string | null;
  created_at: string;
}

export interface Run {
  id: string;
  module_key: string;
  module_version: string;
  status: RunStatus;
  triggered_by: string | null;
  options: Record<string, unknown>;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface RunDetail extends Run {
  files: RunFile[];
  events: RunEvent[];
  has_report: boolean;
}

export interface RunResultItem {
  kind: SheetKind;
  sheet_name: string;
  columns: string[] | null;
  row_index: number;
  payload: Record<string, unknown>;
}

export interface RunResultPage {
  total: number;
  items: RunResultItem[];
}

export interface RunListPage {
  total: number;
  items: Run[];
}

// Stat cards and validation findings arrive as `kind: "summary"` / `kind: "validation"`
// RunResult rows respectively - these shapes mirror ReconOutput.StatCard / ValidationFinding
// on the backend (app/recon/base.py).
export interface StatCardPayload {
  label: string;
  value: string;
  tone: StatTone;
  sub?: string | null;
}

export interface ValidationFindingPayload {
  pass_name: string;
  check: string;
  level: FindingLevel;
  message: string;
}
