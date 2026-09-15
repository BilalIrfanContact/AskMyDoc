import { forwardToBackend } from "../../../lib/backend-proxy";

export async function POST(request: Request) {
  return forwardToBackend({
    path: "/upload",
    method: "POST",
    prepareBody: async () => {
      const formData = await request.formData();
      formData.delete("user_id");
      return formData;
    }
  });
}
