import { useState } from "react";
import { ChevronDown, CircleAlert, Image as ImageIcon, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { chartNameFromResult, toolMeta } from "@/lib/tools";
import { cn } from "@/lib/utils";
import { chartUrl } from "@/api/client";
import type { ToolStep } from "@/types";

interface Props {
  step: ToolStep;
  index: number;
  streaming?: boolean;
  /** Inline chart preview (the result screen shows charts in a gallery instead). */
  showChart?: boolean;
}

export function StepCard({ step, index, streaming, showChart = true }: Props) {
  const [open, setOpen] = useState(false);
  const meta = toolMeta(step.tool);
  const Icon = meta.icon;
  const ok = step.status === "ok";
  const chart = ok ? chartNameFromResult(step.result) : null;
  const preview = step.result.length > 180 ? step.result.slice(0, 180) + "…" : step.result;

  return (
    <div className="animate-in-up relative pl-8" style={{ animationDelay: `${Math.min(index, 8) * 40}ms` }}>
      {/* timeline rail */}
      <span
        className={cn(
          "absolute left-3 top-3 z-10 flex size-5 items-center justify-center rounded-full border",
          ok ? "border-success/50 bg-success/15 text-success" : "border-destructive/50 bg-destructive/15 text-destructive",
        )}
      >
        {ok ? <Icon className="size-2.5" /> : <CircleAlert className="size-2.5" />}
      </span>
      {streaming && (
        <span className="absolute left-[15px] top-8 h-[calc(100%-14px)] w-0.5 animate-pulse rounded bg-ring/50" />
      )}
      {!streaming && (
        <span className="absolute left-[15px] top-8 h-[calc(100%-14px)] w-0.5 bg-border" />
      )}

      <Card className={cn("border-border/70 bg-card/60", !ok && "border-destructive/40")}>
        <CardContent className="p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={cn("flex size-6 items-center justify-center rounded-md", meta.tone)}>
              <Icon className="size-3.5" />
            </span>
            <span className="text-sm font-medium">{meta.label}</span>
            <code className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
              {step.tool}
            </code>
            <Badge variant={ok ? "success" : "destructive"} className="ml-auto">
              {ok ? "ok" : "error"}
            </Badge>
          </div>

          <p className="mt-1.5 break-words font-mono text-[11px] leading-4 text-muted-foreground">
            {step.tool === "create_chart" || step.tool === "profile_dataset"
              ? ""
              : JSON.stringify(step.arguments) === "{}"
                ? ""
                : JSON.stringify(step.arguments)}
          </p>

          {chart && showChart && (
            <a href={chartUrl(chart)} target="_blank" rel="noreferrer" className="mt-2 block">
              <img
                src={chartUrl(chart)}
                alt={chart}
                className="max-h-44 rounded-lg border transition hover:scale-[1.01]"
              />
            </a>
          )}

          <button
            onClick={() => setOpen((v) => !v)}
            className="mt-1.5 flex items-center gap-1 text-[11px] text-muted-foreground transition hover:text-foreground"
          >
            <ChevronDown className={cn("size-3 transition-transform", open && "rotate-180")} />
            {open ? "hide result" : "show result"}
            {!open && chart && <ImageIcon className="ml-1 size-3" />}
            {!open && !chart && streaming && <Loader2 className="ml-1 size-3 animate-spin" />}
          </button>

          <pre
            className={cn(
              "mt-1.5 overflow-x-auto whitespace-pre-wrap break-words rounded-md bg-muted/70 p-2 font-mono text-[11px] leading-4 text-foreground/80",
              !open && "hidden",
            )}
          >
            {open ? step.result : preview}
          </pre>
        </CardContent>
      </Card>
    </div>
  );
}
