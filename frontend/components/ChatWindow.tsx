import { useEffect, useRef, useState } from "react";

import type { Message } from "./home/types";

type ChatWindowProps = {
  messages: Message[];
  isAssistantTyping?: boolean;
  documentName: string;
  suggestedQuestions: string[];
  loadingSuggestions: boolean;
  onSuggestion: (question: string) => Promise<void>;
};

export default function ChatWindow({
  messages,
  isAssistantTyping = false,
  documentName,
  suggestedQuestions,
  loadingSuggestions,
  onSuggestion
}: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const [sourceMessageIndex, setSourceMessageIndex] = useState<number | null>(null);
  const [copiedMessageIndex, setCopiedMessageIndex] = useState<number | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isAssistantTyping]);

  useEffect(() => {
    setSourceMessageIndex(null);
  }, [documentName]);

  useEffect(() => {
    if (
      sourceMessageIndex !== null &&
      !messages[sourceMessageIndex]?.citations?.length
    ) {
      setSourceMessageIndex(null);
    }
  }, [messages, sourceMessageIndex]);

  const sourceMessage = sourceMessageIndex === null ? null : messages[sourceMessageIndex];

  return (
    <div className={`chat-layout ${sourceMessage?.citations?.length ? "has-sources" : ""}`}>
      <div className="chat-window" role="log" aria-live="polite" aria-label={`Conversation about ${documentName}`}>
        {messages.length === 0 ? (
          <div className="chat-empty">
            <h2>What do you need to know?</h2>
            <p>Ask a specific question. Answers will stay within this document.</p>
            {loadingSuggestions ? (
              <div className="suggestion-skeleton" aria-label="Finding questions in this document" role="status">
                <span /><span /><span />
              </div>
            ) : suggestedQuestions.length ? (
              <div className="chat-suggestions" aria-label="Questions suggested from this document">
                {suggestedQuestions.map((question) => (
                  <button type="button" key={question} onClick={() => void onSuggestion(question)}>
                    <SearchIcon />
                    <span>{question}</span>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="conversation-list">
            {messages.map((message, index) => (
              message.role === "user" ? (
                <div className="user-message" key={`message-${index}`}>
                  <p>{message.content}</p>
                </div>
              ) : message.answerStatus === "insufficient_context" ? (
                <p className="insufficient-message" role="status" key={`message-${index}`}>
                  {message.content}
                </p>
              ) : (
                <article className="assistant-answer" key={`message-${index}`}>
                  <p className="answer-copy">{message.content}</p>
                  {message.citations?.length ? (
                    <p className="answer-status">Grounded in {message.citations.length} {message.citations.length === 1 ? "passage" : "passages"}</p>
                  ) : null}
                  <div className="answer-actions">
                    <button type="button" onClick={async () => {
                      await navigator.clipboard.writeText(message.content);
                      setCopiedMessageIndex(index);
                      window.setTimeout(() => setCopiedMessageIndex(null), 1500);
                    }}>
                      <CopyIcon />
                      {copiedMessageIndex === index ? "Copied" : "Copy"}
                    </button>
                    {message.citations?.length ? (
                      <button type="button" onClick={() => setSourceMessageIndex(sourceMessageIndex === index ? null : index)} aria-expanded={sourceMessageIndex === index}>
                        <SourcesIcon />
                        {sourceMessageIndex === index ? "Hide sources" : "Show sources"}
                      </button>
                    ) : null}
                  </div>
                </article>
              )
            ))}
            {isAssistantTyping ? (
              <div className="assistant-working" role="status">
                <span className="typing-indicator" aria-hidden="true"><i /><i /><i /></span>
                <span>AskMyDoc is checking the document.</span>
              </div>
            ) : null}
            <div ref={bottomRef} className="chat-scroll-anchor" aria-hidden="true" />
          </div>
        )}
      </div>

      {sourceMessage?.citations?.length ? (
        <aside className="sources-panel" aria-label="Answer sources">
          <header>
            <h2>Sources</h2>
            <button type="button" onClick={() => setSourceMessageIndex(null)} aria-label="Close sources">×</button>
          </header>
          <div className="sources-list">
            {sourceMessage.citations.map((citation, index) => (
              <article className="source-item" key={`${citation.chunk_id}-${index}`}>
                <div className="source-meta">
                  <span>{index + 1}</span>
                  <code>Passage {citation.chunk_id}</code>
                </div>
                <blockquote>{citation.excerpt}</blockquote>
              </article>
            ))}
          </div>
        </aside>
      ) : null}
    </div>
  );
}

function SearchIcon() {
  return <svg width="25" height="25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>;
}

function CopyIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><rect x="8" y="8" width="11" height="12" rx="1" /><path d="M16 8V4H5v12h3" /></svg>;
}

function SourcesIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M8 6h12M8 12h12M8 18h12" /><circle cx="4" cy="6" r="1" fill="currentColor" /><circle cx="4" cy="12" r="1" fill="currentColor" /><circle cx="4" cy="18" r="1" fill="currentColor" /></svg>;
}
