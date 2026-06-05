import { NextResponse } from "next/server";

import { auth } from "../../../../../auth";
import { createBackendAuthHeaders, getBackendUrl } from "../../../../../lib/backend-proxy";

type RouteContext = {
  params: {
    conversationId: string;
  };
};

export async function GET(_: Request, { params }: RouteContext) {
  const session = await auth();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const response = await fetch(
    getBackendUrl(`/conversations/${encodeURIComponent(params.conversationId)}/messages`),
    {
      method: "GET",
      headers: createBackendAuthHeaders(userId),
      cache: "no-store"
    }
  );

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}
