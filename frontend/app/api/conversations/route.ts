import { forwardToBackend } from "../../../lib/backend-proxy";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const documentId = url.searchParams.get("document_id");
  const query = new URLSearchParams();
  if (documentId) {
    query.set("document_id", documentId);
  }

  return forwardToBackend({
    path: query.toString() ? `/conversations?${query.toString()}` : "/conversations",
    method: "GET",
    cache: "no-store"
  });
}

export async function POST(request: Request) {
  return forwardToBackend({
    path: "/conversations",
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
