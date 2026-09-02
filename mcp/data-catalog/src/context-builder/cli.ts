import { mkdir, readdir, stat, writeFile } from "node:fs/promises";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { ContextBuilder } from "./builder.js";
import { ContextIndexEngine } from "./index-engine.js";
import { supportedExtensions } from "./parsers/parser.js";
import { InMemoryContextStore } from "./store.js";

interface CliOptions {
  inputs: string[];
  output: string;
  sourceVersion?: string;
  query?: string;
}

function usage(): string {
  return [
    "Explore Context Builder v0.1",
    "",
    "Usage:",
    "  npm run context:build -- --input <file-or-dir> [--input <path>] --output <graph.json>",
    "",
    "Options:",
    "  --source-version <version>  Attach a source release/version to evidence",
    "  --query <text>              Run a search smoke check after building",
  ].join("\n");
}

function parseArgs(args: string[]): CliOptions {
  const options: CliOptions = { inputs: [], output: "workspace/contexts/context-graph.json" };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index]!;
    const value = args[index + 1];
    if (arg === "--input" && value) { options.inputs.push(value); index += 1; continue; }
    if (arg === "--output" && value) { options.output = value; index += 1; continue; }
    if (arg === "--source-version" && value) { options.sourceVersion = value; index += 1; continue; }
    if (arg === "--query" && value) { options.query = value; index += 1; continue; }
    if (arg === "--help" || arg === "-h") { console.log(usage()); process.exit(0); }
    throw new Error(`unknown or incomplete argument: ${arg}`);
  }
  if (!options.inputs.length) throw new Error("at least one --input is required");
  return options;
}

async function collect(path: string): Promise<string[]> {
  const absolute = resolve(path);
  const info = await stat(absolute);
  if (info.isFile()) return supportedExtensions.has(extname(absolute).toLocaleLowerCase()) ? [absolute] : [];
  if (!info.isDirectory()) return [];
  const results: string[] = [];
  for (const entry of await readdir(absolute, { withFileTypes: true })) {
    if (entry.name.startsWith(".")) continue;
    results.push(...(await collect(resolve(absolute, entry.name))));
  }
  return results;
}

export async function run(args = process.argv.slice(2)): Promise<void> {
  const options = parseArgs(args);
  const paths = (await Promise.all(options.inputs.map(collect))).flat().sort();
  if (!paths.length) throw new Error("no supported .xlsx or .docx source documents found");
  const graph = await new ContextBuilder({ sourceVersion: options.sourceVersion }).build(paths);
  const output = resolve(options.output);
  await mkdir(dirname(output), { recursive: true });
  await writeFile(output, `${JSON.stringify(graph, null, 2)}\n`, "utf8");
  const summary: Record<string, unknown> = {
    output,
    indexVersion: graph.indexVersion,
    documents: graph.documents.length,
    entities: graph.entities.length,
    facts: graph.facts.length,
    evidence: graph.evidence.length,
    warnings: graph.warnings.length,
  };
  if (options.query) {
    const index = new ContextIndexEngine(new InMemoryContextStore(graph));
    summary.search = index.search({ query: options.query, limit: 5 });
  }
  console.log(JSON.stringify(summary, null, 2));
}

const isMain = process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1];
if (isMain) run().catch((error) => { console.error(error instanceof Error ? error.message : String(error)); process.exitCode = 1; });
