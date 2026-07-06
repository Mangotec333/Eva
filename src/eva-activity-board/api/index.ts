// Vercel serverless entrypoint for all /api/* routes.
//
// Vercel's @vercel/node builder compiles this file from source, tracing all
// imports (server/, shared/, node_modules) automatically — no reliance on a
// pre-built dist/ bundle at runtime. An Express app IS a (req, res) handler,
// so re-exporting the app is a valid serverless handler. server/index.ts binds
// no port and serves no static assets, so it is safe in the serverless runtime.
import app from "../server/index";

export default app;
