// Vercel serverless entrypoint (ESM). Bypasses @vercel/node source-graph
// transpilation by loading the pre-built, self-contained esbuild bundle
// dist/index.cjs (which has express+drizzle+zod+paths already resolved).
// Dynamic import() is ESM-correct for a .cjs target; includeFiles copies
// the bundle into the function. Wrapped in try/catch so any init error
// surfaces as diagnosable JSON instead of FUNCTION_INVOCATION_FAILED.

let appPromise;

function pickHandler(mod) {
  const app =
    mod.default?.default ??
    mod.default?.app ??
    mod.default ??
    mod.app ??
    mod;

  if (typeof app !== "function") {
    throw new Error(
      `dist/index.cjs did not export a callable Express app. module keys=${Object.keys(mod).join(", ")}`
    );
  }

  return app;
}

async function loadApp() {
  if (!appPromise) {
    appPromise = import("../dist/index.cjs").then(pickHandler);
  }
  return appPromise;
}

export default async function handler(req, res) {
  try {
    const app = await loadApp();
    return app(req, res);
  } catch (err) {
    console.error("EVA API initialization failed", err);

    res.statusCode = 500;
    res.setHeader("Content-Type", "application/json");
    res.end(
      JSON.stringify({
        error: "API initialization failed",
        name: err?.name,
        message: err?.message,
        stack: err?.stack,
      }),
    );
  }
}
