/**
 * Bundles smoke/entry.tsx for Node (CJS) with esbuild, applying the same
 * "@" alias as vite.config.ts, then you run: node smoke/out.cjs
 */
import * as esbuild from "esbuild";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const srcDir = path.resolve(here, "..", "src");

await esbuild.build({
  entryPoints: [path.join(here, "entry.tsx")],
  bundle: true,
  platform: "node",
  format: "cjs",
  outfile: path.join(here, "out.cjs"),
  jsx: "automatic",
  logLevel: "warning",
  // client.ts reads import.meta.env (Vite-only); stub it for Node
  define: { "import.meta.env": '{"VITE_API_BASE":""}' },
  plugins: [
    {
      name: "at-alias",
      setup(build) {
        build.onResolve({ filter: /^@\// }, (args) => {
          const base = path.join(srcDir, args.path.slice(2));
          for (const candidate of [base, `${base}.ts`, `${base}.tsx`, path.join(base, "index.ts"), path.join(base, "index.tsx")]) {
            if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
              return { path: candidate };
            }
          }
          return { path: base };
        });
      },
    },
  ],
});

console.log("bundled smoke/out.cjs");
