"use client";

import { useCallback, useEffect, useState } from "react";
import { signOut } from "next-auth/react";

import ChatInput from "./ChatInput";
import ChatWindow from "./ChatWindow";
import PDFUploader from "./PDFUploader";
import {
  askQuestion,
  createConversation,
  getConversationMessages,
  getUserConversations,
  getUserDocuments,
  type PersistedDocument
} from "../lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ViewState = "upload" | "indexing" | "chat";
type TransitionMode = "indexing" | "loading";

type DocumentMeta = {
  fileName: string;
  fileSize?: string;
  chunkCount?: number;
  storedCount?: number;
  uploadedAt?: string | null;
};

type HomeClientProps = {
  userId: string;
  greeting: string;
};

export default function HomeClient({ userId, greeting }: HomeClientProps) {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [documentMeta, setDocumentMeta] = useState<DocumentMeta | null>(null);
  const [documents, setDocuments] = useState<PersistedDocument[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const [view, setView] = useState<ViewState>("upload");
  const [transitionMode, setTransitionMode] = useState<TransitionMode>("indexing");
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [busyDocumentId, setBusyDocumentId] = useState<string | null>(null);

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

  const waitForTransition = () =>
    new Promise<void>((resolve) => {
      window.setTimeout(resolve, 1200);
    });

  const handleUploaded = async (
    id: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => {
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
  };

  const handleSelectDocument = async (document: PersistedDocument) => {
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
    }
  };

  const handleClear = () => {
    setDocumentId(null);
    setConversationId(null);
    setDocumentMeta(null);
    setMessages([]);
    setError(null);
    setResetSignal((value) => value + 1);
    setView("upload");
  };

  const handleSend = async (question: string) => {
    if (!documentId || !conversationId) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setError(null);

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
    }
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand-lockup" href="#workspace" aria-label="AskMyDoc home">
          <img src="/logo.png" alt="AskMyDoc Logo" width={32} height={32} />
          <span className="brand-name">AskMyDoc</span>
        </a>

        <div className="topbar-actions">
          <button type="button" className="btn-ghost" onClick={handleClear} disabled={view === "upload"}>
            New document
          </button>
          <button type="button" className="btn-ghost" onClick={() => signOut({ callbackUrl: "/login" })}>
            Sign out
          </button>
        </div>
      </header>

      <main className="shell-grid" id="workspace">
        {view === "upload" ? (
          <section className="upload-stage">
            <h1 className="hero-title">{greeting}</h1>

            <aside className="panel-upload card-ivory">
              <PDFUploader
                onUploaded={handleUploaded}
                onClear={handleClear}
                activeDocumentId={documentId}
                resetSignal={resetSignal}
                userId={userId}
              />
            </aside>

            <section className="documents-panel card-ivory" aria-label="Recent documents">
              <div className="documents-panel-head">
                <h2 className="documents-title">Recent documents</h2>
                {loadingDocuments ? <span className="documents-meta">Loading...</span> : null}
              </div>

              {!loadingDocuments && documents.length === 0 ? (
                <p className="text-olive">No saved documents yet.</p>
              ) : null}

              {documents.length > 0 ? (
                <div className="documents-list">
                  {documents.map((document) => (
                    <button
                      key={document.id}
                      type="button"
                      className="document-row"
                      onClick={() => void handleSelectDocument(document)}
                      disabled={busyDocumentId === document.id}
                    >
                      <span className="document-name">{document.filename}</span>
                      <span className="document-meta">
                        {busyDocumentId === document.id
                          ? "Opening..."
                          : document.uploaded_at
                            ? new Date(document.uploaded_at).toLocaleDateString()
                            : "Saved"}
                      </span>
                    </button>
                  ))}
                </div>
              ) : null}
            </section>
          </section>
        ) : null}

        {view === "indexing" && documentMeta ? (
          <section className="transition-stage">
            <div className="card-ivory transition-card" aria-live="polite">
              <span className="badge">
                {transitionMode === "indexing" ? "Indexing document" : "Loading document"}
              </span>
              <h2 className="transition-title">{documentMeta.fileName}</h2>
              <p className="text-olive">
                {transitionMode === "indexing"
                  ? "Building the retrieval index and preparing the chat workspace."
                  : "Restoring the latest saved conversation for this document."}
              </p>
              <div className="upload-progress" aria-hidden="true">
                <div className="upload-progress-fill"></div>
              </div>
            </div>
          </section>
        ) : null}

        {view === "chat" ? (
          <section className="chat-stage">
            <section className="panel-chat" id="chat" aria-label="Chat workspace">
              <div className="panel-head">
                <div>
                  {documentMeta ? <h2 className="panel-title-file">{documentMeta.fileName}</h2> : null}
                  {documentMeta?.uploadedAt ? (
                    <p className="panel-subtitle">Saved {new Date(documentMeta.uploadedAt).toLocaleString()}</p>
                  ) : null}
                </div>
              </div>

              <ChatWindow messages={messages} />

              {error ? <p style={{ color: "var(--color-error)", padding: "0 24px" }}>{error}</p> : null}

              <ChatInput disabled={!documentId || !conversationId} onSend={handleSend} />
            </section>
          </section>
        ) : null}
      </main>
    </div>
  );
}
