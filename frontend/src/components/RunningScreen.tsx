import type { RefObject } from "react";
import { AlertTriangle, Sparkles, Square } from "lucide-react";
import { TraceGraph } from "@/components/TraceGraph";
import { StepCard } from "@/components/StepCard";
import { ValidationBadge } from "@/components/ValidationBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { GraphNode, ToolStep, Validation } from "@/types";

interface Props {
  question: string;
  dataset: string;
  activeNode: GraphNode | null;
  counts: Record<GraphNode, number>;
  plans: string[];
  steps: ToolStep[];
  validation: Validation | null;
  retries: number;
  onStop: () => void;
  endRef: RefObject<HTMLDivElement | null>;
}

/**
 * Stage 2 — the live agent trace: animated graph, streaming plans,
 * tool-call timeline and the grounding check, with a Stop button.
 */
export function RunningScreen({
  question,
  dataset,
  activeNode,
  counts,
  plans,
  steps,
  validation,
  retries,
  onStop,
  endRef,
}: Props) {
  return (
    <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
      {/* echo of the question being worked on */}
      <div className="animate-in-up flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground shadow-sm">
          {question}
        </div>
      </div>

      {/* indeterminate progress bar */}
      <div className="h-1 overflow-hidden rounded-full bg-muted">
        <div className="progress-slide h-full w-1/4 rounded-full bg-primary" />
      </div>

      <Card className="shadow-md">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3">
          <CardTitle className="flex items-center gap-2 text-sm font-medium">
            <span className="size-2 animate-pulse rounded-full bg-primary" />
            Live agent trace
          </CardTitle>
          <Badge variant="muted">{dataset}</Badge>
        </CardHeader>
        <CardContent className="space-y-4">
          <TraceGraph active={activeNode} counts={counts} done={false} streaming />

          {/* status line */}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.2s]" />
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary/60 [animation-delay:-0.1s]" />
            <span className="inline-block size-1.5 animate-bounce rounded-full bg-primary/30" />
            <span className="ml-1">
              {activeNode ? `running ${activeNode} node…` : "thinking…"}
            </span>
          </div>

          {/* plans stream in while the agent reasons */}
          {plans.length > 0 && (
            <div className="space-y-1.5 rounded-lg border bg-card/60 p-3">
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Plan
              </div>
              {plans.map((p, j) => (
                <p
                  key={j}
                  className="animate-in-up flex items-start gap-1.5 text-xs italic text-muted-foreground"
                >
                  <Sparkles className="mt-0.5 size-3 shrink-0 text-primary/70" />
                  {p}
                </p>
              ))}
            </div>
          )}

          {retries > 0 && (
            <div className="flex items-center gap-2 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
              <AlertTriangle className="size-3.5" />
              Validation bounced the answer back {retries}× for correction
            </div>
          )}

          {/* tool timeline */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Tool calls
              </span>
              <Badge variant="muted">{steps.length}</Badge>
            </div>
            {steps.length === 0 ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full" />
                <Skeleton className="h-16 w-full" />
              </div>
            ) : (
              <div className="space-y-2">
                {steps.map((step, i) => (
                  <StepCard
                    key={i}
                    step={step}
                    index={i}
                    streaming={i === steps.length - 1}
                  />
                ))}
              </div>
            )}
          </div>

          {/* grounding check */}
          <div className="rounded-lg border bg-card/60 p-3">
            <div className="mb-1.5 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Grounding check
            </div>
            <ValidationBadge validation={validation} retries={retries} streaming />
            {validation && !validation.note && validation.passed !== undefined && (
              <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                {validation.checked ?? 0} number
                {(validation.checked ?? 0) === 1 ? "" : "s"} in answer vs{" "}
                {validation.tool_results ?? 0} tool result
                {(validation.tool_results ?? 0) === 1 ? "" : "s"}
                {(validation.unsupported?.length ?? 0) > 0 && (
                  <> · unsupported: {validation.unsupported?.join(", ")}</>
                )}
              </p>
            )}
          </div>

          <div ref={endRef} />
        </CardContent>
      </Card>

      <div className="flex justify-center">
        <Button variant="destructive" size="lg" onClick={onStop}>
          <Square /> Stop run
        </Button>
      </div>
    </div>
  );
}
