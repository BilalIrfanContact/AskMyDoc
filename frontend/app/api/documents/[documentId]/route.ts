import { forwardToBackend } from "../../../../lib/backend-proxy";

type RouteContext = {
  params: Promise<{
    documentId: string;
  }>;
};

export async function DELETE(_: Request, { params }: RouteContext) {
  const { documentId } = await params;
  return forwardToBackend({
    path: `/documents/${encodeURIComponent(documentId)}`,
    method: "DELETE"
  });
}
