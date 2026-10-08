import { Check, ShieldCheck, Sparkles, Wrench } from "lucide-react";
import { cn } from "@/lib/utils";
import type { GraphNode } from "@/types";

interface Props {
  active: GraphNode | null;
  counts: Record<GraphNode, number>;
  done: boolean;
  streaming: boolean;
}

interface NodeDef {
  key: GraphNode | "answer";
  title: string;
  subtitle: string;
  icon: typeof Sparkles;
}

const NODES: NodeDef[] = [
  { key: "agent", title: "agent", subtitle: "plans the next move", icon: Sparkles },
  { key: "tools", title: "tools", subtitle: "runs computations", icon: Wrench },
  { key: "validate", title: "validate", subtitle: "grounds every number", icon: ShieldCheck },
  { key: "answer", title: "answer", subtitle: "delivered to you", icon: Check },
];

/**
 * Live visualization of the LangGraph loop:
 *   agent ⇄ tools → validate → answer
 */
export function TraceGraph({ active, counts, done, streaming }: Props) {
  return (
    <div className="grid grid-cols-4 gap-1.5">
      {NODES.map((node, i) => {
        const isAnswer = node.key === "answer";
        const count = isAnswer ? (done ? 1 : 0) : counts[node.key as GraphNode];
        const isActive = !isAnswer && active === node.key;
        const isDone = count > 0 && !isActive;
        const Icon = node.icon;

        return (
          <div key={node.key} className="flex items-center gap-1.5">
            <div
              className={cn(
                "flex min-w-0 flex-1 flex-col items-center gap-1 rounded-lg border px-1.5 py-2.5 text-center transition-all duration-300",
                isActive && "border-ring bg-accent pulse-ring",
                isDone && "border-success/50 bg-success/10",
                !isActive && !isDone && "border-border bg-card opacity-60",
              )}
            >
              <div
                className={cn(
                  "flex size-7 items-center justify-center rounded-full border transition-colors",
                  isActive && "border-ring bg-ring/15 text-ring",
                  isDone && "border-success/60 bg-success/15 text-success",
                  !isActive && !isDone && "border-border text-muted-foreground",
                )}
              >
                {isDone && !isActive ? <Check className="size-3.5" /> : <Icon className="size-3.5" />}
              </div>
              <div className="min-w-0">
                <div className="truncate font-mono text-[11px] font-medium">{node.title}</div>
                <div className="hidden truncate text-[9px] text-muted-foreground sm:block">
                  {node.subtitle}
                </div>
              </div>
              {count > 0 && (
                <span className="rounded bg-background/70 px-1 font-mono text-[9px] text-muted-foreground">
                  ×{count}
                </span>
              )}
            </div>

            {i < NODES.length - 1 && (
              <div
                className={cn(
                  "h-0.5 w-3 shrink-0 rounded-full transition-colors",
                  streaming && "flow-line",
                  done && "bg-success/60",
                  !streaming && !done && "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
