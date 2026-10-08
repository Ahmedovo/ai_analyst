import {
  BarChart3,
  FileSearch,
  Layers,
  ShieldCheck,
  Sigma,
  Terminal,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

export interface ToolMeta {
  label: string;
  icon: LucideIcon;
  tone: string;
}

export const TOOL_META: Record<string, ToolMeta> = {
  profile_dataset: { label: "Profile dataset", icon: FileSearch, tone: "text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-500/10" },
  execute_sql: { label: "SQL query", icon: Terminal, tone: "text-emerald-600 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-500/10" },
  group_by: { label: "Group by", icon: Layers, tone: "text-indigo-600 bg-indigo-50 dark:text-indigo-400 dark:bg-indigo-500/10" },
  calculate_statistics: { label: "Statistics", icon: Sigma, tone: "text-amber-600 bg-amber-50 dark:text-amber-400 dark:bg-amber-500/10" },
  detect_anomalies: { label: "Anomaly detection", icon: TriangleAlert, tone: "text-rose-600 bg-rose-50 dark:text-rose-400 dark:bg-rose-500/10" },
  create_chart: { label: "Create chart", icon: BarChart3, tone: "text-sky-600 bg-sky-50 dark:text-sky-400 dark:bg-sky-500/10" },
  validate_data: { label: "Validate data", icon: ShieldCheck, tone: "text-emerald-700 bg-emerald-50 dark:text-emerald-400 dark:bg-emerald-500/10" },
};

export const FALLBACK_META: ToolMeta = {
  label: "Tool",
  icon: Terminal,
  tone: "text-muted-foreground bg-muted",
};

export function toolMeta(name: string): ToolMeta {
  return TOOL_META[name] ?? { ...FALLBACK_META, label: name };
}

/** One-line human summary of a tool call's arguments. */
export function argsSummary(name: string, args: Record<string, unknown>): string {
  if (name === "execute_sql" && typeof args.sql === "string") {
    return args.sql.replace(/\s+/g, " ").trim();
  }
  if (name === "group_by") {
    const by = Array.isArray(args.by) ? args.by.join(", ") : "?";
    const values = Array.isArray(args.values) ? args.values.join(", ") : "?";
    return `${by} → ${values} (${args.agg ?? "sum"})`;
  }
  if (name === "detect_anomalies") {
    return `${args.column ?? ""} · ${args.method ?? "iqr"}${args.threshold ? ` · ${args.threshold}` : ""}`;
  }
  if (name === "create_chart") {
    return [args.chart_type, args.x, args.y].filter(Boolean).join(" · ");
  }
  if (name === "validate_data") {
    const rules = Array.isArray(args.rules) ? args.rules.length : 0;
    return rules === 0 ? "default quality suite" : `${rules} rule${rules > 1 ? "s" : ""}`;
  }
  if (name === "calculate_statistics" && Array.isArray(args.columns)) {
    return args.columns.join(", ");
  }
  const compact = JSON.stringify(args);
  return compact === "{}" ? "no arguments" : compact;
}

/** Extract a PNG file name from a create_chart result path. */
export function chartNameFromResult(result: string): string | null {
  const last = result.trim().split(/[\\/]/).pop() ?? "";
  return last.toLowerCase().endsWith(".png") ? last : null;
}
