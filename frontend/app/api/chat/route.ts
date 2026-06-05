import { NextResponse } from "next/server";

import { auth } from "../../../auth";
import { createBackendAuthHeaders, getBackendUrl } from "../../../lib/backend-proxy";

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

  const response = await fetch(getBackendUrl("/chat"), {
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
