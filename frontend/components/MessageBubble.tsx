type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
};

export default function MessageBubble({ role, content }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm md:text-base ${
          isUser
            ? "bg-ink text-white dark:bg-mist/10 dark:text-mist"
            : "bg-white/90 text-ink border border-ink/10 dark:bg-white/10 dark:text-mist dark:border-white/10"
        }`}
      >
        {content}
      </div>
    </div>
  );
}
