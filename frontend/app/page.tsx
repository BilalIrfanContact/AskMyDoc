"use client";

import { useState } from "react";

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);

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
        <span className="inline-flex w-fit items-center rounded-full bg-white/80 px-4 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-ink/70">
          Portfolio Project
        </span>
        <h1 className="font-[var(--font-fraunces)] text-4xl text-ink md:text-5xl">
          PDF AI Chatbot
        </h1>
        <p className="max-w-2xl text-base text-ink/70 md:text-lg">
          Upload any PDF and ask questions. The assistant answers only from the document using retrieval-augmented generation.
        </p>
      </header>

      <section className="grid gap-8 lg:grid-cols-[1fr_1.3fr]">
        <PDFUploader onUploaded={(id) => setDocumentId(id)} />
        <div className="flex flex-col gap-4">
          <ChatWindow messages={messages} />
          {error ? (
            <div className="rounded-2xl border border-coral/40 bg-white/80 px-4 py-3 text-sm text-coral">
              {error}
            </div>
          ) : null}
          <ChatInput disabled={!documentId} onSend={handleSend} />
        </div>
      </section>
    </main>
  );
}
