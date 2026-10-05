import { NextRequest } from "next/server";
import { forwardToBackend } from "../../../lib/backend-proxy";

export async function POST(request: NextRequest) {
  return forwardToBackend({
    path: "/uploads",
    method: "POST",
    headers: { "Content-Type": "application/json" },
    prepareBody: async () => JSON.stringify(await request.json())
  });
}
