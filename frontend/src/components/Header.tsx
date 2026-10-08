import { BrainCircuit, Moon, Sun } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { HealthInfo } from "@/types";

interface Props {
  health: HealthInfo | null;
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export function Header({ health, theme, onToggleTheme }: Props) {
  const llmReady = health?.llm_available ?? false;
  return (
    <header className="sticky top-0 z-20 border-b bg-background/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-3 px-4">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary shadow-sm">
          <BrainCircuit className="size-4.5 text-primary-foreground" />
        </div>
        <div className="flex flex-col">
          <span className="text-sm font-semibold leading-tight">AI Data Analyst</span>
          <span className="text-[11px] leading-tight text-muted-foreground">
            LangGraph agent · 7 tools · grounded answers
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2">
          {health && (
            <Badge variant="muted" className="hidden sm:inline-flex">
              <span
                className={`size-1.5 rounded-full ${
                  llmReady ? "bg-success" : "bg-warning"
                }`}
              />
              {health.provider} / {health.model}
            </Badge>
          )}
          <Badge variant={llmReady ? "success" : "warning"} className="hidden md:inline-flex">
            {llmReady ? "LLM ready" : "LLM key missing"}
          </Badge>
          <Button
            variant="ghost"
            size="icon"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
          >
            {theme === "dark" ? <Sun /> : <Moon />}
          </Button>
        </div>
      </div>
    </header>
  );
}
