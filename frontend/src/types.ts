/** Types mirroring the FastAPI backend schemas. */

export interface HealthInfo {
  status: string;
  provider: string;
  model: string;
  llm_available: boolean;
}

export interface DatasetInfo {
  name: string;
  size: number;
}

export interface ToolStep {
  tool: string;
  arguments: Record<string, unknown>;
  status: "ok" | "error";
  result: string;
}

export interface Validation {
  passed?: boolean;
  checked?: number;
  unsupported?: string[];
  tool_results?: number;
  note?: string;
}

export interface AnalysisResult {
  dataset: string;
  question: string;
  answer: string;
  steps: ToolStep[];
  validation: Validation;
  chart_paths?: string[];
}

export type GraphNode = "agent" | "tools" | "validate";

export type StreamEvent =
  | { type: "node"; node: GraphNode }
  | { type: "plan"; text: string }
  | { type: "step"; step: ToolStep }
  | { type: "validation"; validation: Validation }
  | { type: "retry"; unsupported: string[] }
  | { type: "done"; result: AnalysisResult }
  | { type: "error"; message: string };

export type ChatMessage =
  | { role: "user"; content: string }
  | {
      role: "assistant";
      content: string;
      validation?: Validation;
      steps?: ToolStep[];
      charts?: string[];
      retries?: number;
      dataset?: string;
    }
  | { role: "error"; content: string };

export interface AnalyzePayload {
  dataset: string;
  question: string;
  max_turns: number;
  history?: HistoryTurn[];
}

/** One earlier exchange, replayed so follow-up questions have context. */
export interface HistoryTurn {
  question: string;
  answer: string;
  /** Tool-result texts from that turn, so reused numbers stay grounded. */
  tool_results?: string[];
}
