import { forwardToBackend } from "../../../../../lib/backend-proxy";

type RouteContext = {
  params: Promise<{
    conversationId: string;
  }>;
};

export async function GET(_: Request, { params }: RouteContext) {
  const { conversationId } = await params;
  return forwardToBackend({
    path: `/conversations/${encodeURIComponent(conversationId)}/messages`,
    method: "GET",
    cache: "no-store"
  });
}
