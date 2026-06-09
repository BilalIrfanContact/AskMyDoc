"use client";

import { useCallback, useEffect, useMemo, useReducer } from "react";

import {
  askQuestion,
  createConversation,
  DeleteFlowError,
  deleteUserDocument,
  getConversationMessages,
  getUserConversations,
  getUserDocuments,
  type PersistedDocument
} from "../../lib/api";
import type { UploadBootstrapResult, UploadMeta, WorkspaceState } from "./types";
import { createInitialWorkspaceState, workspaceReducer } from "./workspaceReducer";

function waitForTransition() {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, 1200);
  });
}

export function useHomeWorkspace() {
  const [state, dispatch] = useReducer(workspaceReducer, undefined, createInitialWorkspaceState);

  const filteredDocuments = useMemo(() => {
    const query = state.searchQuery.trim().toLowerCase();
    if (!query) return state.documents;
    return state.documents.filter((doc) => doc.filename.toLowerCase().includes(query));
  }, [state.documents, state.searchQuery]);

  const openSearch = useCallback(() => {
    dispatch({ type: "search/open" });
  }, []);

  const closeSearch = useCallback(() => {
    dispatch({ type: "search/start-close" });
    window.setTimeout(() => {
      dispatch({ type: "search/finish-close" });
    }, 250);
  }, []);

  const refreshDocuments = useCallback(async () => {
    dispatch({ type: "documents/load-start" });
    try {
      const nextDocuments = await getUserDocuments();
      dispatch({ type: "documents/load-success", documents: nextDocuments });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load documents.";
      dispatch({ type: "documents/load-failure", error: message });
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && state.isSearchOpen) {
        closeSearch();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeSearch, state.isSearchOpen]);

  const handleUploaded = useCallback(async (id: string, meta: UploadMeta) => {
    dispatch({ type: "workflow/upload-start", documentId: id, documentMeta: meta });

    try {
      await refreshDocuments();
      const [conversation] = await Promise.all([createConversation(id), waitForTransition()]);
      dispatch({
        type: "workflow/chat-ready",
        conversationId: conversation.conversation_id,
        messages: []
      });
      return { status: "ready" } satisfies UploadBootstrapResult;
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to prepare conversation.";
      const recoveryMessage = `${message} The document was uploaded successfully. Select it from the sidebar to try again.`;
      dispatch({ type: "workflow/bootstrap-failure", error: recoveryMessage });
      return {
        status: "document-ready",
        message: recoveryMessage
      } satisfies UploadBootstrapResult;
    }
  }, [refreshDocuments]);

  const handleSelectDocument = useCallback(async (document: PersistedDocument) => {
    dispatch({
      type: "workflow/select-start",
      documentId: document.id,
      documentMeta: {
        fileName: document.filename,
        uploadedAt: document.uploaded_at
      }
    });

    try {
      const [conversations] = await Promise.all([getUserConversations(document.id), waitForTransition()]);
      const activeConversation = conversations[0];
      const nextConversationId = activeConversation
        ? activeConversation.id
        : (await createConversation(document.id)).conversation_id;
      const persistedMessages = await getConversationMessages(nextConversationId);

      dispatch({
        type: "workflow/chat-ready",
        conversationId: nextConversationId,
        messages: persistedMessages.map((message) => ({
          role: message.role,
          content: message.content
        }))
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load document.";
      dispatch({ type: "workflow/failure", error: message });
    } finally {
      closeSearch();
    }
  }, [closeSearch]);

  const handleClear = useCallback(() => {
    dispatch({ type: "workflow/clear" });
  }, []);

  const openDeleteDialog = useCallback((document: PersistedDocument) => {
    dispatch({ type: "delete/open", document });
  }, []);

  const closeDeleteDialog = useCallback(() => {
    dispatch({ type: "delete/close" });
  }, []);

  const handleDeleteDocument = useCallback(async () => {
    if (!state.documentToDelete) return;

    dispatch({ type: "delete/start" });

    try {
      await deleteUserDocument(state.documentToDelete.id);

      if (state.documentId === state.documentToDelete.id) {
        handleClear();
      }

      dispatch({ type: "delete/success", documentId: state.documentToDelete.id });
    } catch (err) {
      const message = getDeleteErrorMessage(err);
      dispatch({ type: "delete/failure", error: message });
    }
  }, [handleClear, state.documentId, state.documentToDelete]);

  const handleSend = useCallback(async (question: string) => {
    if (!state.documentId || !state.conversationId) return;

    dispatch({ type: "chat/send-start", question });

    try {
      const response = await askQuestion({
        documentId: state.documentId,
        conversationId: state.conversationId,
        message: question
      });
      dispatch({ type: "chat/send-success", answer: response.answer });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      dispatch({ type: "chat/send-failure", error: message });
    }
  }, [state.conversationId, state.documentId]);

  return {
    state: {
      ...state,
      filteredDocuments,
    },
    actions: {
      setSearchQuery: (query: string) => dispatch({ type: "search/set-query", query }),
      toggleSidebar: () => dispatch({ type: "sidebar/toggle" }),
      openSearch,
      closeSearch,
      handleUploaded,
      handleSelectDocument,
      handleClear,
      openDeleteDialog,
      closeDeleteDialog,
      handleDeleteDocument,
      handleSend
    },
    helpers: {
      getInitials(name: string) {
        if (!name) return "??";
        const parts = name.split(" ").filter(Boolean);
        if (parts.length === 0) return "??";
        if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      }
    }
  };
}

function getDeleteErrorMessage(error: unknown) {
  if (!(error instanceof Error)) {
    return "Failed to delete document.";
  }

  if (!(error instanceof DeleteFlowError)) {
    return error.message;
  }

  const recoveryNote =
    error.cleanupStatus === "not-started"
      ? " No cleanup steps were applied."
      : error.cleanupStatus === "partial"
        ? " Some cleanup steps already ran. Retry delete to finish removing the document."
        : "";

  if (error.failureStage === "indexing") {
    return `${error.message}${recoveryNote} The document will remain visible until cleanup completes.`;
  }

  if (error.failureStage === "storage" || error.failureStage === "metadata") {
    return `${error.message}${recoveryNote} The document may still appear until deletion finishes.`;
  }

  return `${error.message}${recoveryNote}`;
}
