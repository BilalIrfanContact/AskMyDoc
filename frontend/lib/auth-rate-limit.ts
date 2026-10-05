import { getSupabaseAdmin } from "./supabase-admin";

export class AuthRateLimitError extends Error {
  constructor(public retryAfter: number) {
    super("Too many attempts. Please try again later.");
  }
}

export async function authRateKey(scope: "login" | "signup", headers?: Headers) {
  // Vercel overwrites this header. Other deployments share a conservative fallback
  // until a trusted proxy is configured; arbitrary client headers never choose the key.
  const forwarded = process.env.VERCEL === "1" ? headers?.get("x-forwarded-for")?.split(",")[0].trim() : undefined;
  const ip = forwarded && forwarded.length <= 64 && /^[0-9a-f:.]+$/i.test(forwarded) ? forwarded.toLowerCase() : "unknown";
  const secret = process.env.AUTH_SECRET || process.env.NEXTAUTH_SECRET;
  if (!secret) throw new Error("Missing auth secret for rate limits.");
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const signature = await crypto.subtle.sign("HMAC", key, encoder.encode(ip));
  return `${scope}:${Array.from(new Uint8Array(signature), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
}

export async function checkAuthRate(scope: "login" | "signup", headers?: Headers, client = getSupabaseAdmin()) {
  const { data, error } = await client.rpc("demo_rate_limit", {
    p_key: await authRateKey(scope, headers), p_limit: scope === "login" ? 5 : 3,
    p_seconds: scope === "login" ? 60 : 3600
  });
  if (error || typeof data !== "number") throw new Error("Sign-in is temporarily unavailable. Please try again later.");
  if (data > 0) throw new AuthRateLimitError(data);
}
