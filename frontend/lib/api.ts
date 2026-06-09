const API_BASE = "/api";

async function getErrorMessage(res: Response, fallback: string) {
  const error = await res.json().catch(() => ({ detail: fallback }));
  if (typeof error?.detail === "string") {
    return error.detail;
  }

  if (typeof error?.detail?.message === "string") {
    return error.detail.message;
  }

  return fallback;
}

type UploadLifecycleStatus = "ready" | "failed" | "rejected";
type UploadFailureStage = "validation" | "indexing" | "storage" | "metadata";
type UploadCleanupStatus = "not-needed" | "completed" | "failed";
type UploadReasonCode =
  | "invalid_file_type"
  | "no_extractable_text"
  | "no_usable_chunks"
  | "indexing_failed"
  | "no_chunks_stored"
  | "storage_upload_failed"
  | "metadata_persist_failed";
type DeleteLifecycleStatus = "deleted" | "failed";
type DeleteFailureStage = "conversations" | "indexing" | "storage" | "metadata";
type DeleteCleanupStatus = "not-started" | "partial" | "completed";
type DeleteReasonCode =
  | "conversation_lookup_failed"
  | "storage_delete_failed"
  | "metadata_delete_failed"
  | "conversation_cleanup_failed"
  | "indexing_cleanup_failed";

export class UploadFlowError extends Error {
  lifecycleStatus: UploadLifecycleStatus;
  failureStage: UploadFailureStage | null;
  reasonCode: UploadReasonCode | null;
  cleanupStatus: UploadCleanupStatus | null;

  constructor(
    message: string,
    options?: {
      lifecycleStatus?: UploadLifecycleStatus;
      failureStage?: UploadFailureStage | null;
      reasonCode?: UploadReasonCode | null;
      cleanupStatus?: UploadCleanupStatus | null;
    }
  ) {
    super(message);
    this.name = "UploadFlowError";
    this.lifecycleStatus = options?.lifecycleStatus ?? "failed";
    this.failureStage = options?.failureStage ?? null;
    this.reasonCode = options?.reasonCode ?? null;
    this.cleanupStatus = options?.cleanupStatus ?? null;
  }
}

export class DeleteFlowError extends Error {
  lifecycleStatus: DeleteLifecycleStatus;
  failureStage: DeleteFailureStage | null;
  reasonCode: DeleteReasonCode | null;
  cleanupStatus: DeleteCleanupStatus | null;

  constructor(
    message: string,
    options?: {
      lifecycleStatus?: DeleteLifecycleStatus;
      failureStage?: DeleteFailureStage | null;
      reasonCode?: DeleteReasonCode | null;
      cleanupStatus?: DeleteCleanupStatus | null;
    }
  ) {
    super(message);
    this.name = "DeleteFlowError";
    this.lifecycleStatus = options?.lifecycleStatus ?? "failed";
    this.failureStage = options?.failureStage ?? null;
    this.reasonCode = options?.reasonCode ?? null;
    this.cleanupStatus = options?.cleanupStatus ?? null;
  }
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
    const error = await res.json().catch(() => ({ detail: { message: "Upload failed." } }));
    const detail = error?.detail;

    if (detail && typeof detail === "object") {
      throw new UploadFlowError(
        typeof detail.message === "string" ? detail.message : "Upload failed.",
        {
          lifecycleStatus:
            detail.lifecycle_status === "rejected" || detail.lifecycle_status === "failed"
              ? detail.lifecycle_status
              : "failed",
          failureStage:
            detail.failure_stage === "validation" ||
            detail.failure_stage === "indexing" ||
            detail.failure_stage === "storage" ||
            detail.failure_stage === "metadata"
              ? detail.failure_stage
              : null,
          reasonCode:
            detail.reason_code === "invalid_file_type" ||
            detail.reason_code === "no_extractable_text" ||
            detail.reason_code === "no_usable_chunks" ||
            detail.reason_code === "indexing_failed" ||
            detail.reason_code === "no_chunks_stored" ||
            detail.reason_code === "storage_upload_failed" ||
            detail.reason_code === "metadata_persist_failed"
              ? detail.reason_code
              : null,
          cleanupStatus:
            detail.cleanup_status === "not-needed" ||
            detail.cleanup_status === "completed" ||
            detail.cleanup_status === "failed"
              ? detail.cleanup_status
              : null
        }
      );
    }

    throw new UploadFlowError(typeof detail === "string" ? detail : "Upload failed.");
  }

  return res.json() as Promise<{
    status: string;
    lifecycle_status: "ready";
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
    const error = await res.json().catch(() => ({ detail: { message: "Failed to delete document." } }));
    const detail = error?.detail;

    if (detail && typeof detail === "object") {
      throw new DeleteFlowError(
        typeof detail.message === "string" ? detail.message : "Failed to delete document.",
        {
          lifecycleStatus: detail.lifecycle_status === "failed" ? "failed" : "failed",
          failureStage:
            detail.failure_stage === "conversations" ||
            detail.failure_stage === "indexing" ||
            detail.failure_stage === "storage" ||
            detail.failure_stage === "metadata"
              ? detail.failure_stage
              : null,
          reasonCode:
            detail.reason_code === "conversation_lookup_failed" ||
            detail.reason_code === "storage_delete_failed" ||
            detail.reason_code === "metadata_delete_failed" ||
            detail.reason_code === "conversation_cleanup_failed" ||
            detail.reason_code === "indexing_cleanup_failed"
              ? detail.reason_code
              : null,
          cleanupStatus:
            detail.cleanup_status === "not-started" ||
            detail.cleanup_status === "partial" ||
            detail.cleanup_status === "completed"
              ? detail.cleanup_status
              : null
        }
      );
    }

    throw new DeleteFlowError(typeof detail === "string" ? detail : "Failed to delete document.");
  }

  return res.json() as Promise<{
    deleted: boolean;
    lifecycle_status: "deleted";
    cleanup_status: "completed";
  }>;
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
