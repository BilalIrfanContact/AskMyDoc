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
    if (!question.trim() || loading || disabled) return;

    setLoading(true);
    try {
      await onSend(question.trim());
      setQuestion("");
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
        className="min-h-[100px] w-full resize-none rounded-2xl border border-ink/10 bg-white/90 p-4 text-sm text-ink shadow-sm focus:border-tide focus:outline-none"
        disabled={disabled}
      />
      <button
        type="submit"
        disabled={disabled || loading}
        className="self-end rounded-full bg-tide px-5 py-2 text-sm font-semibold text-white transition hover:bg-ink disabled:cursor-not-allowed disabled:bg-ink/40"
      >
        {loading ? "Thinking..." : "Send"}
      </button>
    </form>
  );
}
