// Vercel serverless entrypoint for all /api/* routes.
//
// The Express app graph is imported STATICALLY so that @vercel/node traces every
// source file (server/*, shared/*) into the function bundle. Dynamic import() is
// NOT used here: @vercel/node only bundles statically-imported files, so a lazy
// import() of "../server/index" resolves at build but throws "Cannot find module"
// at runtime. An Express app is itself a (req, res) handler, so we delegate to it.
import type { IncomingMessage, ServerResponse } from "node:http";
import app from "../server/index";

export default function handler(req: IncomingMessage, res: ServerResponse) {
  return (app as unknown as (req: IncomingMessage, res: ServerResponse) => unknown)(req, res);
}
