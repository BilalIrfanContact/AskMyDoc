import ChatInput from "../ChatInput";
import ChatWindow from "../ChatWindow";
import PDFUploader from "../PDFUploader";
import type { DocumentMeta, Message, TransitionMode, ViewState } from "./types";

type HomeWorkspaceProps = {
  userId: string;
  greeting: string;
  view: ViewState;
  transitionMode: TransitionMode;
  documentId: string | null;
  conversationId: string | null;
  documentMeta: DocumentMeta | null;
  messages: Message[];
  error: string | null;
  resetSignal: number;
  isAssistantTyping: boolean;
  onUploaded: (
    documentId: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => Promise<void>;
  onClear: () => void;
  onSend: (question: string) => Promise<void>;
};

export default function HomeWorkspace({
  userId,
  greeting,
  view,
  transitionMode,
  documentId,
  conversationId,
  documentMeta,
  messages,
  error,
  resetSignal,
  isAssistantTyping,
  onUploaded,
  onClear,
  onSend
}: HomeWorkspaceProps) {
  return (
    <main className="main-stage">
      <header className="topbar" />

      <section className="shell-grid" id="workspace">
        {view === "upload" ? (
          <section className="upload-stage">
            <div className="hero-lockup">
              <img src="/logo.png" alt="AskMyDoc icon" width={44} height={44} className="hero-icon" />
              <h1 className="hero-title hero-title-home">{greeting}</h1>
            </div>

            <aside className="panel-upload card-ivory">
              <PDFUploader
                onUploaded={onUploaded}
                onClear={onClear}
                activeDocumentId={documentId}
                resetSignal={resetSignal}
                userId={userId}
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
        ) : null}

        {view === "chat" ? (
          <section className="chat-stage">
            <section className="panel-chat" id="chat" aria-label="Chat workspace">
              <div className="panel-head">
                <div>
                  {documentMeta ? <h2 className="panel-title-file">{documentMeta.fileName}</h2> : null}
                </div>
              </div>

              <ChatWindow messages={messages} isAssistantTyping={isAssistantTyping} />

              {error ? <p style={{ color: "var(--color-error)", padding: "0 24px" }}>{error}</p> : null}

              <ChatInput disabled={!documentId || !conversationId} onSend={onSend} />
            </section>
          </section>
        ) : null}
      </section>
    </main>
  );
}
