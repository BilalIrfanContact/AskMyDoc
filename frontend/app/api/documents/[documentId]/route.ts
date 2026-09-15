import { forwardToBackend } from "../../../../lib/backend-proxy";

type RouteContext = {
  params: {
    documentId: string;
  };
};

export async function DELETE(_: Request, { params }: RouteContext) {
  return forwardToBackend({
    path: `/documents/${encodeURIComponent(params.documentId)}`,
    method: "DELETE"
  });
}
