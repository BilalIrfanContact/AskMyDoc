import { NextResponse } from "next/server";

import { auth } from "../../../auth";
import { createBackendAuthHeaders, getBackendUrl } from "../../../lib/backend-proxy";

export async function GET(request: Request) {
  const session = await auth();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const url = new URL(request.url);
  const documentId = url.searchParams.get("document_id");
  const backendUrl = new URL(getBackendUrl("/conversations"));
  if (documentId) {
    backendUrl.searchParams.set("document_id", documentId);
  }

  const response = await fetch(backendUrl, {
    method: "GET",
    headers: createBackendAuthHeaders(userId),
    cache: "no-store"
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}

export async function POST(request: Request) {
  const session = await auth();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const payload = (await request.json()) as Record<string, unknown>;
  if (payload && typeof payload === "object") {
    delete payload.user_id;
  }

  const response = await fetch(getBackendUrl("/conversations"), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...createBackendAuthHeaders(userId)
    },
    body: JSON.stringify(payload)
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}
