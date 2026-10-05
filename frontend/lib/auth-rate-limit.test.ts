import assert from "node:assert/strict";
import test from "node:test";
import { createClient } from "@supabase/supabase-js";
import { AuthRateLimitError, authRateKey, checkAuthRate } from "./auth-rate-limit";
import { createAuthConfig } from "./auth-config";
import type { CredentialsConfig } from "next-auth/providers/credentials";

test("client-supplied forwarding headers cannot bypass limits outside Vercel", async () => {
  const oldSecret = process.env.AUTH_SECRET;
  const oldVercel = process.env.VERCEL;
  process.env.AUTH_SECRET = "test-secret";
  delete process.env.VERCEL;
  try {
    assert.equal(await authRateKey("login", new Headers({ "x-forwarded-for": "1.2.3.4" })), await authRateKey("login", new Headers({ "x-forwarded-for": "5.6.7.8" })));
    process.env.VERCEL = "1";
    assert.notEqual(await authRateKey("login", new Headers({ "x-forwarded-for": "1.2.3.4" })), await authRateKey("login", new Headers({ "x-forwarded-for": "5.6.7.8" })));
    assert.ok(!(await authRateKey("login", new Headers({ "x-forwarded-for": "1.2.3.4" }))).includes("1.2.3.4"));
  } finally {
    if (oldSecret === undefined) delete process.env.AUTH_SECRET; else process.env.AUTH_SECRET = oldSecret;
    if (oldVercel === undefined) delete process.env.VERCEL; else process.env.VERCEL = oldVercel;
  }
});

test("rate-limited password login stops before user lookup and password hashing", async () => {
  let lookups = 0;
  const config = createAuthConfig({
    checkAuthRate: async () => { throw new AuthRateLimitError(60); },
    getUserByEmail: async () => { lookups++; return null; },
    getOrCreateGoogleUser: async () => null,
    verifyPassword: async () => { throw new Error("must not run"); }
  });
  const credentials = config.providers[1] as CredentialsConfig & { options: Partial<CredentialsConfig> };
  await assert.rejects(async () => credentials.options.authorize!({ email: "test@example.test", password: "password" }, new Request("https://app.test")), (error: unknown) => {
    assert.equal((error as { code: string }).code, "rate_limited");
    return true;
  });
  assert.equal(lookups, 0);
});


test("auth rate checks use the durable RPC with the agreed limits and fail closed", async () => {
  const previous = process.env.AUTH_SECRET;
  process.env.AUTH_SECRET = "test-secret";
  let result: unknown = 0;
  const requests: Record<string, unknown>[] = [];
  const client = createClient("https://supabase.example.test", "test-key", {
    auth: { persistSession: false, autoRefreshToken: false },
    global: { fetch: async (url, init) => {
      assert.equal(new URL(String(url)).pathname, "/rest/v1/rpc/demo_rate_limit");
      requests.push(JSON.parse(String(init?.body)));
      return new Response(JSON.stringify(result), { headers: { "content-type": "application/json" } });
    } }
  });
  try {
    await checkAuthRate("login", new Headers(), client);
    await checkAuthRate("signup", new Headers(), client);
    assert.equal(requests[0].p_limit, 5);
    assert.equal(requests[0].p_seconds, 60);
    assert.equal(requests[1].p_limit, 3);
    assert.equal(requests[1].p_seconds, 3600);
    result = 45;
    await assert.rejects(checkAuthRate("login", new Headers(), client), (error: unknown) => error instanceof AuthRateLimitError && error.retryAfter === 45);
    result = null;
    await assert.rejects(checkAuthRate("login", new Headers(), client), /temporarily unavailable/);
  } finally {
    if (previous === undefined) delete process.env.AUTH_SECRET; else process.env.AUTH_SECRET = previous;
  }
});
