import type { PersistedDocument } from "../../lib/api";
import type { DocumentMeta, Message, TransitionMode, ViewState, WorkspaceState } from "./types";

export type WorkspaceAction =
  | { type: "documents/load-start" }
  | { type: "documents/load-success"; documents: PersistedDocument[] }
  | { type: "documents/load-failure"; error: string }
  | { type: "search/open" }
  | { type: "search/set-query"; query: string }
  | { type: "search/start-close" }
  | { type: "search/finish-close" }
  | { type: "sidebar/toggle" }
  | { type: "workflow/upload-start"; documentId: string; documentMeta: DocumentMeta }
  | { type: "workflow/select-start"; documentId: string; documentMeta: DocumentMeta }
  | { type: "workflow/chat-ready"; conversationId: string; messages: Message[] }
  | { type: "workflow/bootstrap-failure"; error: string }
  | { type: "workflow/failure"; error: string }
  | { type: "workflow/clear" }
  | { type: "delete/open"; document: PersistedDocument }
  | { type: "delete/start" }
  | { type: "delete/success"; documentId: string }
  | { type: "delete/failure"; error: string }
  | { type: "delete/close" }
  | { type: "chat/send-start"; question: string }
  | { type: "chat/send-success"; answer: string }
  | { type: "chat/send-failure"; error: string };

const initialState: Omit<WorkspaceState, "filteredDocuments"> = {
  documentId: null,
  conversationId: null,
  documentMeta: null,
  documents: [],
  messages: [],
  error: null,
  resetSignal: 0,
  view: "upload",
  transitionMode: "indexing",
  loadingDocuments: true,
  busyDocumentId: null,
  isSidebarOpen: true,
  isSearchOpen: false,
  isSearchClosing: false,
  searchQuery: "",
  documentToDelete: null,
  isDeletingDocument: false,
  deleteError: null,
  isAssistantTyping: false
};

export function createInitialWorkspaceState(): Omit<WorkspaceState, "filteredDocuments"> {
  return initialState;
}

export function workspaceReducer(
  state: Omit<WorkspaceState, "filteredDocuments">,
  action: WorkspaceAction
): Omit<WorkspaceState, "filteredDocuments"> {
  switch (action.type) {
    case "documents/load-start":
      return {
        ...state,
        loadingDocuments: true
      };
    case "documents/load-success":
      return {
        ...state,
        documents: action.documents,
        loadingDocuments: false
      };
    case "documents/load-failure":
      return {
        ...state,
        error: action.error,
        loadingDocuments: false
      };
    case "search/open":
      return {
        ...state,
        searchQuery: "",
        isSearchOpen: true,
        isSearchClosing: false
      };
    case "search/set-query":
      return {
        ...state,
        searchQuery: action.query
      };
    case "search/start-close":
      return {
        ...state,
        isSearchClosing: true
      };
    case "search/finish-close":
      return {
        ...state,
        isSearchOpen: false,
        isSearchClosing: false
      };
    case "sidebar/toggle":
      return {
        ...state,
        isSidebarOpen: !state.isSidebarOpen
      };
    case "workflow/upload-start":
      return {
        ...state,
        transitionMode: "indexing",
        view: "indexing",
        busyDocumentId: action.documentId,
        documentId: action.documentId,
        conversationId: null,
        documentMeta: action.documentMeta,
        messages: [],
        error: null
      };
    case "workflow/select-start":
      return {
        ...state,
        transitionMode: "loading",
        view: "indexing",
        busyDocumentId: action.documentId,
        documentId: action.documentId,
        conversationId: null,
        documentMeta: action.documentMeta,
        messages: [],
        error: null
      };
    case "workflow/chat-ready":
      return {
        ...state,
        conversationId: action.conversationId,
        messages: action.messages,
        view: "chat",
        busyDocumentId: null
      };
    case "workflow/bootstrap-failure":
      return {
        ...state,
        error: action.error,
        conversationId: null,
        view: "upload",
        busyDocumentId: null
      };
    case "workflow/failure":
      return {
        ...state,
        error: action.error,
        view: "upload",
        busyDocumentId: null
      };
    case "workflow/clear":
      return {
        ...state,
        documentId: null,
        conversationId: null,
        documentMeta: null,
        messages: [],
        error: null,
        resetSignal: state.resetSignal + 1,
        view: "upload",
        isAssistantTyping: false
      };
    case "delete/open":
      return {
        ...state,
        documentToDelete: action.document,
        deleteError: null
      };
    case "delete/start":
      return {
        ...state,
        isDeletingDocument: true,
        error: null,
        deleteError: null
      };
    case "delete/success":
      return {
        ...state,
        documents: state.documents.filter((document) => document.id !== action.documentId),
        documentToDelete: null,
        isDeletingDocument: false,
        deleteError: null,
        isSearchOpen: false,
        isSearchClosing: false
      };
    case "delete/failure":
      return {
        ...state,
        deleteError: action.error,
        isDeletingDocument: false
      };
    case "delete/close":
      if (state.isDeletingDocument) {
        return state;
      }

      return {
        ...state,
        documentToDelete: null,
        deleteError: null
      };
    case "chat/send-start":
      return {
        ...state,
        messages: [...state.messages, { role: "user", content: action.question }],
        error: null,
        isAssistantTyping: true
      };
    case "chat/send-success":
      return {
        ...state,
        messages: [...state.messages, { role: "assistant", content: action.answer }],
        isAssistantTyping: false
      };
    case "chat/send-failure":
      return {
        ...state,
        error: action.error,
        isAssistantTyping: false
      };
    default:
      return state;
  }
}
