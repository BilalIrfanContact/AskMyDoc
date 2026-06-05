import { NextResponse } from "next/server";

import { auth } from "../../../../auth";
import { createBackendAuthHeaders, getBackendUrl } from "../../../../lib/backend-proxy";

type RouteContext = {
  params: {
    documentId: string;
  };
};

export async function DELETE(_: Request, { params }: RouteContext) {
  const session = await auth();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const response = await fetch(getBackendUrl(`/documents/${encodeURIComponent(params.documentId)}`), {
    method: "DELETE",
    headers: createBackendAuthHeaders(userId)
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}
