import type { AnalyzePayload, DatasetInfo, HealthInfo, StreamEvent } from "@/types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthInfo> {
  return fetch(`${BASE}/api/health`).then((r) => json<HealthInfo>(r));
}

export function fetchDatasets(): Promise<DatasetInfo[]> {
  return fetch(`${BASE}/api/datasets`).then((r) => json<DatasetInfo[]>(r));
}

export async function uploadDataset(file: File): Promise<{ name: string }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/datasets`, { method: "POST", body: form });
  return json<{ name: string }>(res);
}

export async function fetchCharts(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/charts`);
  const body = await json<{ charts: string[] }>(res);
  return body.charts;
}

export function chartUrl(name: string): string {
  return `${BASE}/api/charts/${encodeURIComponent(name)}`;
}

/**
 * POST /api/analyze/stream and yield NDJSON events as they arrive.
 * Supports AbortSignal for a Stop button.
 */
export async function* streamAnalyze(
  payload: AnalyzePayload,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/api/analyze/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    signal,
  });
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* keep statusText */
    }
    throw new Error(`${res.status}: ${detail}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let newline: number;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) yield JSON.parse(line) as StreamEvent;
    }
  }
  const tail = buffer.trim();
  if (tail) yield JSON.parse(tail) as StreamEvent;
}
