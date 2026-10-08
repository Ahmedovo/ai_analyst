import { useRef } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Database,
  FileSpreadsheet,
  GitBranch,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Upload,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import type { DatasetInfo } from "@/types";

const EXAMPLES = [
  "Profile this dataset and summarise what you find",
  "Which region and product generate the most revenue?",
  "Why did revenue decrease in Q3?",
  "Are there any anomalies in units sold?",
  "Validate data quality, then find the top 3 products",
];

interface Props {
  datasets: DatasetInfo[];
  dataset: string;
  onChange: (name: string) => void;
  onUpload: (file: File) => void;
  onRefresh: () => void;
  busy?: boolean;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  error: string | null;
  maxTurns: number;
  onMaxTurnsChange: (value: number) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

/**
 * Stage 1 — the first page: pick/upload a dataset, type a question, send.
 * Chat-style composer, centred, professional.
 */
export function IntakeScreen({
  datasets,
  dataset,
  onChange,
  onUpload,
  onRefresh,
  busy,
  input,
  onInputChange,
  onSend,
  error,
  maxTurns,
  onMaxTurnsChange,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const selected = datasets.find((d) => d.name === dataset);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-3.5rem)] max-w-2xl flex-col justify-center px-4 py-10">
      {/* hero */}
      <div className="mb-7 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-xl bg-primary shadow-lg shadow-primary/20">
          <Sparkles className="size-6 text-primary-foreground" />
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Ask your data anything
        </h1>
        <p className="mx-auto mt-2 max-w-lg text-sm text-muted-foreground">
          An autonomous agent plans, runs tools against your CSV and answers —
          with every number validated against real tool output.
        </p>
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Badge variant="outline">
            <GitBranch className="text-primary" /> live agent loop
          </Badge>
          <Badge variant="outline">
            <BarChart3 className="text-primary" /> 7 tools
          </Badge>
          <Badge variant="outline">
            <ShieldCheck className="text-success" /> grounded answers
          </Badge>
        </div>
      </div>

      {error && (
        <div className="animate-in-up mb-4 flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          {error}
        </div>
      )}

      {/* composer + dataset controls */}
      <Card className="shadow-md">
        <CardContent className="space-y-3 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Database className="size-4 text-muted-foreground" />
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Dataset
            </span>
            <select
              value={dataset}
              onChange={(e) => onChange(e.target.value)}
              disabled={busy}
              className="h-8 max-w-56 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 disabled:opacity-50"
            >
              {datasets.length === 0 && <option value="">no CSVs in data/</option>}
              {datasets.map((d) => (
                <option key={d.name} value={d.name}>
                  {d.name}
                </option>
              ))}
            </select>
            {selected && (
              <span className="text-xs text-muted-foreground">
                {formatSize(selected.size)}
              </span>
            )}
            <div className="ml-auto flex items-center gap-1.5">
              <Button
                variant="ghost"
                size="icon"
                onClick={onRefresh}
                aria-label="Refresh datasets"
              >
                <RefreshCw className={busy ? "animate-spin" : undefined} />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
              >
                <Upload /> Upload CSV
              </Button>
              <input
                ref={fileRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) onUpload(file);
                  e.target.value = "";
                }}
              />
            </div>
          </div>

          <Textarea
            value={input}
            onChange={(e) => onInputChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the agent about your data… (Enter to send, Shift+Enter for newline)"
            rows={3}
            className="resize-none"
          />

          <div className="flex items-center justify-between gap-3">
            <label className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              Max turns
              <select
                value={maxTurns}
                onChange={(e) => onMaxTurnsChange(Number(e.target.value))}
                className="h-6 rounded-md border border-input bg-background px-1 text-[11px] shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
              >
                {[4, 6, 8, 12, 16].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <span className="hidden sm:inline">
                · answer validated before display
              </span>
            </label>
            <Button
              size="lg"
              onClick={onSend}
              disabled={!input.trim() || !dataset}
            >
              Ask the agent <ArrowRight />
            </Button>
          </div>

          {datasets.length === 0 && (
            <div className="flex items-center gap-2 rounded-lg bg-warning/10 px-3 py-2 text-xs text-warning">
              <FileSpreadsheet className="size-3.5" />
              No datasets in data/ — upload a CSV to get started.
            </div>
          )}
        </CardContent>
      </Card>

      {/* example prompts */}
      <div className="mt-6">
        <p className="mb-2 text-center text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Try asking
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {EXAMPLES.map((q) => (
            <button
              key={q}
              onClick={() => onInputChange(q)}
              className="rounded-full border bg-card px-3 py-1.5 text-xs text-muted-foreground transition hover:border-primary/40 hover:bg-accent hover:text-foreground"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
