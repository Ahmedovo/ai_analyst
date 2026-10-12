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
  ChatMessage,
  DatasetInfo,
  GraphNode,
  HealthInfo,
  HistoryTurn,
  ToolStep,
  Validation,
} from "@/types";

/**
 * Three-stage flow:
 *   intake   — chat composer + dataset upload/select (first page)
 *   running  — animated live agent trace (graph, tool timeline)
 *   result   — just the answer, its charts, and the follow-up composer
 */
type Stage = "intake" | "running" | "result";

const EMPTY_COUNTS: Record<GraphNode, number> = { agent: 0, tools: 0, validate: 0 };

//: cap the history carried into a follow-up request (payload size + latency)
const MAX_HISTORY_TURNS = 10;
const MAX_EVIDENCE_CHARS = 4000;
//: prior answers replay into the LLM context, so keep only the conclusion
//: (answers state the conclusion first; the full tables cost real tokens)
const MAX_PRIOR_ANSWER_CHARS = 800;

function pathBase(p: string): string {
  return p.trim().split(/[\\/]/).pop() ?? "";
}

/** Collapse the message thread into replayable turns (oldest first, capped). */
function buildHistory(messages: ChatMessage[]): HistoryTurn[] {
  const turns: HistoryTurn[] = [];
  let pending: string | null = null;
  for (const msg of messages) {
    if (msg.role === "user") {
      pending = msg.content;
    } else if (msg.role === "assistant" && pending !== null) {
      const answer = msg.content.slice(0, MAX_PRIOR_ANSWER_CHARS);
      turns.push({
        question: pending,
        answer,
        tool_results: (msg.steps ?? []).map((s) =>
          s.result.slice(0, MAX_EVIDENCE_CHARS),
        ),
      });
      pending = null;
    }
  }
  return turns.slice(-MAX_HISTORY_TURNS);
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
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [validation, setValidation] = useState<Validation | null>(null);
  const [retries, setRetries] = useState(0);

  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);

  // latest retries for use inside the streaming loop (stale closures)
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
  }, [messages.length, steps.length, stage]);

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

    // Capture context BEFORE the new user turn is appended — messages may
    // already include prior Q&A from earlier runs in this conversation.
    const history = buildHistory(messages);

    setMessages((m) => [...m, { role: "user", content: q }]);
    setStage("running");
    setActiveNode(null);
    setCounts(EMPTY_COUNTS);
    setSteps([]);
    setValidation(null);
    setRetries(0);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of streamAnalyze(
        { dataset, question: q, max_turns: maxTurns, history },
        controller.signal,
      )) {
        switch (event.type) {
          case "node": {
            setActiveNode(event.node);
            setCounts((c) => ({ ...c, [event.node]: c[event.node] + 1 }));
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
            setValidation(event.result.validation);
            setActiveNode(null);
            setMessages((m) => [
              ...m,
              {
                role: "assistant",
                content: event.result.answer || "(no answer produced)",
                validation: event.result.validation,
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
            content: `Request failed: ${error.message}. Is the API running? (.venv\\Scripts\\python.exe -m uvicorn app.api.main:app --port 8000 --app-dir .venv)`,
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
            endRef={endRef}
          />
        )}
      </main>
    </div>
  );
}
