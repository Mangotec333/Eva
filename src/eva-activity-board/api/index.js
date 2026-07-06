// Vercel serverless entrypoint for all /api/* routes.
//
// vercel.json rewrites `/api/(.*)` to this function, preserving the original
// URL (e.g. `/api/activities`), which matches the Express routes registered in
// server/routes.ts. An Express app IS a (req, res) request handler, so we just
// re-export the built bundle's app. esbuild emits a CJS module with the app on
// `.default` (from `export default app`) and also as the named `.app`, so we
// normalize both shapes here.
const mod = require("../dist/index.cjs");

module.exports = mod.default || mod.app || mod;
