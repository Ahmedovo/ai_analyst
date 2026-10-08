import { useCallback, useEffect, useRef, useState } from "react";
import { Header } from "@/components/Header";
import { IntakeScreen } from "@/components/IntakeScreen";
import { RunningScreen } from "@/components/RunningScreen";
import { ResultScreen } from "@/components/ResultScreen";
import {
  fetchDatasets,
  fetchHealth,
  streamAnalyze,
  uploadDataset,
} from "@/api/client";
import type {
  AnalysisResult,
  ChatMessage,
  DatasetInfo,
  GraphNode,
  HealthInfo,
  ToolStep,
  Validation,
} from "@/types";

/**
 * Three-stage flow:
 *   intake   — chat composer + dataset upload/select (first page)
 *   running  — animated live agent trace (graph, plans, tool timeline)
 *   result   — every AI return: answer, validation, charts, tool audit,
 *              raw JSON, plus a follow-up composer
 */
type Stage = "intake" | "running" | "result";

const EMPTY_COUNTS: Record<GraphNode, number> = { agent: 0, tools: 0, validate: 0 };

function pathBase(p: string): string {
  return p.trim().split(/[\\/]/).pop() ?? "";
}

export default function App() {
  // ---- global state -------------------------------------------------------
  const [theme, setTheme] = useState<"dark" | "light">("light");
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [datasets, setDatasets] = useState<DatasetInfo[]>([]);
  const [dataset, setDataset] = useState<string>("");
  const [datasetsBusy, setDatasetsBusy] = useState(false);

  // ---- stage + conversation ----------------------------------------------
  const [stage, setStage] = useState<Stage>("intake");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [intakeError, setIntakeError] = useState<string | null>(null);
  const [maxTurns, setMaxTurns] = useState(12);

  // ---- live trace ---------------------------------------------------------
  const [question, setQuestion] = useState("");
  const [activeNode, setActiveNode] = useState<GraphNode | null>(null);
  const [counts, setCounts] = useState(EMPTY_COUNTS);
  const [plans, setPlans] = useState<string[]>([]);
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [retries, setRetries] = useState(0);
  const [result, setResult] = useState<AnalysisResult | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  // latest plans/retries for use inside the streaming loop (stale closures)
  const plansRef = useRef<string[]>([]);
  plansRef.current = plans;
  const retriesRef = useRef(0);
  retriesRef.current = retries;

  // ---- effects ------------------------------------------------------------
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  const refreshDatasets = useCallback(async () => {
    setDatasetsBusy(true);
    try {
      const list = await fetchDatasets();
      setDatasets(list);
      setDataset((current) =>
        current && list.some((d) => d.name === current)
          ? current
          : (list[0]?.name ?? ""),
      );
    } catch {
      /* backend down — intake shows the empty hint */
    } finally {
      setDatasetsBusy(false);
    }
  }, []);

  useEffect(() => {
    refreshDatasets();
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, [refreshDatasets]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, steps.length, plans.length, stage]);

  // ---- actions ------------------------------------------------------------
  async function handleUpload(file: File) {
    setIntakeError(null);
    setDatasetsBusy(true);
    try {
      const { name } = await uploadDataset(file);
      await refreshDatasets();
      setDataset(name);
    } catch (err) {
      setIntakeError(`Upload failed: ${(err as Error).message}`);
    } finally {
      setDatasetsBusy(false);
    }
  }

  function stopRun() {
    abortRef.current?.abort();
  }

  function newChat() {
    abortRef.current?.abort();
    setMessages([]);
    setResult(null);
    setInput("");
    setIntakeError(null);
    setStage("intake");
  }

  async function runQuestion(raw: string) {
    const q = raw.trim();
    if (!q || stage === "running") return;
    if (!dataset) {
      setIntakeError("No dataset selected — upload a CSV first.");
      return;
    }

    setIntakeError(null);
    setInput("");
    setQuestion(q);
    setMessages((m) => [...m, { role: "user", content: q }]);
    setStage("running");
    setActiveNode(null);
    setCounts(EMPTY_COUNTS);
    setPlans([]);
    setSteps([]);
    setValidation(null);
    setRetries(0);
    setResult(null);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamAnalyze(
        { dataset, question: q, max_turns: maxTurns },
        controller.signal,
      )) {
        switch (event.type) {
          case "node": {
            setActiveNode(event.node);
            setCounts((c) => ({ ...c, [event.node]: c[event.node] + 1 }));
            break;
          }
          case "plan": {
            setPlans((p) => [...p, event.text]);
            break;
          }
          case "step": {
            setSteps((s) => [...s, event.step]);
            break;
          }
          case "validation": {
            setValidation(event.validation);
            break;
          }
          case "retry": {
            setRetries((r) => r + 1);
            break;
          }
          case "error": {
            setMessages((m) => [
              ...m,
              { role: "error", content: `Agent error: ${event.message}` },
            ]);
            break;
          }
          case "done": {
            const charts = (event.result.chart_paths ?? [])
              .map(pathBase)
              .filter((n) => n.toLowerCase().endsWith(".png"));
            setResult(event.result);
            setValidation(event.result.validation);
            setActiveNode(null);
            setMessages((m) => [
              ...m,
              {
                role: "assistant",
                content: event.result.answer || "(no answer produced)",
                validation: event.result.validation,
                plans: plansRef.current,
                steps: event.result.steps,
                charts,
                retries: retriesRef.current,
                dataset,
              },
            ]);
            break;
          }
        }
      }
      setActiveNode(null);
      setStage("result");
    } catch (err) {
      setActiveNode(null);
      const error = err as Error;
      if (error.name === "AbortError") {
        setMessages((m) => [
          ...m,
          { role: "error", content: "⏹ Run stopped by user." },
        ]);
      } else {
        setMessages((m) => [
          ...m,
          {
            role: "error",
            content: `Request failed: ${error.message}. Is the API running? (uvicorn app.api.main:app)`,
          },
        ]);
      }
      setStage("result");
    } finally {
      abortRef.current = null;
    }
  }

  return (
    <div className="min-h-screen">
      <Header
        health={health}
        theme={theme}
        onToggleTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
      />

      <main>
        {stage === "intake" && (
          <IntakeScreen
            datasets={datasets}
            dataset={dataset}
            onChange={setDataset}
            onUpload={(f) => void handleUpload(f)}
            onRefresh={() => void refreshDatasets()}
            busy={datasetsBusy}
            input={input}
            onInputChange={setInput}
            onSend={() => void runQuestion(input)}
            error={intakeError}
            maxTurns={maxTurns}
            onMaxTurnsChange={setMaxTurns}
          />
        )}

        {stage === "running" && (
          <RunningScreen
            question={question}
            dataset={dataset}
            activeNode={activeNode}
            counts={counts}
            plans={plans}
            steps={steps}
            validation={validation}
            retries={retries}
            onStop={stopRun}
            endRef={endRef}
          />
        )}

        {stage === "result" && (
          <ResultScreen
            messages={messages}
            dataset={dataset}
            input={input}
            onInputChange={setInput}
            onSend={() => void runQuestion(input)}
            onNewChat={newChat}
            latest={result}
            endRef={endRef}
          />
        )}
      </main>
    </div>
  );
}
