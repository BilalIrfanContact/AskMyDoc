import test from "node:test";
import assert from "node:assert/strict";

import type { PersistedConversation, PersistedDocument, PersistedMessage } from "../../lib/api";
import type { ChatResponseBody } from "../../lib/api-contract";
import { createInitialWorkspaceState, workspaceReducer } from "./workspaceReducer";
import { createWorkspaceStateModule, type WorkspaceServices } from "./workspaceStateModule";
import type { WorkspaceState } from "./types";

type WorkspaceCoreState = Omit<WorkspaceState, "filteredDocuments">;

function createDeferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((nextResolve, nextReject) => {
    resolve = nextResolve;
    reject = nextReject;
  });

  return { promise, resolve, reject };
}

function createDocument(id: string, filename: string): PersistedDocument {
  return {
    id,
    filename,
    uploaded_at: "2026-06-14T00:00:00Z",
    storage_url: `https://example.com/${id}.pdf`,
    user_id: "user-1"
  };
}

function createHarness() {
  let state: WorkspaceCoreState = createInitialWorkspaceState();

  const documents = [createDocument("doc-a", "alpha.pdf"), createDocument("doc-b", "beta.pdf")];
  const conversationsByDocument = new Map<string, PersistedConversation[]>([
    ["doc-a", [{ id: "conv-a", document_id: "doc-a", created_at: "2026-06-14T00:00:00Z", user_id: "user-1" }]],
    ["doc-b", [{ id: "conv-b", document_id: "doc-b", created_at: "2026-06-14T00:00:00Z", user_id: "user-1" }]]
  ]);
  const messagesByConversation = new Map<string, PersistedMessage[]>([
    ["conv-a", [{ id: "msg-a", conversation_id: "conv-a", role: "assistant", content: "alpha", created_at: "2026-06-14T00:00:00Z" }]],
    ["conv-b", [{ id: "msg-b", conversation_id: "conv-b", role: "assistant", content: "beta", created_at: "2026-06-14T00:00:00Z" }]]
  ]);

  const services: WorkspaceServices = {
    askQuestion: async ({ message }): Promise<ChatResponseBody> => ({
      answer: `answer:${message}`,
      answer_status: "answered",
      citations: [],
      intent: "qa",
      retrieval_mode: "semantic"
    }),
    createConversation: async (documentId: string) => ({
      conversation_id: `conv-new-${documentId}`
    }),
    deleteUserDocument: async (_documentId: string) => ({
      deleted: true as const,
      lifecycle_status: "deleted" as const,
      cleanup_status: "completed" as const
    }),
    getConversationMessages: async (conversationId: string) => messagesByConversation.get(conversationId) ?? [],
    getUserConversations: async (documentId?: string) => {
      if (!documentId) return [];
      return conversationsByDocument.get(documentId) ?? [];
    },
    getUserDocuments: async () => documents,
    scheduleSearchClose: (callback: () => void) => callback(),
    waitForTransition: async () => {}
  };

  return {
    documents,
    getState() {
      return state;
    },
    setState(nextState: WorkspaceCoreState) {
      state = nextState;
    },
    services,
    createModule() {
      return createWorkspaceStateModule({
        dispatch(action) {
          state = workspaceReducer(state, action);
        },
        getState() {
          return state;
        },
        services
      });
    }
  };
}

test("ignores upload bootstrap completion after the workspace is cleared", async () => {
  const harness = createHarness();
  const documentsDeferred = createDeferred<PersistedDocument[]>();
  const conversationDeferred = createDeferred<{ conversation_id: string }>();
  const transitionDeferred = createDeferred<void>();

  harness.services.getUserDocuments = async () => documentsDeferred.promise;
  harness.services.createConversation = async () => conversationDeferred.promise;
  harness.services.waitForTransition = async () => {
    await transitionDeferred.promise;
  };

  const workspaceModule = harness.createModule();

  const uploadPromise = workspaceModule.handleUploaded("doc-upload", {
    fileName: "upload.pdf",
    fileSize: "20 KB",
    chunkCount: 3,
    storedCount: 3
  });

  workspaceModule.clearWorkspace();
  documentsDeferred.resolve(harness.documents);
  transitionDeferred.resolve();
  conversationDeferred.resolve({ conversation_id: "conv-upload" });

  const result = await uploadPromise;

  assert.deepEqual(result, { status: "cancelled" });
  assert.equal(harness.getState().view, "upload");
  assert.equal(harness.getState().documentId, null);
  assert.equal(harness.getState().conversationId, null);
});

test("latest document selection wins when requests resolve out of order", async () => {
  const harness = createHarness();
  const transitionA = createDeferred<void>();
  const transitionB = createDeferred<void>();
  const conversationsA = createDeferred<PersistedConversation[]>();
  const conversationsB = createDeferred<PersistedConversation[]>();

  let selectCalls = 0;
  harness.services.waitForTransition = async () => {
    selectCalls += 1;
    await (selectCalls === 1 ? transitionA.promise : transitionB.promise);
  };
  harness.services.getUserConversations = async (documentId?: string) => {
    if (documentId === "doc-a") return conversationsA.promise;
    if (documentId === "doc-b") return conversationsB.promise;
    return [];
  };

  const workspaceModule = harness.createModule();

  const selectA = workspaceModule.handleSelectDocument(harness.documents[0]);
  const selectB = workspaceModule.handleSelectDocument(harness.documents[1]);

  conversationsB.resolve([{ id: "conv-b", document_id: "doc-b", created_at: "2026-06-14T00:00:00Z", user_id: "user-1" }]);
  transitionB.resolve();
  await selectB;

  conversationsA.resolve([{ id: "conv-a", document_id: "doc-a", created_at: "2026-06-14T00:00:00Z", user_id: "user-1" }]);
  transitionA.resolve();
  await selectA;

  assert.equal(harness.getState().documentId, "doc-b");
  assert.equal(harness.getState().conversationId, "conv-b");
  assert.deepEqual(harness.getState().messages, [{ role: "assistant", content: "beta" }]);
});

test("ignores stale chat responses after clearing the workspace", async () => {
  const harness = createHarness();
  const chatDeferred = createDeferred<ChatResponseBody>();

  harness.services.askQuestion = async () => chatDeferred.promise;

  harness.setState({
    ...createInitialWorkspaceState(),
    documentId: "doc-a",
    conversationId: "conv-a",
    view: "chat"
  });
  const workspaceModule = harness.createModule();

  const sendPromise = workspaceModule.handleSend("What is alpha?");
  workspaceModule.clearWorkspace();
  chatDeferred.resolve({
    answer: "stale answer",
    answer_status: "answered",
    citations: [],
    intent: "qa",
    retrieval_mode: "semantic"
  });
  await sendPromise;

  assert.equal(harness.getState().view, "upload");
  assert.equal(harness.getState().messages.length, 0);
  assert.equal(harness.getState().error, null);
});
