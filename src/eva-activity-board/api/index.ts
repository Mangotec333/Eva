// Vercel serverless entrypoint for all /api/* routes.
//
// COLD-START SAFETY: this module must NEVER throw during evaluation, or Vercel
// returns FUNCTION_INVOCATION_FAILED for every request with no logs. To guarantee
// that, we do NOT statically import the Express app graph here. Instead we lazily
// `import()` it on the first request, inside a try/catch. Any error in the import
// graph (server/, shared/, node_modules) is therefore caught and surfaced as a
// logged JSON 500 rather than crashing module initialization. The resolved app is
// cached so subsequent requests reuse it. An Express app is itself a (req, res)
// handler, so we simply delegate to it.
import type { IncomingMessage, ServerResponse } from "node:http";

type NodeHandler = (req: IncomingMessage, res: ServerResponse) => unknown;

let cachedApp: NodeHandler | null = null;

async function getApp(): Promise<NodeHandler> {
  if (cachedApp) return cachedApp;
  const mod = (await import("../server/index")) as {
    default?: NodeHandler;
    app?: NodeHandler;
  };
  const app = mod.default ?? mod.app;
  if (typeof app !== "function") {
    throw new Error("server/index did not export a callable Express app");
  }
  cachedApp = app;
  return cachedApp;
}

export default async function handler(req: IncomingMessage, res: ServerResponse) {
  try {
    const app = await getApp();
    return app(req, res);
  } catch (err) {
    // Reaching here means the app graph failed to initialize. Log the real cause
    // (visible in `vercel logs`) and respond gracefully instead of crashing.
    console.error("EVA: /api initialization failed —", err);
    if (!res.headersSent) {
      res.statusCode = 500;
      res.setHeader("Content-Type", "application/json");
      res.end(
        JSON.stringify({
          error: "API initialization failed",
          detail: err instanceof Error ? err.message : String(err),
        }),
      );
    }
  }
}
