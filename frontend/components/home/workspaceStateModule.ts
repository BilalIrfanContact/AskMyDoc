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
import type { WorkspaceAction } from "./workspaceReducer";
import type { Message, UploadBootstrapResult, UploadMeta, WorkspaceState } from "./types";

type WorkspaceCoreState = Omit<WorkspaceState, "filteredDocuments">;

export type WorkspaceServices = {
  askQuestion: typeof askQuestion;
  createConversation: typeof createConversation;
  deleteUserDocument: typeof deleteUserDocument;
  getConversationMessages: typeof getConversationMessages;
  getUserConversations: typeof getUserConversations;
  getUserDocuments: typeof getUserDocuments;
  waitForTransition: () => Promise<void>;
  scheduleSearchClose: (callback: () => void) => void;
};

type WorkspaceStateModuleOptions = {
  dispatch: (action: WorkspaceAction) => void;
  getState: () => WorkspaceCoreState;
  services?: Partial<WorkspaceServices>;
};

type RefreshDocumentsOptions = {
  suppressFailureError?: boolean;
};

const defaultServices: WorkspaceServices = {
  askQuestion,
  createConversation,
  deleteUserDocument,
  getConversationMessages,
  getUserConversations,
  getUserDocuments,
  waitForTransition() {
    return new Promise<void>((resolve) => {
      window.setTimeout(resolve, 1200);
    });
  },
  scheduleSearchClose(callback) {
    window.setTimeout(callback, 250);
  }
};

function createFlowTracker() {
  let nextRunId = 0;
  let activeRunId = 0;

  return {
    begin() {
      activeRunId = nextRunId + 1;
      nextRunId = activeRunId;
      return activeRunId;
    },
    invalidate() {
      activeRunId = nextRunId + 1;
      nextRunId = activeRunId;
    },
    isActive(runId: number) {
      return activeRunId === runId;
    }
  };
}

