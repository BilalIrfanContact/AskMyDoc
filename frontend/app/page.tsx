"use client";

import { useEffect, useState } from "react";

import ChatInput from "../components/ChatInput";
import ChatWindow from "../components/ChatWindow";
import PDFUploader from "../components/PDFUploader";
import { askQuestion } from "../lib/api";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ViewState = "upload" | "indexing" | "chat";

export default function Home() {
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [documentMeta, setDocumentMeta] = useState<{
    fileName: string;
    fileSize: string;
    chunkCount: number;
    storedCount: number;
  } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resetSignal, setResetSignal] = useState(0);
  const [view, setView] = useState<ViewState>("upload");

  useEffect(() => {
    if (view !== "indexing") return;

    const timer = window.setTimeout(() => {
      setView("chat");
    }, 1400);

    return () => window.clearTimeout(timer);
  }, [view]);

  const handleUploaded = (
    id: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => {
    setDocumentId(id);
    setDocumentMeta(meta);
    setMessages([]);
    setError(null);
    setView("indexing");
  };

  const handleClear = () => {
    setDocumentId(null);
    setDocumentMeta(null);
    setMessages([]);
    setError(null);
    setResetSignal((value) => value + 1);
    setView("upload");
  };

  const handleSend = async (question: string) => {
    if (!documentId) return;

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setError(null);

    try {
      const response = await askQuestion(documentId, question);
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
          <span className="brand-name">AskMyDoc</span>
        </a>

        <button type="button" className="btn-ghost" onClick={handleClear} disabled={view === "upload"}>
          New document
        </button>
      </header>

      <main className="shell-grid" id="workspace">
        {view === "upload" ? (
          <section className="upload-stage">
            <h1 className="hero-title">Ask your PDF.</h1>

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

        {view === "indexing" && documentMeta ? (
          <section className="transition-stage">
            <div className="card-ivory transition-card" aria-live="polite">
              <span className="badge">Indexing document</span>
              <h2 className="transition-title">{documentMeta.fileName}</h2>
              <p className="text-olive">
                Building the retrieval index and preparing the chat workspace.
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
                  {documentMeta ? (
                    <h2 className="panel-title-file">
                      {documentMeta.fileName}
                    </h2>
                  ) : null}
                </div>
              </div>

              <ChatWindow messages={messages} />

              {error ? <p style={{color: "var(--color-error)", padding: "0 24px"}}>{error}</p> : null}

              <ChatInput disabled={!documentId} onSend={handleSend} />
            </section>
          </section>
        ) : null}
      </main>
    </div>
  );
}
