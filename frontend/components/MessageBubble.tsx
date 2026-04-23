type MessageBubbleProps = {
  role: "user" | "assistant";
  content: string;
  isTyping?: boolean;
};

export default function MessageBubble({ role, content, isTyping = false }: MessageBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row-user" : "message-row-assistant"}`}>
      <div className={`message-bubble ${isUser ? "message-user" : "message-assistant"}`}>
        {isTyping ? (
          <div className="typing-indicator" aria-label="Assistant is typing">
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        ) : (
          content
        )}
      </div>
    </div>
  );
}