export function createWorkspaceStateModule({
  dispatch,
  getState,
  services: overrides
}: WorkspaceStateModuleOptions) {
  const services = { ...defaultServices, ...overrides };
  const workflowRuns = createFlowTracker();
  const chatRuns = createFlowTracker();

  async function refreshDocuments(options?: RefreshDocumentsOptions) {
    dispatch({ type: "documents/load-start" });
    try {
      const nextDocuments = await services.getUserDocuments();
      dispatch({ type: "documents/load-success", documents: nextDocuments });
      return nextDocuments;
    } catch (error) {
      if (options?.suppressFailureError) {
        dispatch({ type: "documents/load-finish" });
        return getState().documents;
      }

      const message = error instanceof Error ? error.message : "Failed to load documents.";
      dispatch({ type: "documents/load-failure", error: message });
      throw error;
    }
  }

  function openSearch() {
    dispatch({ type: "search/open" });
  }

  function closeSearch() {
    dispatch({ type: "search/start-close" });
    services.scheduleSearchClose(() => {
      dispatch({ type: "search/finish-close" });
    });
  }

  function setSearchQuery(query: string) {
    dispatch({ type: "search/set-query", query });
  }

  function toggleSidebar() {
    dispatch({ type: "sidebar/toggle" });
  }

  function clearWorkspace() {
    workflowRuns.invalidate();
    chatRuns.invalidate();
    dispatch({ type: "workflow/clear" });
  }

  async function handleUploaded(documentId: string, meta: UploadMeta): Promise<UploadBootstrapResult> {
    const runId = workflowRuns.begin();

    dispatch({ type: "workflow/upload-start", documentId, documentMeta: meta });

    try {
      await refreshDocuments({ suppressFailureError: true });
      const [conversation] = await Promise.all([
        services.createConversation(documentId),
        services.waitForTransition()
      ]);

      if (!workflowRuns.isActive(runId)) {
        return { status: "cancelled" };
      }

      dispatch({
        type: "workflow/chat-ready",
        conversationId: conversation.conversation_id,
        messages: []
      });
      return { status: "ready" };
    } catch (error) {
      if (!workflowRuns.isActive(runId)) {
        return { status: "cancelled" };
      }

      const message =
        error instanceof Error ? error.message : "Failed to prepare conversation.";
      const recoveryMessage = `${message} The document was uploaded successfully. Select it from the sidebar to try again.`;
      dispatch({ type: "workflow/bootstrap-failure", error: recoveryMessage });
      return {
        status: "document-ready",
        message: recoveryMessage
      };
    }
  }

  async function handleSelectDocument(document: PersistedDocument) {
    const runId = workflowRuns.begin();

    dispatch({
      type: "workflow/select-start",
      documentId: document.id,
      documentMeta: {
        fileName: document.filename,
        uploadedAt: document.uploaded_at
      }
    });

    try {
      const [conversations] = await Promise.all([
        services.getUserConversations(document.id),
        services.waitForTransition()
      ]);
      const activeConversation = conversations[0];
      const nextConversationId = activeConversation
        ? activeConversation.id
        : (await services.createConversation(document.id)).conversation_id;
      const persistedMessages = await services.getConversationMessages(nextConversationId);

      if (!workflowRuns.isActive(runId)) {
        return;
      }

      dispatch({
        type: "workflow/chat-ready",
        conversationId: nextConversationId,
        messages: persistedMessages.map((message) => ({
          role: message.role === "assistant" ? "assistant" : "user",
          content: message.content
        }))
      });
    } catch (error) {
      if (!workflowRuns.isActive(runId)) {
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load document.";
      dispatch({ type: "workflow/failure", error: message });
    } finally {
      closeSearch();
    }
  }

  function openDeleteDialog(document: PersistedDocument) {
    dispatch({ type: "delete/open", document });
  }

  function closeDeleteDialog() {
    dispatch({ type: "delete/close" });
  }

  async function handleDeleteDocument() {
    const currentState = getState();
    if (!currentState.documentToDelete) return;

    const documentToDelete = currentState.documentToDelete;
    dispatch({ type: "delete/start" });

    try {
      await services.deleteUserDocument(documentToDelete.id);

      if (getState().documentId === documentToDelete.id) {
        clearWorkspace();
      }

      dispatch({ type: "delete/success", documentId: documentToDelete.id });
    } catch (error) {
      if (
        error instanceof DeleteFlowError &&
        (
          error.reasonCode === "conversation_cleanup_failed" ||
          error.reasonCode === "indexing_cleanup_failed"
        )
      ) {
        if (getState().documentId === documentToDelete.id) {
          clearWorkspace();
        }
        try {
          await refreshDocuments();
        } catch {
          // Keep the original delete error as the visible failure and always exit deleting state.
        }
      }

      const message = getDeleteErrorMessage(error);
      dispatch({ type: "delete/failure", error: message });
    }
  }

  async function handleSend(question: string) {
    const currentState = getState();
    if (!currentState.documentId || !currentState.conversationId) return;

    const documentId = currentState.documentId;
    const conversationId = currentState.conversationId;
    const runId = chatRuns.begin();

    dispatch({ type: "chat/send-start", question });

    try {
      const response = await services.askQuestion({
        documentId,
        conversationId,
        message: question
      });

      const nextState = getState();
      if (
        !chatRuns.isActive(runId) ||
        nextState.documentId !== documentId ||
        nextState.conversationId !== conversationId
      ) {
        return;
      }

      dispatch({ type: "chat/send-success", answer: response.answer });
    } catch (error) {
      const nextState = getState();
      if (
        !chatRuns.isActive(runId) ||
        nextState.documentId !== documentId ||
        nextState.conversationId !== conversationId
      ) {
        return;
      }

      const message = error instanceof Error ? error.message : "Something went wrong.";
      dispatch({ type: "chat/send-failure", error: message });
    }
  }

  return {
    refreshDocuments,
    openSearch,
    closeSearch,
    setSearchQuery,
    toggleSidebar,
    clearWorkspace,
    handleUploaded,
    handleSelectDocument,
    openDeleteDialog,
    closeDeleteDialog,
    handleDeleteDocument,
    handleSend
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
        ? error.reasonCode === "conversation_cleanup_failed" ||
          error.reasonCode === "indexing_cleanup_failed"
          ? " The document has already been removed from the workspace."
          : " Some cleanup steps already ran. Retry delete to finish removing the document."
        : "";

  if (error.reasonCode === "conversation_lookup_failed") {
    return `${error.message}${recoveryNote} Delete did not start, so the document should still be visible.`;
  }

  if (error.reasonCode === "conversation_cleanup_failed") {
    return `${error.message}${recoveryNote} The document was removed, but chat cleanup is still incomplete.`;
  }

  if (error.reasonCode === "indexing_cleanup_failed") {
    return `${error.message}${recoveryNote} The document was removed, but retrieval cleanup is still incomplete.`;
  }

  if (
    error.reasonCode === "storage_delete_failed" ||
    error.reasonCode === "metadata_delete_failed"
  ) {
    return `${error.message}${recoveryNote} The document may still appear until deletion finishes.`;
  }

  return `${error.message}${recoveryNote}`;
}

export type WorkspaceStateModule = ReturnType<typeof createWorkspaceStateModule>;
