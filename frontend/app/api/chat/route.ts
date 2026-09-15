import { forwardToBackend } from "../../../lib/backend-proxy";

export async function POST(request: Request) {
  return forwardToBackend({
    path: "/chat",
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    prepareBody: async () => {
      const payload = (await request.json()) as Record<string, unknown>;
      if (payload && typeof payload === "object") {
        delete payload.user_id;
      }
      return JSON.stringify(payload);
    }
  });
}
