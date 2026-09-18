import type { PersistedDocument } from "../../lib/api";
import ChatInput from "../ChatInput";
import ChatWindow from "../ChatWindow";
import PDFUploader from "../PDFUploader";
import { FileIcon, MagnifyIcon, TrashIcon } from "./HomeIcons";
import type { DocumentMeta, Message, TransitionMode, UploadBootstrapResult, ViewState } from "./types";

type HomeWorkspaceProps = {
  greeting: string;
  userInitials: string;
  isMobileNavOpen: boolean;
  documents: PersistedDocument[];
  loadingDocuments: boolean;
  busyDocumentId: string | null;
  view: ViewState;
  transitionMode: TransitionMode;
  documentId: string | null;
  conversationId: string | null;
  documentMeta: DocumentMeta | null;
  messages: Message[];
  error: string | null;
  resetSignal: number;
  isAssistantTyping: boolean;
  onOpenMobileNav: () => void;
  onOpenSearch: () => void;
  onRetryDocuments: () => void;
  onSelectDocument: (document: PersistedDocument) => void;
  onDeleteDocument: (document: PersistedDocument) => void;
  onUploaded: (
    documentId: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => Promise<UploadBootstrapResult>;
  onClear: () => void;
  onSend: (question: string) => Promise<void>;
};

export default function HomeWorkspace({
  greeting,
  userInitials,
  isMobileNavOpen,
  documents,
  loadingDocuments,
  busyDocumentId,
  view,
  transitionMode,
  documentId,
  conversationId,
  documentMeta,
  messages,
  error,
  resetSignal,
  isAssistantTyping,
  onOpenMobileNav,
  onOpenSearch,
  onRetryDocuments,
  onSelectDocument,
  onDeleteDocument,
  onUploaded,
  onClear,
  onSend
}: HomeWorkspaceProps) {
  return (
    <main className="main-stage" inert={isMobileNavOpen ? true : undefined}>
      <header className="mobile-appbar">
        <button type="button" className="mobile-menu-button" onClick={onOpenMobileNav} aria-label="Open document navigation">
          <span aria-hidden="true" />
          <span aria-hidden="true" />
          <span aria-hidden="true" />
        </button>
        <span className="mobile-wordmark">AskMyDoc</span>
        <span className="mobile-avatar" aria-label="Account">{userInitials}</span>
      </header>

      {view === "upload" ? (
        <section className="library-page" id="workspace">
          <header className="library-intro">
            <h1>{normalizeGreeting(greeting)}</h1>
            <p>Choose a document, then ask only what the source can support.</p>
          </header>

          {error ? (
            <div className="notice notice-error" role="alert">
              <div>
                <strong>We could not finish that request.</strong>
                <p>{error}</p>
              </div>
              <button type="button" className="button-secondary button-small" onClick={onRetryDocuments}>Retry</button>
            </div>
          ) : null}

          <div className="library-layout">
            <section className="document-library" aria-labelledby="recent-documents-heading">
              <div className="section-heading-row">
                <h2 id="recent-documents-heading">Recent documents</h2>
                <button type="button" className="text-action" onClick={onOpenSearch}>View all</button>
              </div>

              <div className="document-list">
                {loadingDocuments ? <DocumentListSkeleton /> : null}
                {!loadingDocuments && documents.length === 0 ? (
                  <div className="document-empty">
                    <h3>Your library is empty</h3>
                    <p>Add a PDF or Markdown file to start asking questions.</p>
                  </div>
                ) : null}
                {documents.slice(0, 5).map((document) => (
                  <article className="document-row" key={document.id}>
                    <button
                      type="button"
                      className="document-open"
                      onClick={() => onSelectDocument(document)}
                      disabled={busyDocumentId === document.id}
                    >
                      <span className={`document-file-icon ${isPdf(document.filename) ? "is-pdf" : ""}`}>
                        <FileIcon />
                      </span>
                      <span className="document-row-copy">
                        <strong>{document.filename}</strong>
                        <span>{formatUploadedDate(document.uploaded_at)}</span>
                      </span>
                      <span className="document-row-date">{busyDocumentId === document.id ? "Opening…" : formatShortDate(document.uploaded_at)}</span>
                    </button>
                    <button
                      type="button"
                      className="document-delete"
                      onClick={() => onDeleteDocument(document)}
                      aria-label={`Delete ${document.filename}`}
                    >
                      <TrashIcon />
                    </button>
                  </article>
                ))}
              </div>

              <section className="question-examples" aria-labelledby="question-examples-heading">
                <h2 id="question-examples-heading">What you can ask</h2>
                <div className="question-example"><FileIcon /><span>Summarize the key decisions</span></div>
                <div className="question-example"><MagnifyIcon /><span>Find the termination clause</span></div>
                <div className="question-example"><MessageIcon /><span>Explain this section in plain language</span></div>
              </section>
            </section>

            <aside className="upload-panel" aria-labelledby="upload-heading">
              <div className="upload-panel-heading">
                <h2 id="upload-heading">Add a document</h2>
                <p>PDF or Markdown</p>
              </div>
              <PDFUploader
                onUploaded={onUploaded}
                onClear={onClear}
                activeDocumentId={documentId}
                resetSignal={resetSignal}
              />
            </aside>
          </div>
        </section>
      ) : null}

      {view === "indexing" ? (
        <section className="processing-page" aria-live="polite">
          <div className="processing-content">
            <h1>{transitionMode === "loading" ? "Opening your document" : "Preparing your document"}</h1>
            <div className="processing-file">
              <span className={`document-file-icon ${isPdf(documentMeta?.fileName ?? "") ? "is-pdf" : ""}`}><FileIcon /></span>
              <div>
                <h2>{documentMeta?.fileName}</h2>
                <p>{documentMeta?.fileSize ? `${documentMeta.fileSize} · ` : ""}{isPdf(documentMeta?.fileName ?? "") ? "PDF" : "Markdown"}</p>
              </div>
            </div>
            <div className="processing-rule" />
            <div className="processing-status">
              <LoadingMark />
              <h2>{transitionMode === "loading" ? "Restoring conversation" : "Indexing document"}</h2>
              <p>{transitionMode === "loading" ? "Loading your document and previous messages." : "Reading the file and building a searchable index. This can take a moment."}</p>
            </div>
            <button type="button" className="button-secondary processing-cancel" onClick={onClear}>Cancel</button>
            <p className="processing-helper">Cancelling returns to the library.</p>
          </div>
          <WorkspaceSkeleton />
        </section>
      ) : null}

      {view === "chat" ? (
        <section className="document-workspace" id="chat" aria-label="Document conversation">
          <header className="document-header">
            <span className={`document-file-icon ${isPdf(documentMeta?.fileName ?? "") ? "is-pdf" : ""}`}><FileIcon /></span>
            <div className="document-header-copy">
              <h1>{documentMeta?.fileName}</h1>
              <p>{documentMeta?.uploadedAt ? formatUploadedDate(documentMeta.uploadedAt) : "Document ready"}</p>
            </div>
            <button type="button" className="document-options" aria-label="Document options" onClick={() => {
              const document = documents.find((item) => item.id === documentId);
              if (document) onDeleteDocument(document);
            }}>
              <span aria-hidden="true">•••</span>
              <span>Document options</span>
            </button>
          </header>

          <div className="conversation-shell">
            <ChatWindow
              messages={messages}
              isAssistantTyping={isAssistantTyping}
              documentName={documentMeta?.fileName ?? "this document"}
              onSuggestion={onSend}
            />

            {error ? <div className="chat-error" role="alert">{error}</div> : null}

            <ChatInput disabled={!documentId || !conversationId} onSend={onSend} documentName={documentMeta?.fileName} />
          </div>
        </section>
      ) : null}
    </main>
  );
}

function DocumentListSkeleton() {
  return <div className="document-list-skeleton" aria-label="Loading documents">{[0, 1, 2].map((item) => <span key={item} />)}</div>;
}

function WorkspaceSkeleton() {
  return (
    <aside className="workspace-preview" aria-hidden="true">
      <div className="workspace-preview-rail"><span /><span /><span /><span /></div>
      <div className="workspace-preview-main"><span /><span className="preview-answer" /><span /><span /><span className="preview-input" /></div>
    </aside>
  );
}

function LoadingMark() {
  return <span className="loading-mark" aria-hidden="true"><i /><i /><i /></span>;
}

function MessageIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z" />
      <path d="M8 9h8M8 13h5" />
    </svg>
  );
}

function normalizeGreeting(greeting: string) {
  const cleaned = greeting.replace(/[!?]$/, ".");
  return cleaned.endsWith(".") ? cleaned : `${cleaned}.`;
}

function isPdf(fileName: string) {
  return fileName.toLowerCase().endsWith(".pdf");
}

function formatUploadedDate(value?: string | null) {
  if (!value) return "Upload date unavailable";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "Upload date unavailable";
  const days = Math.max(0, Math.floor((Date.now() - timestamp) / 86_400_000));
  if (days === 0) return "Uploaded today";
  if (days === 1) return "Uploaded yesterday";
  if (days < 7) return `Uploaded ${days} days ago`;
  return `Uploaded ${new Date(value).toLocaleDateString()}`;
}

function formatShortDate(value?: string | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
