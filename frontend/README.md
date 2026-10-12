# Frontend — AI Data Analyst

A creative, **shadcn-style** React UI that visualises the LangGraph agent loop
**live** while it runs: you watch the `agent → tools → validate → answer` graph
light up, tool calls stream in as timeline cards, and the grounding verdict
lands as a shield badge before the answer is shown.

![stack](https://img.shields.io/badge/React_19-Vite_6-blue) ![style](https://img.shields.io/badge/shadcn/ui-style-black) ![css](https://img.shields.io/badge/Tailwind-v4-38bdf8)

## Stack

| Layer     | Choice                                                        |
| --------- | ------------------------------------------------------------- |
| Build     | Vite 6 + TypeScript (strict)                                  |
| UI        | React 19                                                      |
| Styling   | Tailwind CSS v4 (`@theme` tokens) + shadcn/ui-style components |
| Icons     | lucide-react                                                  |
| Markdown  | marked + DOMPurify (sanitised rendering)                      |
| Live data | NDJSON streaming from `POST /api/analyze/stream`              |

The shadcn components (`button`, `card`, `badge`, `input`, `textarea`,
`skeleton`) live in `src/components/ui/` — copy-in, themeable, zero
lock-in — exactly how shadcn is meant to be used.

## Run it

```bash
# 1. start the backend (from the project root; backend lives in .venv/)
.venv\Scripts\python.exe -m uvicorn app.api.main:app --port 8000 --app-dir .venv

# 2. start the frontend (from frontend/)
npm install
npm run dev          # → http://localhost:5173 (proxies /api → :8000)
```

Production build:

```bash
npm run build        # typechecks + bundles to dist/
npm run preview
```

Point a production build at a remote API with `VITE_API_BASE=https://host`.

## What the screens do

The UI is a three-stage flow (`intake → running → result`):

- **Stage 1 — Intake** (first page, a chat)
  - Pick an existing CSV from `data/` or upload a new one, right in the
    composer.
  - Type a question (Enter to send) or click an example prompt to fill the
    composer. Submitting moves to the live trace.
- **Stage 2 — Live agent trace** (animated while the run streams)
  - **TraceGraph** — four nodes (`agent · tools · validate · answer`) with a
    pulse/ring animation on the active node, ✓ on visited nodes, run counters
    (×N) and animated flow lines between nodes.
  - Indeterminate progress bar, bouncing status dots, and the agent's *plan*
    text streaming in line by line.
  - **Tool timeline** — each executed tool appears as a staggered-entrance
    card (muted categorical icon per tool, mono args, status badge only — no
    raw result payloads or inline chart previews; the user asked for answers,
    not intermediate dumps); the newest card pulses while it runs.
  - **Validation shield** — `all N numbers grounded` (green), the unsupported
    list (red), or a retry notice when the validator bounced the answer back.
  - **Stop run** aborts the fetch (AbortController) and returns to the result
    screen with the partial trace preserved.
- **Stage 3 — Result** (just the answers)
  - Full markdown answer in an Analyst card with the grounding verdict badge.
    Agent reasoning, the tool audit, and raw JSON are intentionally not shown —
    only the answer itself, so the page stays lean (and follow-up context
    replays a truncated answer, keeping LLM token use low).
  - **Charts gallery** — every `create_chart` PNG (union of `chart_paths` and
    step results) displayed as large cards in a 2-column grid; click to open
    the full-size chart in a new tab.
  - Follow-up composer at the bottom (Enter to send) runs the next question
    against the same dataset, **replaying the conversation** (`history` of
    `{question, answer, tool_results}`) so the agent remembers earlier turns —
    a "follow-up context · N exchanges" badge shows memory is active;
    **New chat** clears the conversation and returns to the intake screen.

**Colors** — professional slate neutrals with a single blue-600 accent
(light mode default); dark mode uses the same layout in slate-950 with a
blue-500 accent. No gradients or glow effects.

## Streaming protocol

`POST /api/analyze/stream` returns **newline-delimited JSON** (one event per
line). Event types:

```jsonc
{"type": "node",       "node": "agent"}          // graph node entered
{"type": "plan",       "text": "Profiling first."}  // assistant reasoning
{"type": "step",       "step": {"tool": "execute_sql", "status": "ok", ...}}
{"type": "validation", "validation": {"passed": true, "checked": 4, ...}}
{"type": "retry",      "unsupported": ["42"]}
{"type": "done",       "result": { /* full AnalysisResult */ }}
```

If the agent crashes mid-run (provider outage, rate limit), the `error` event
is **not** emitted — instead the run ends with a `done` event whose answer is
an evidence digest of the tool results gathered so far, so the UI always has
an answer to show. `{"type": "error", ...}` is reserved for catastrophic
failures inside the API layer itself.

The client (`src/api/client.ts`) decodes the response body with
`TextDecoder` and yields parsed events — no EventSource needed, works with
plain `fetch` + AbortSignal.

## Project structure

```
frontend/
├── index.html                 # Inter + JetBrains Mono, light by default
├── vite.config.ts             # @ alias, /api dev proxy
├── tsconfig.json
└── src/
    ├── main.tsx
    ├── App.tsx                # stage machine: intake → running → result
    ├── index.css              # shadcn theme tokens (slate + blue) + motion
    ├── types.ts               # mirrors the backend Pydantic schemas
    ├── api/client.ts          # fetch helpers + NDJSON stream reader
    ├── lib/
    │   ├── utils.ts           # cn() — clsx + tailwind-merge
    │   └── tools.ts           # tool → icon/tone/args summary mapping
    └── components/
        ├── ui/                # shadcn-style primitives
        ├── Header.tsx         # health badge + theme toggle
        ├── IntakeScreen.tsx   # stage 1: chat composer + dataset upload
        ├── RunningScreen.tsx  # stage 2: animated live agent trace
        ├── ResultScreen.tsx   # stage 3: answer + charts + audit + follow-up
        ├── TraceGraph.tsx     # live LangGraph node visualiser
        ├── StepCard.tsx       # timeline card per tool call
        ├── ValidationBadge.tsx# grounding verdict shield
        └── Markdown.tsx       # sanitised answer renderer
```
