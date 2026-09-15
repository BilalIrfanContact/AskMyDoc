import { forwardToBackend } from "../../../lib/backend-proxy";

export async function GET() {
  return forwardToBackend({
    path: "/documents",
    method: "GET",
    cache: "no-store"
  });
}
