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
  userName: string;
  greeting: string;
};

export default function HomeClient({ userId, userName, greeting }: HomeClientProps) {
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
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

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

  const SidebarIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
      <line x1="9" x2="9" y1="3" y2="21"/>
    </svg>
  );

  const FileIcon = () => (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path fill="currentColor" d="M17.226 0C18.206 0 19 .814 19 1.818v16.364C19 19.186 18.206 20 17.226 20H4.542c-.98 0-1.774-.814-1.774-1.818l-.001-1.686H1.665a.674.674 0 0 1-.665-.68c0-.377.298-.682.665-.682h1.102v-2.419H1.665A.674.674 0 0 1 1 12.033c0-.377.298-.682.665-.682l1.102-.001V8.919H1.665A.674.674 0 0 1 1 8.239c0-.377.298-.682.665-.682l1.102-.001V5.122H1.665A.674.674 0 0 1 1 4.441c0-.377.298-.682.665-.682l1.102-.001l.001-1.94C2.768.814 3.562 0 4.542 0h12.684Zm-3.248 1.364H4.466a.344.344 0 0 0-.246.118a.428.428 0 0 0-.12.268v2.008h.844a.668.668 0 0 1 .665.683a.674.674 0 0 1-.665.681H4.1v2.431h.873l.045.007l-.074-.004a.65.65 0 0 1 .313.08l.02.011a.53.53 0 0 1 .124.101l-.055-.053a.684.684 0 0 1 .261.509l-.007-.08a.676.676 0 0 1-.596.792l-.03.002l-.016.001H4.1v2.431h.844a.65.65 0 0 1 .308.078c.062.03.111.066.15.111l-.03-.029a.687.687 0 0 1 .216.696l-.009.03a.682.682 0 0 1-.286.378l-.01.005a.644.644 0 0 1-.339.095H4.1v2.419h.873c.008 0 .016.002.023.004l-.052-.004c.367 0 .665.305.665.682c0 .222-.104.42-.265.544l-.013.01a.524.524 0 0 1-.062.04l-.008.004a.628.628 0 0 1-.275.082h-.013l-.015.002h-.014l-.844-.001v1.764c.006.067.03.13.072.19l.048.058c.073.077.163.12.27.13h9.488V1.364Zm3.264-.002h-1.938v17.274h1.974c.091 0 .176-.042.256-.13a.473.473 0 0 0 .134-.267V1.794a.486.486 0 0 0-.134-.298a.415.415 0 0 0-.292-.134Z"/>
    </svg>
  );

  const PlusIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/>
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );

  const SearchIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  );

  const LogoutIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  );

  const getInitials = (name: string) => {
    if (!name) return "??";
    const parts = name.split(" ").filter(Boolean);
    if (parts.length === 0) return "??";
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  };

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
      <aside className={`sidebar ${!isSidebarOpen ? "sidebar-collapsed" : ""}`}>
        <div className="sidebar-content">
          <header className="sidebar-header">
            <div className="sidebar-brand">
              <img src="/logo.png" alt="Logo" width={32} height={32} />
              <span className="brand-name">AskMyDoc</span>
            </div>
            <button
              type="button"
              className="sidebar-toggle"
              onClick={() => setIsSidebarOpen(!isSidebarOpen)}
              title={isSidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
            >
              <SidebarIcon />
            </button>
          </header>

          <button
            type="button"
            className={`btn-brand ${!isSidebarOpen ? "icon-only" : ""}`}
            style={{ width: "100%", justifyContent: isSidebarOpen ? "flex-start" : "center", gap: "12px" }}
            onClick={handleClear}
          >
            <PlusIcon />
            {isSidebarOpen && <span>New document</span>}
          </button>

          <div className="sidebar-search-wrap">
            <div className="sidebar-search-icon">
              <SearchIcon />
            </div>
            <input
              type="text"
              className="sidebar-search-input"
              placeholder="Search documents..."
            />
          </div>

          {isSidebarOpen && <h2 className="sidebar-section-title">Recent documents</h2>}

          <nav className="sidebar-nav-list" style={{ marginTop: isSidebarOpen ? "0" : "24px" }}>
            {documents.map((doc) => (
              <button
                key={doc.id}
                type="button"
                className={`sidebar-nav-item ${documentId === doc.id ? "active" : ""}`}
                onClick={() => void handleSelectDocument(doc)}
                disabled={busyDocumentId === doc.id}
                title={doc.filename}
              >
                <div className="sidebar-doc-icon">
                  <FileIcon />
                </div>
                {isSidebarOpen && (
                  <div className="sidebar-doc-name">
                    {doc.filename}
                  </div>
                )}
              </button>
            ))}
            {!loadingDocuments && documents.length === 0 && isSidebarOpen && (
              <p className="text-label" style={{ padding: "0 8px", color: "var(--color-stone-gray)" }}>
                No documents yet.
              </p>
            )}
          </nav>
        </div>

        <footer className="sidebar-footer">
          <div className="avatar" title={userName}>
            {getInitials(userName)}
          </div>
          <div className="user-info">
            <span className="user-name">{userName}</span>
            <span className="user-plan">Free plan</span>
          </div>
          <button
            type="button"
            className="logout-btn"
            onClick={() => signOut({ callbackUrl: "/login" })}
            title="Sign out"
          >
            <LogoutIcon />
          </button>
        </footer>
      </aside>

      <main className="main-stage">
        <header className="topbar">
          {/* Topbar actions removed as they are now in the sidebar footer */}
        </header>

        <section className="shell-grid" id="workspace">
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
        </section>
      </main>
    </div>
  );
}
