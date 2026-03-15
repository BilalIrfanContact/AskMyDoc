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
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = window.localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const initial = stored ? (stored === "dark" ? "dark" : "light") : prefersDark ? "dark" : "light";
    setTheme(initial);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    window.localStorage.setItem("theme", theme);
  }, [theme]);

  const handleUploaded = (
    id: string,
    meta: { fileName: string; fileSize: string; chunkCount: number; storedCount: number }
  ) => {
    setDocumentId(id);
    setDocumentMeta(meta);
    setMessages([]);
    setError(null);
  };

  const handleClear = () => {
    setDocumentId(null);
    setDocumentMeta(null);
    setMessages([]);
    setError(null);
    setResetSignal((value) => value + 1);
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
    <main className="mx-auto flex min-h-screen max-w-6xl flex-col gap-10 px-6 py-12">
      <header className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="inline-flex items-center gap-2 rounded-full bg-white/80 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-ink/70 dark:bg-white/10 dark:text-mist/70">
            AskMyDoc
          </div>
          <button
            type="button"
            onClick={() => setTheme((prev) => (prev === "dark" ? "light" : "dark"))}
            className="rounded-full border border-ink/15 bg-white/80 px-4 py-2 text-xs font-semibold text-ink transition hover:border-ink/30 dark:border-mist/30 dark:bg-white/10 dark:text-mist"
          >
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
        </div>
        <h1 className="font-[var(--font-fraunces)] text-4xl text-ink md:text-5xl dark:text-mist">
          AskMyDoc
        </h1>
        <p className="max-w-2xl text-base text-ink/70 md:text-lg dark:text-mist/70">
          Upload any PDF and ask questions. The assistant answers only from the document using retrieval-augmented generation.
        </p>
      </header>

      <section className="grid gap-8 lg:grid-cols-[1fr_1.3fr]">
        <PDFUploader
          onUploaded={handleUploaded}
          onClear={handleClear}
          activeDocumentId={documentId}
          resetSignal={resetSignal}
        />
        <div className="flex flex-col gap-4">
          <ChatWindow messages={messages} />
          {error ? (
            <div className="rounded-2xl border border-coral/40 bg-white/80 px-4 py-3 text-sm text-coral dark:bg-white/10">
              {error}
            </div>
          ) : null}
          {documentMeta ? (
            <div className="rounded-2xl border border-ink/10 bg-white/70 px-4 py-3 text-xs text-ink/70 dark:border-white/10 dark:bg-white/10 dark:text-mist/70">
              <span className="font-semibold text-ink dark:text-mist">Active document:</span>{" "}
              {documentMeta.fileName} • {documentMeta.fileSize}
            </div>
          ) : null}
          <ChatInput disabled={!documentId} onSend={handleSend} />
        </div>
      </section>
    </main>
  );
}
