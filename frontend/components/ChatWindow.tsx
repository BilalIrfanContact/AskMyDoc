import MessageBubble from "./MessageBubble";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ChatWindowProps = {
  messages: Message[];
};

export default function ChatWindow({ messages }: ChatWindowProps) {
  return (
    <div className="chat-window" role="log" aria-live="polite">
      {messages.length === 0 ? (
        <div className="chat-empty">
          <p className="empty-title">
            Start the conversation
          </p>
          <p className="text-olive">
            Ask specific questions about your uploaded PDF.
          </p>
        </div>
      ) : (
        messages.map((message, index) => (
          <MessageBubble key={`${message.role}-${index}`} role={message.role} content={message.content} />
        ))
      )}
    </div>
  );
}
