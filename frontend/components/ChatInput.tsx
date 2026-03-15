import { FormEvent, useState } from "react";


type ChatInputProps = {
  disabled: boolean;
  onSend: (question: string) => Promise<void>;
};

export default function ChatInput({ disabled, onSend }: ChatInputProps) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);

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
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <textarea
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        placeholder={disabled ? "Upload a PDF to start asking questions." : "Ask something about the document..."}
        className="min-h-[100px] w-full resize-none rounded-2xl border border-ink/10 bg-white/90 p-4 text-sm text-ink shadow-sm focus:border-tide focus:outline-none dark:border-white/10 dark:bg-white/10 dark:text-mist"
        disabled={disabled}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSubmit(event as unknown as FormEvent);
          }
        }}
      />
      <button
        type="submit"
        disabled={disabled || loading}
        className="self-end rounded-full bg-tide px-5 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/40 dark:hover:bg-slate"
      >
        {loading ? "Thinking..." : "Send"}
      </button>
    </form>
  );
}
