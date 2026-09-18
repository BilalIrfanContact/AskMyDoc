import { FormEvent, useEffect, useRef, useState } from "react";

type ChatInputProps = {
  disabled: boolean;
  onSend: (question: string) => Promise<void>;
  documentName?: string;
};

export default function ChatInput({ disabled, onSend, documentName }: ChatInputProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "0px";
    const lineHeight = 24;
    const maxHeight = lineHeight * 4 + 24;
    const nextHeight = Math.min(textarea.scrollHeight, maxHeight);

    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [question]);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed || loading || disabled) return;

    setLoading(true);
    setQuestion("");
    try {
      await onSend(trimmed);
    } finally {
      setLoading(false);
    }
  };

  const SendIcon = () => (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="m4 4 17 8-17 8 4-8z" />
      <path d="M8 12h13" />
    </svg>
  );

  return (
    <form onSubmit={handleSubmit} className="chat-form">
      <div className="chat-composer">
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={disabled ? "Document workspace is not ready." : `Ask about ${documentName ?? "this document"}`}
          className="chat-textarea"
          disabled={disabled}
          rows={1}
          aria-label="Ask about this document"
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void handleSubmit(event as unknown as FormEvent);
            }
          }}
        />
        <button type="submit" disabled={disabled || loading || !question.trim()} className="chat-send-btn" aria-label="Send question">
          <SendIcon />
        </button>
      </div>
    </form>
  );
}
