import { createHmac } from "crypto";

import { NextResponse } from "next/server";

import { auth } from "../auth";

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

export type BackendForwardOptions = {
  path: string;
  method: string;
  headers?: HeadersInit;
  body?: BodyInit | null;
  prepareBody?: () => BodyInit | Promise<BodyInit>;
  cache?: RequestCache;
};

type BackendSession = {
  user?: {
    id?: string | null;
  } | null;
} | null;

export type BackendProxyDependencies = {
  getSession?: () => Promise<BackendSession>;
  fetch?: typeof fetch;
  createAuthHeaders?: (userId: string) => Record<string, string>;
};

export async function forwardToBackend(
  options: BackendForwardOptions,
  dependencies: BackendProxyDependencies = {}
) {
  const session = await (dependencies.getSession ?? auth)();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const headers = new Headers(options.headers);
  const authHeaders = (dependencies.createAuthHeaders ?? createBackendAuthHeaders)(userId);
  for (const [name, value] of Object.entries(authHeaders)) {
    headers.set(name, value);
  }

  const requestBody = options.prepareBody ? await options.prepareBody() : options.body;
  const response = await (dependencies.fetch ?? fetch)(getBackendUrl(options.path), {
    method: options.method,
    headers,
    ...(requestBody !== undefined ? { body: requestBody } : {}),
    ...(options.cache !== undefined ? { cache: options.cache } : {})
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}
