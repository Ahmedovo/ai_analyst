import type { RefObject } from "react";
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  BrainCircuit,
  ExternalLink,
  Plus,
} from "lucide-react";
import { ValidationBadge } from "@/components/ValidationBadge";
import { Markdown } from "@/components/Markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { chartUrl } from "@/api/client";
import { chartNameFromResult } from "@/lib/tools";
import type { ChatMessage } from "@/types";

interface Props {
  messages: ChatMessage[];
  dataset: string;
  input: string;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onNewChat: () => void;
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
 * Stage 3 — just the answer: the markdown answer with its grounding verdict
 * and any charts it produced, plus a follow-up composer. Agent reasoning,
 * the tool audit, and raw JSON are intentionally not shown.
 */
export function ResultScreen({
  messages,
  dataset,
  input,
  onInputChange,
  onSend,
  onNewChat,
  endRef,
}: Props) {
  const exchangeCount = messages.filter((m) => m.role === "assistant").length;

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
                <CardContent>
                  <Markdown content={msg.content} />
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
              {exchangeCount > 1 && (
                <Badge variant="outline" className="border-primary/30 text-primary">
                  follow-up context · {exchangeCount} exchanges
                </Badge>
              )}
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