import { FormEvent, useEffect, useRef, useState } from "react";

type ChatInputProps = {
  disabled: boolean;
  onSend: (question: string) => Promise<void>;
};

export default function ChatInput({ disabled, onSend }: ChatInputProps) {
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

  return (
    <form onSubmit={handleSubmit} className="chat-form">
      <textarea
        ref={textareaRef}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder={disabled ? "Upload a PDF to start asking questions." : "Ask about the document..."}
        className="chat-textarea"
        disabled={disabled}
        rows={1}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            void handleSubmit(event as unknown as FormEvent);
          }
        }}
      />
      <button type="submit" disabled={disabled || loading} className="btn-brand chat-send">
        {loading ? "Thinking..." : "Send"}
      </button>
    </form>
  );
}
