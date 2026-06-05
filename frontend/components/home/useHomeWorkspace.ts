"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  askQuestion,
  createConversation,
  deleteUserDocument,
  getConversationMessages,
  getUserConversations,
  getUserDocuments,
  type PersistedDocument
} from "../../lib/api";
import type { UploadMeta, WorkspaceState } from "./types";

type UseHomeWorkspaceArgs = {
  userId: string;
};

function waitForTransition() {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, 1200);
  });
}

export function useHomeWorkspace({ userId }: UseHomeWorkspaceArgs) {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [documentMeta, setDocumentMeta] = useState<WorkspaceState["documentMeta"]>(null);
  const [documents, setDocuments] = useState<PersistedDocument[]>([]);
  const [messages, setMessages] = useState<WorkspaceState["messages"]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const [view, setView] = useState<WorkspaceState["view"]>("upload");
  const [transitionMode, setTransitionMode] = useState<WorkspaceState["transitionMode"]>("indexing");
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isSearchClosing, setIsSearchClosing] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [documentToDelete, setDocumentToDelete] = useState<PersistedDocument | null>(null);
  const [isDeletingDocument, setIsDeletingDocument] = useState(false);
  const [isAssistantTyping, setIsAssistantTyping] = useState(false);

  const filteredDocuments = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return documents;
    return documents.filter((doc) => doc.filename.toLowerCase().includes(query));
  }, [documents, searchQuery]);

  const openSearch = useCallback(() => {
    setSearchQuery("");
    setIsSearchOpen(true);
  }, []);

  const closeSearch = useCallback(() => {
    setIsSearchClosing(true);
    window.setTimeout(() => {
      setIsSearchOpen(false);
      setIsSearchClosing(false);
    }, 250);
  }, []);

  const refreshDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    try {
      const nextDocuments = await getUserDocuments(userId);
      setDocuments(nextDocuments);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load documents.";
      setError(message);
    } finally {
      setLoadingDocuments(false);
    }
  }, [userId]);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isSearchOpen) {
        closeSearch();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeSearch, isSearchOpen]);

  const handleUploaded = useCallback(async (id: string, meta: UploadMeta) => {
    setTransitionMode("indexing");
    setView("indexing");
    setBusyDocumentId(id);
    setDocumentId(id);
    setConversationId(null);
    setDocumentMeta(meta);
    setMessages([]);
    setError(null);

    try {
      const [conversation] = await Promise.all([createConversation(userId, id), waitForTransition()]);
      setConversationId(conversation.conversation_id);
      await refreshDocuments();
      setView("chat");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to prepare conversation.";
      setError(message);
      setView("upload");
    } finally {
      setBusyDocumentId(null);
    }
  }, [refreshDocuments, userId]);

  const handleSelectDocument = useCallback(async (document: PersistedDocument) => {
    setTransitionMode("loading");
    setView("indexing");
    setBusyDocumentId(document.id);
    setDocumentId(document.id);
    setConversationId(null);
    setDocumentMeta({
      fileName: document.filename,
      uploadedAt: document.uploaded_at
    });
    setMessages([]);
    setError(null);

    try {
      const [conversations] = await Promise.all([getUserConversations(userId, document.id), waitForTransition()]);
      const activeConversation = conversations[0];
      const nextConversationId = activeConversation
        ? activeConversation.id
        : (await createConversation(userId, document.id)).conversation_id;
      const persistedMessages = await getConversationMessages(nextConversationId);

      setConversationId(nextConversationId);
      setMessages(
        persistedMessages.map((message) => ({
          role: message.role,
          content: message.content
        }))
      );
      setView("chat");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load document.";
      setError(message);
      setView("upload");
    } finally {
      setBusyDocumentId(null);
      closeSearch();
    }
  }, [closeSearch, userId]);

  const handleClear = useCallback(() => {
    setDocumentId(null);
    setConversationId(null);
    setDocumentMeta(null);
    setMessages([]);
    setError(null);
    setIsAssistantTyping(false);
    setResetSignal((value) => value + 1);
    setView("upload");
  }, []);

  const openDeleteDialog = useCallback((document: PersistedDocument) => {
    setDocumentToDelete(document);
  }, []);

  const closeDeleteDialog = useCallback(() => {
    if (!isDeletingDocument) {
      setDocumentToDelete(null);
    }
  }, [isDeletingDocument]);

  const handleDeleteDocument = useCallback(async () => {
    if (!documentToDelete) return;

    setIsDeletingDocument(true);
    setError(null);

    try {
      await deleteUserDocument(userId, documentToDelete.id);
      setDocuments((prev) => prev.filter((doc) => doc.id !== documentToDelete.id));

      if (documentId === documentToDelete.id) {
        handleClear();
      }

      closeSearch();
      setDocumentToDelete(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to delete document.";
      setError(message);
    } finally {
      setIsDeletingDocument(false);
    }
  }, [closeSearch, documentId, documentToDelete, handleClear, userId]);

  const handleSend = useCallback(async (question: string) => {
    if (!documentId || !conversationId) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setError(null);
    setIsAssistantTyping(true);

    try {
      const response = await askQuestion({
        documentId,
        conversationId,
        userId,
        message: question
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
    } finally {
      setIsAssistantTyping(false);
    }
  }, [conversationId, documentId, userId]);

  return {
    state: {
      documentId,
      conversationId,
      documentMeta,
      documents,
      filteredDocuments,
      messages,
      error,
      resetSignal,
      view,
      transitionMode,
      loadingDocuments,
      busyDocumentId,
      isSidebarOpen,
      isSearchOpen,
      isSearchClosing,
      searchQuery,
      documentToDelete,
      isDeletingDocument,
      isAssistantTyping
    },
    actions: {
      setSearchQuery,
      toggleSidebar: () => setIsSidebarOpen((value) => !value),
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
