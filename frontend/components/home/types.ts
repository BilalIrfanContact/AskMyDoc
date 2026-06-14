import type { PersistedDocument } from "../../lib/api";

export type Message = {
  role: "user" | "assistant";
  content: string;
};

export type ViewState = "upload" | "indexing" | "chat";
export type TransitionMode = "indexing" | "loading";

export type DocumentMeta = {
  fileName: string;
  fileSize?: string;
  chunkCount?: number;
  storedCount?: number;
  uploadedAt?: string | null;
};

export type UploadMeta = {
  fileName: string;
  fileSize: string;
  chunkCount: number;
  storedCount: number;
};

export type UploadBootstrapResult =
  | { status: "ready" }
  | { status: "cancelled" }
  | { status: "document-ready"; message: string };

export type WorkspaceState = {
  documentId: string | null;
  conversationId: string | null;
  documentMeta: DocumentMeta | null;
  documents: PersistedDocument[];
  filteredDocuments: PersistedDocument[];
  messages: Message[];
  error: string | null;
  resetSignal: number;
  view: ViewState;
  transitionMode: TransitionMode;
  loadingDocuments: boolean;
  busyDocumentId: string | null;
  isSidebarOpen: boolean;
  isSearchOpen: boolean;
  isSearchClosing: boolean;
  searchQuery: string;
  documentToDelete: PersistedDocument | null;
  isDeletingDocument: boolean;
  deleteError: string | null;
  isAssistantTyping: boolean;
};
