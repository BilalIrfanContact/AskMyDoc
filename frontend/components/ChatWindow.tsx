import { useEffect, useRef } from "react";

import MessageBubble from "./MessageBubble";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type ChatWindowProps = {
  messages: Message[];
  isAssistantTyping?: boolean;
};

export default function ChatWindow({ messages, isAssistantTyping = false }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, isAssistantTyping]);

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
        <>
          {messages.map((message, index) => (
            <MessageBubble key={`${message.role}-${index}`} role={message.role} content={message.content} />
          ))}
          {isAssistantTyping ? <MessageBubble role="assistant" content="" isTyping /> : null}
          <div ref={bottomRef} className="chat-scroll-anchor" aria-hidden="true" />
        </>
      )}
    </div>
  );
}
