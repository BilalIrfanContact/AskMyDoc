import { forwardToBackend } from "../../../../../lib/backend-proxy";

export const maxDuration = 300;

export async function POST(_request: Request, { params }: { params: { uploadId: string } }) {
  return forwardToBackend({ path: `/uploads/${encodeURIComponent(params.uploadId)}/complete`, method: "POST" });
}
