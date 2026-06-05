const API_BASE = "/api";

async function getErrorMessage(res: Response, fallback: string) {
  const error = await res.json().catch(() => ({ detail: fallback }));
  return error.detail || fallback;
}

export type PersistedDocument = {
  id: string;
  user_id: string;
  filename: string;
  storage_url: string;
  uploaded_at?: string | null;
};

export type PersistedConversation = {
  id: string;
  user_id: string;
  document_id: string;
  created_at?: string | null;
};

export type PersistedMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

export async function uploadPdf(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE}/upload`, {
    method: "POST",
    body: formData
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Upload failed."));
  }

  return res.json() as Promise<{
    status: string;
    document_id: string;
    chunk_count: number;
    stored_count: number;
  }>;
}

export async function createConversation(documentId: string) {
  const res = await fetch(`${API_BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: documentId })
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to create conversation."));
  }

  return res.json() as Promise<{ conversation_id: string }>;
}

export async function getUserDocuments() {
  const res = await fetch(`${API_BASE}/documents`, {
    method: "GET",
    cache: "no-store"
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to load documents."));
  }

  const data = (await res.json()) as { documents: PersistedDocument[] };
  return data.documents;
}

export async function deleteUserDocument(documentId: string) {
  const res = await fetch(`${API_BASE}/documents/${encodeURIComponent(documentId)}`, {
    method: "DELETE"
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to delete document."));
  }

  return res.json() as Promise<{ deleted: boolean }>;
}

export async function getUserConversations(documentId?: string) {
  const query = new URLSearchParams();
  if (documentId) {
    query.set("document_id", documentId);
  }

  const res = await fetch(`${API_BASE}/conversations?${query.toString()}`, {
    method: "GET",
    cache: "no-store"
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to load conversations."));
  }

  const data = (await res.json()) as { conversations: PersistedConversation[] };
  return data.conversations;
}

export async function getConversationMessages(conversationId: string) {
  const res = await fetch(`${API_BASE}/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "GET",
    cache: "no-store"
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Failed to load messages."));
  }

  const data = (await res.json()) as { messages: PersistedMessage[] };
  return data.messages;
}

export async function askQuestion(input: {
  documentId: string;
  conversationId: string;
  message: string;
}) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      document_id: input.documentId,
      conversation_id: input.conversationId,
      message: input.message
    })
  });

  if (!res.ok) {
    throw new Error(await getErrorMessage(res, "Chat failed."));
  }

  return res.json() as Promise<{ answer: string }>;
}
