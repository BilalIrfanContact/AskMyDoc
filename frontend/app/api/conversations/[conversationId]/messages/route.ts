import { forwardToBackend } from "../../../../../lib/backend-proxy";

type RouteContext = {
  params: {
    conversationId: string;
  };
};

export async function GET(_: Request, { params }: RouteContext) {
  return forwardToBackend({
    path: `/conversations/${encodeURIComponent(params.conversationId)}/messages`,
    method: "GET",
    cache: "no-store"
  });
}
