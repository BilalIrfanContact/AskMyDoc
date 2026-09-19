import { forwardToBackend } from "../../../../../lib/backend-proxy";

type RouteContext = {
  params: {
    documentId: string;
  };
};

export async function GET(_: Request, { params }: RouteContext) {
  return forwardToBackend({
    path: `/documents/${encodeURIComponent(params.documentId)}/suggestions`,
    method: "GET",
    cache: "no-store"
  });
}
