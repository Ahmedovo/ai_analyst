import type { RefObject } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  ChevronDown,
  ExternalLink,
  Plus,
  Wrench,
} from "lucide-react";
import { StepCard } from "@/components/StepCard";
import { ValidationBadge } from "@/components/ValidationBadge";
import { Markdown } from "@/components/Markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { chartUrl } from "@/api/client";
import { chartNameFromResult } from "@/lib/tools";
import type { AnalysisResult, ChatMessage } from "@/types";

interface Props {
  messages: ChatMessage[];
  dataset: string;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onNewChat: () => void;
  latest: AnalysisResult | null;
  endRef: RefObject<HTMLDivElement | null>;
}

type AssistantMessage = Extract<ChatMessage, { role: "assistant" }>;

function pathBase(p: string): string {
  return p.trim().split(/[\\/]/).pop() ?? "";
}

/** Chart file names for one exchange: chart_paths ∪ create_chart step results. */
function chartsOf(msg: AssistantMessage): string[] {
  const fromPaths = (msg.charts ?? []).map(pathBase);
  const fromSteps = (msg.steps ?? [])
    .filter((s) => s.tool === "create_chart" && s.status === "ok")
    .map((s) => chartNameFromResult(s.result))
    .filter((n): n is string => Boolean(n));
  return Array.from(new Set([...fromPaths, ...fromSteps]));
}

/**
 * Stage 3 — everything the agent returned: markdown answer, grounding
 * verdict, chart gallery, full tool-call audit, raw JSON. A follow-up
 * composer at the bottom feeds the next run.
 */
export function ResultScreen({
  messages,
  dataset,
  input,
  onInputChange,
  onSend,
  onNewChat,
  latest,
  endRef,
}: Props) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="space-y-6">
        {messages.map((msg, i) => {
          if (msg.role === "user") {
            return (
              <div key={i} className="animate-in-up flex justify-end">
                <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
                  {msg.content}
                </div>
              </div>
            );
          }

          if (msg.role === "error") {
            return (
              <div
                key={i}
                className="animate-in-up flex items-start gap-2 rounded-xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                {msg.content}
              </div>
            );
          }

          const charts = chartsOf(msg);
          const steps = msg.steps ?? [];
          const unsupported = msg.validation?.unsupported ?? [];

          return (
            <div key={i} className="animate-in-up space-y-3">
              {/* ---------- answer ---------- */}
              <Card className="shadow-md">
                <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
                  <CardTitle className="flex items-center gap-2 text-sm font-medium">
                    <span className="flex size-6 items-center justify-center rounded-md bg-primary">
                      <BrainCircuit className="size-3.5 text-primary-foreground" />
                    </span>
                    Analyst
                  </CardTitle>
                  <ValidationBadge
                    validation={msg.validation ?? null}
                    retries={msg.retries ?? 0}
                  />
                </CardHeader>
                <CardContent className="space-y-3">
                  {msg.plans && msg.plans.length > 0 && (
                    <div className="space-y-1 rounded-lg bg-muted/60 px-3 py-2">
                      {msg.plans.map((p, j) => (
                        <p
                          key={j}
                          className="text-xs italic text-muted-foreground"
                        >
                          {p}
                        </p>
                      ))}
                    </div>
                  )}
                  <Markdown content={msg.content} />
                  {msg.validation &&
                    !msg.validation.note &&
                    msg.validation.passed !== undefined && (
                      <p className="font-mono text-[10px] text-muted-foreground">
                        {msg.validation.checked ?? 0} number
                        {(msg.validation.checked ?? 0) === 1 ? "" : "s"} in answer
                        vs {msg.validation.tool_results ?? 0} tool results
                        {unsupported.length > 0 && (
                          <> · unsupported: {unsupported.join(", ")}</>
                        )}
                      </p>
                    )}
                </CardContent>
              </Card>

              {/* ---------- charts gallery ---------- */}
              {charts.length > 0 && (
                <div className="animate-in-up">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <BarChart3 className="size-3.5" />
                    Charts produced
                  </h3>
                  <div className="grid gap-3 sm:grid-cols-2">
                    {charts.map((name) => (
                      <a
                        key={name}
                        href={chartUrl(name)}
                        target="_blank"
                        rel="noreferrer"
                        className="group block overflow-hidden rounded-xl border bg-card shadow-sm transition hover:border-primary/40 hover:shadow-md"
                      >
                        <img
                          src={chartUrl(name)}
                          alt={name}
                          className="aspect-[16/10] w-full object-cover transition duration-300 group-hover:scale-[1.03]"
                        />
                        <div className="flex items-center justify-between gap-2 border-t px-3 py-2">
                          <span className="truncate font-mono text-[11px] text-muted-foreground">
                            {name}
                          </span>
                          <ExternalLink className="size-3.5 shrink-0 text-muted-foreground opacity-0 transition group-hover:opacity-100" />
                        </div>
                      </a>
                    ))}
                  </div>
                </div>
              )}

              {/* ---------- tool-call audit ---------- */}
              {steps.length > 0 && (
                <details className="group rounded-xl border bg-card shadow-sm">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium">
                    <span className="flex items-center gap-2">
                      <Wrench className="size-4 text-muted-foreground" />
                      Tool calls
                      <Badge variant="muted">{steps.length}</Badge>
                    </span>
                    <ChevronDown className="size-4 text-muted-foreground transition group-open:rotate-180" />
                  </summary>
                  <div className="space-y-2 border-t p-3">
                    {steps.map((step, j) => (
                      <StepCard key={j} step={step} index={j} showChart={false} />
                    ))}
                  </div>
                </details>
              )}

              {/* ---------- raw result JSON (latest exchange only) ---------- */}
              {latest && i === messages.length - 1 && (
                <details className="group rounded-xl border bg-card shadow-sm">
                  <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium">
                    <span className="flex items-center gap-2">
                      <ChevronDown className="size-4 text-muted-foreground transition group-open:rotate-180" />
                      Raw result JSON
                    </span>
                  </summary>
                  <pre className="overflow-x-auto rounded-b-xl border-t bg-muted/70 p-3 font-mono text-[11px] leading-4 text-foreground/80">
                    {JSON.stringify(latest, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          );
        })}
      </div>

      <div ref={endRef} />

      {/* ---------- follow-up composer ---------- */}
      <div className="sticky bottom-4 z-10 mt-6">
        <Card className="shadow-lg">
          <CardContent className="space-y-2 p-3">
            <div className="flex items-end gap-2">
              <Textarea
                value={input}
                onChange={(e) => onInputChange(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={`Ask a follow-up about ${dataset || "your data"}…`}
                rows={2}
                className="resize-none"
              />
              <Button
                size="lg"
                onClick={onSend}
                disabled={!input.trim() || !dataset}
              >
                Send <ArrowRight />
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <Badge variant="muted">{dataset || "no dataset"}</Badge>
              <span>every number is checked against tool output</span>
              <Button
                variant="ghost"
                size="sm"
                className="ml-auto"
                onClick={onNewChat}
              >
                <Plus /> New chat
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
