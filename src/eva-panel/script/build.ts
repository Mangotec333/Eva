import { build as esbuild } from "esbuild";
import { build as viteBuild } from "vite";
import { rm, readFile } from "node:fs/promises";

// server deps to bundle to reduce openat(2) syscalls
// which helps cold start times
const allowlist = [
  "@google/generative-ai",
  "axios",
  "cors",
  "date-fns",
  "drizzle-orm",
  "drizzle-zod",
  "express",
  "express-rate-limit",
  "express-session",
  "jsonwebtoken",
  "memorystore",
  "multer",
  "nanoid",
  "nodemailer",
  "openai",
  "passport",
  "passport-local",
  "stripe",
  "uuid",
  "ws",
  "xlsx",
  "zod",
  "zod-validation-error",
];

async function buildAll() {
  await rm("dist", { recursive: true, force: true });

  console.log("building client...");
  await viteBuild();

  console.log("building server...");
  const pkg = JSON.parse(await readFile("package.json", "utf-8"));
  const allDeps = [
    ...Object.keys(pkg.dependencies || {}),
    ...Object.keys(pkg.devDependencies || {}),
  ];
  const externals = allDeps.filter((dep) => !allowlist.includes(dep));

  const common = {
    platform: "node",
    bundle: true,
    format: "cjs",
    define: {
      "process.env.NODE_ENV": '"production"',
    },
    minify: true,
    external: externals,
    logLevel: "info",
  } as const;

  // dist/index.cjs — exports the Express app (no port bind); consumed by the
  // Vercel serverless entrypoint at api/index.js.
  await esbuild({
    ...common,
    entryPoints: ["server/index.ts"],
    outfile: "dist/index.cjs",
  });

  // dist/start.cjs — standalone launcher (serves client + binds PORT); used by
  // `npm start` for local/self-hosted runs. Never invoked on Vercel.
  await esbuild({
    ...common,
    entryPoints: ["server/start.ts"],
    outfile: "dist/start.cjs",
  });
}

buildAll().catch((err) => {
  console.error(err);
  process.exit(1);
});
