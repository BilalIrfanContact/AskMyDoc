const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function uploadPdf(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Upload failed." }));
    throw new Error(error.detail || "Upload failed.");
  }

  return res.json() as Promise<{
    status: string;
    document_id: string;
    chunk_count: number;
    stored_count: number;
  }>;
}

export async function askQuestion(documentId: string, question: string) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId, question })
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Chat failed." }));
    throw new Error(error.detail || "Chat failed.");
  }

  return res.json() as Promise<{ answer: string }>;
}
