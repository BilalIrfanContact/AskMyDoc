import { forwardToBackend } from "../../../../../lib/backend-proxy";

export const maxDuration = 300;

export async function POST(_request: Request, { params }: { params: Promise<{ uploadId: string }> }) {
  const { uploadId } = await params;
  return forwardToBackend({ path: `/uploads/${encodeURIComponent(uploadId)}/complete`, method: "POST", stream: true });
}
