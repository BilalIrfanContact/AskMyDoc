"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { signOut } from "next-auth/react";

import ChatInput from "./ChatInput";
import ChatWindow from "./ChatWindow";
import PDFUploader from "./PDFUploader";
import {
  askQuestion,
  createConversation,
  deleteUserDocument,
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
  userName: string;
  greeting: string;
};

export default function HomeClient({ userName, greeting }: HomeClientProps) {
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
    setTimeout(() => {
      setIsSearchOpen(false);
      setIsSearchClosing(false);
    }, 250);
  }, []);

  const refreshDocuments = useCallback(async () => {
    setLoadingDocuments(true);
    try {
      const nextDocuments = await getUserDocuments();
      setDocuments(nextDocuments);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load documents.";
      setError(message);
    } finally {
      setLoadingDocuments(false);
    }
  }, []);

  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isSearchOpen) {
        closeSearch();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isSearchOpen, closeSearch]);

  const SidebarIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
      <line x1="9" x2="9" y1="3" y2="21"/>
    </svg>
  );

  const FileIcon = () => (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path fill="currentColor" d="M17.226 0C18.206 0 19 .814 19 1.818v16.364C19 19.186 18.206 20 17.226 20H4.542c-.98 0-1.774-.814-1.774-1.818l-.001-1.686H1.665a.674.674 0 0 1-.665-.68c0-.377.298-.682.665-.682h1.102v-2.419H1.665A.674.674 0 0 1 1 12.033c0-.377.298-.682.665-.682l1.102-.001V8.919H1.665A.674.674 0 0 1 1 8.239c0-.377.298-.682.665-.682l1.102-.001V5.122H1.665A.674.674 0 0 1 1 4.441c0-.377.298-.682.665-.682l1.102-.001l.001-1.94C2.768.814 3.562 0 4.542 0h12.684Zm-3.248 1.364H4.466a.344.344 0 0 0-.246.118a.428.428 0 0 0-.12.268v2.008h.844a.668.668 0 0 1 .665.683a.674.674 0 0 1-.665.681H4.1v2.431h.873l.045.007l-.074-.004a.65.65 0 0 1 .313.08l.02.011a.53.53 0 0 1 .124.101l-.055-.053a.684.684 0 0 1 .261.509l-.007-.08a.676.676 0 0 1-.596.792l-.03.002l-.016.001H4.1v2.431h.844a.65.65(0 0 1 .308.078c.062.03.111.066.15.111l-.03-.029a.687.687 0 0 1 .216.696l-.009.03a.682.682 0 0 1-.286.378l-.01.005a.644.644 0 0 1-.339.095H4.1v2.419h.873c.008 0 .016.002.023.004l-.052-.004c.367 0 .665.305.665.682c0 .222-.104.42-.265.544l-.013.01a.524.524 0 0 1-.062.04l-.008.004a.628.628 0 0 1-.275.082h-.013l-.015.002h-.014l-.844-.001v1.764c.006.067.03.13.072.19l.048.058c.073.077.163.12.27.13h9.488V1.364Zm3.264-.002h-1.938v17.274h1.974c.091 0 .176-.042.256-.13a.473.473 0 0 0 .134-.267V1.794a.486.486 0 0 0-.134-.298a.415.415 0 0 0-.292-.134Z"/>
    </svg>
  );

  const PlusIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19"/>
      <line x1="5" y1="12" x2="19" y2="12"/>
    </svg>
  );

  const MagnifyIcon = () => (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8"/>
      <line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
  );

  const LogoutIcon = () => (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
      <polyline points="16 17 21 12 16 7"/>
      <line x1="21" y1="12" x2="9" y2="12"/>
    </svg>
  );

  const TrashIcon = () => (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18"/>
      <path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
      <path d="M10 11v6"/>
      <path d="M14 11v6"/>
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
      const [conversation] = await Promise.all([createConversation(id), waitForTransition()]);
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
      const [conversations] = await Promise.all([getUserConversations(document.id), waitForTransition()]);
      const activeConversation = conversations[0];
      const nextConversationId = activeConversation
        ? activeConversation.id
        : (await createConversation(document.id)).conversation_id;
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
  };

  const handleClear = () => {
    setDocumentId(null);
    setConversationId(null);
    setDocumentMeta(null);
    setMessages([]);
    setError(null);
    setIsAssistantTyping(false);
    setResetSignal((value) => value + 1);
    setView("upload");
  };

  const handleDeleteDocument = async () => {
    if (!documentToDelete) return;

    setIsDeletingDocument(true);
    setError(null);

    try {
      await deleteUserDocument(documentToDelete.id);
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
  };

  const handleSend = async (question: string) => {
    if (!documentId || !conversationId) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setError(null);
    setIsAssistantTyping(true);

    try {
      const response = await askQuestion({
        documentId,
        conversationId,
        message: question
      });
      setMessages((prev) => [...prev, { role: "assistant", content: response.answer }]);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
    } finally {
      setIsAssistantTyping(false);
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

          <button type="button" className="sidebar-action-btn" onClick={handleClear}>
            <div className="sidebar-action-icon"><PlusIcon /></div>
            {isSidebarOpen && <span>New document</span>}
          </button>

          <button type="button" className="sidebar-action-btn" onClick={openSearch}>
            <div className="sidebar-action-icon"><MagnifyIcon /></div>
            {isSidebarOpen && <span>Search</span>}
          </button>

          <nav className="sidebar-nav">
            {isSidebarOpen && <h4 className="sidebar-section-title">Recent documents</h4>}
            <div className="sidebar-nav-list">
              {documents.map((doc) => (
                <div
                  key={doc.id}
                  className={`sidebar-doc-row ${documentId === doc.id ? "active" : ""}`}
                  title={doc.filename}
                >
                  <button
                    type="button"
                    className={`sidebar-nav-item ${documentId === doc.id ? "active" : ""}`}
                    onClick={() => void handleSelectDocument(doc)}
                    disabled={busyDocumentId === doc.id}
                  >
                    <div className="sidebar-doc-icon">
                      <FileIcon />
                    </div>
                    {isSidebarOpen && (
                      <div className="sidebar-doc-info">
                        <span className="sidebar-doc-name">{doc.filename}</span>
                      </div>
                    )}
                  </button>
                  {isSidebarOpen && (
                    <button
                      type="button"
                      className="sidebar-doc-delete"
                      aria-label={`Delete ${doc.filename}`}
                      title={`Delete ${doc.filename}`}
                      onClick={() => setDocumentToDelete(doc)}
                      disabled={isDeletingDocument}
                    >
                      <TrashIcon />
                    </button>
                  )}
                </div>
              ))}
              {!loadingDocuments && documents.length === 0 && isSidebarOpen && (
                <p className="text-label" style={{ padding: "0 14px", color: "var(--color-stone-gray)" }}>
                  No documents yet.
                </p>
              )}
            </div>
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
              <div className="hero-lockup">
                <img src="/logo.png" alt="AskMyDoc icon" width={44} height={44} className="hero-icon" />
                <h1 className="hero-title hero-title-home">{greeting}</h1>
              </div>

              <aside className="panel-upload card-ivory">
                <PDFUploader
                  onUploaded={handleUploaded}
                  onClear={handleClear}
                  activeDocumentId={documentId}
                  resetSignal={resetSignal}
                />
              </aside>
            </section>
          ) : null}

          {view === "indexing" ? (
            <div className="main-stage">
              {transitionMode === "loading" ? (
                <div className="skeleton-screen">
                  <header className="skeleton-header">
                    <div className="skeleton-title" />
                  </header>
                  <div className="skeleton-messages">
                    <div className="skeleton-bubble user" />
                    <div className="skeleton-bubble assistant" />
                    <div className="skeleton-bubble user" style={{ width: "30%" }} />
                    <div className="skeleton-bubble assistant" style={{ width: "60%" }} />
                  </div>
                  <footer className="skeleton-footer">
                    <div className="skeleton-input" />
                  </footer>
                </div>
              ) : (
                <div className="transition-stage">
                  <div className="transition-card">
                    <div className="status-pill">Indexing document</div>
                    <h2 className="brand-name">{documentMeta?.fileName}</h2>
                    <p className="text-label" style={{ marginTop: "12px" }}>
                      Analyzing and preparing your document for chat.
                    </p>
                    <div style={{ marginTop: "24px", display: "flex", justifyContent: "center" }}>
                      <div className="loader" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : view === "chat" ? (
            <section className="chat-stage">
              <section className="panel-chat" id="chat" aria-label="Chat workspace">
                <div className="panel-head">
                  <div>
                    {documentMeta ? <h2 className="panel-title-file">{documentMeta.fileName}</h2> : null}
                  </div>
                </div>

                <ChatWindow messages={messages} isAssistantTyping={isAssistantTyping} />

                {error ? <p style={{ color: "var(--color-error)", padding: "0 24px" }}>{error}</p> : null}

                <ChatInput disabled={!documentId || !conversationId} onSend={handleSend} />
              </section>
            </section>
          ) : null}
        </section>
      </main>

      {isSearchOpen && (
        <div className={`modal-overlay ${isSearchClosing ? "closing" : ""}`} onClick={closeSearch}>
          <div className={`modal-content ${isSearchClosing ? "closing" : ""}`} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="sidebar-action-icon"><MagnifyIcon /></div>
              <input
                type="text"
                autoFocus
                placeholder="Search chats and projects"
                className="modal-search-input"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
              />
            </div>
            <div className="modal-body">
              {filteredDocuments.length > 0 ? (
                filteredDocuments.map((doc) => (
                  <button
                    key={doc.id}
                    className="modal-doc-item"
                    onClick={() => void handleSelectDocument(doc)}
                  >
                    <FileIcon />
                    <div className="modal-doc-info">
                      <span className="modal-doc-name">{doc.filename}</span>
                      <span className="modal-doc-date">
                        {doc.uploaded_at ? new Date(doc.uploaded_at).toLocaleDateString() : "Unknown date"}
                      </span>
                    </div>
                  </button>
                ))
              ) : (
                <p className="text-label" style={{ padding: "20px", textAlign: "center" }}>
                  {documents.length === 0 ? "No documents found." : "No matches found."}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {documentToDelete && (
        <div className="modal-overlay" onClick={() => !isDeletingDocument && setDocumentToDelete(null)}>
          <div className="modal-content delete-modal" onClick={(event) => event.stopPropagation()}>
            <div className="delete-modal-body">
              <h3 className="delete-modal-title">Delete document?</h3>
              <p className="delete-modal-text">
                This will permanently remove <strong>{documentToDelete.filename}</strong> and its chat history.
              </p>
            </div>
            <div className="delete-modal-actions">
              <button
                type="button"
                className="btn-ghost delete-modal-cancel"
                onClick={() => setDocumentToDelete(null)}
                disabled={isDeletingDocument}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn-brand delete-modal-confirm"
                onClick={() => void handleDeleteDocument()}
                disabled={isDeletingDocument}
              >
                {isDeletingDocument ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
