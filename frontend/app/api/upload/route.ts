import { NextResponse } from "next/server";

import { auth } from "../../../auth";
import { createBackendAuthHeaders, getBackendUrl } from "../../../lib/backend-proxy";

export async function POST(request: Request) {
  const session = await auth();
  const userId = session?.user?.id;

  if (!userId) {
    return NextResponse.json({ detail: "Authentication required." }, { status: 401 });
  }

  const formData = await request.formData();
  formData.delete("user_id");

  const response = await fetch(getBackendUrl("/upload"), {
    method: "POST",
    headers: createBackendAuthHeaders(userId),
    body: formData
  });

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "application/json"
    }
  });
}
