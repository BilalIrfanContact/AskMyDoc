import { createHmac } from "crypto";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const INTERNAL_USER_HEADER = "x-askmydoc-user-id";
const INTERNAL_TIMESTAMP_HEADER = "x-askmydoc-timestamp";
const INTERNAL_SIGNATURE_HEADER = "x-askmydoc-signature";

function getInternalAuthSecret() {
  const secret =
    process.env.INTERNAL_API_SECRET ||
    process.env.NEXTAUTH_SECRET ||
    process.env.AUTH_SECRET;

  if (!secret) {
    throw new Error("Missing INTERNAL_API_SECRET or NEXTAUTH_SECRET for backend identity signing.");
  }

  return secret;
}

export function getBackendUrl(path: string) {
  return `${API_BASE}${path}`;
}

export function createBackendAuthHeaders(userId: string) {
  const timestamp = Math.floor(Date.now() / 1000).toString();
  const signature = createHmac("sha256", getInternalAuthSecret())
    .update(`${userId}:${timestamp}`)
    .digest("hex");

  return {
    [INTERNAL_USER_HEADER]: userId,
    [INTERNAL_TIMESTAMP_HEADER]: timestamp,
    [INTERNAL_SIGNATURE_HEADER]: signature
  };
}
