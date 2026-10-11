import assert from "node:assert/strict";
import test from "node:test";
import { NextRequest, type NextFetchEvent } from "next/server";

import proxy from "../proxy";

// Exercise the actual exported entry point with Auth.js's request-specific config.
// No session cookie is supplied, so these checks do not contact Supabase.
test("proxy exports a function and lets signed-out visitors open login", async (context) => {
  const previousSecret = process.env.NEXTAUTH_SECRET;
  process.env.NEXTAUTH_SECRET = "middleware-test-secret";
  context.after(() => {
    if (previousSecret === undefined) delete process.env.NEXTAUTH_SECRET;
    else process.env.NEXTAUTH_SECRET = previousSecret;
  });
  assert.equal(typeof proxy, "function");
  const response = await proxy(new NextRequest("http://localhost:3000/login"), {} as NextFetchEvent);
  assert.equal(response?.status, 200);
  assert.equal(response?.headers.get("x-middleware-next"), "1");
});

test("proxy still redirects a signed-out visitor away from the workspace", async (context) => {
  const previousSecret = process.env.NEXTAUTH_SECRET;
  process.env.NEXTAUTH_SECRET = "middleware-test-secret";
  context.after(() => {
    if (previousSecret === undefined) delete process.env.NEXTAUTH_SECRET;
    else process.env.NEXTAUTH_SECRET = previousSecret;
  });
  const response = await proxy(new NextRequest("http://localhost:3000/"), {} as NextFetchEvent);
  assert.equal(response?.status, 307);
  assert.equal(response?.headers.get("location"), "http://localhost:3000/login");
});
