/**
 * SSR smoke test: renders <App /> with react-dom/server and asserts that the
 * first paint contains the key UI landmarks. Catches runtime render errors
 * (bad hook usage, undefined access on initial state) that tsc cannot see.
 *
 * Run via: node smoke/build.mjs && node smoke/out.cjs
 */
import { renderToString } from "react-dom/server";
import App from "../src/App";

const html = renderToString(<App />);

const markers = [
  "AI Data Analyst", // header
  "Ask your data anything", // intake hero
  "Dataset", // dataset picker inside the intake composer
  "Upload CSV", // upload button
  "Max turns", // turn-budget selector
  "Ask the agent", // send button
  "Try asking", // example prompts
];

const missing = markers.filter((m) => !html.includes(m));
if (missing.length > 0) {
  console.error("SSR smoke FAILED — missing markers:", missing);
  process.exit(1);
}
if (html.length < 2000) {
  console.error(`SSR smoke FAILED — suspiciously small render (${html.length} B)`);
  process.exit(1);
}
console.log(`SSR smoke OK — ${html.length} bytes, ${markers.length}/${markers.length} markers present`);
