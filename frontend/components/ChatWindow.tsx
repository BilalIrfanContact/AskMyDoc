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
    <div className="chat-scrollbar flex h-[420px] flex-col gap-4 overflow-y-auto rounded-3xl bg-white/70 p-6 shadow-glow dark:bg-white/10 dark:shadow-glowDark">
      {messages.length === 0 ? (
        <div className="flex h-full flex-col items-center justify-center text-center text-sm text-ink/60 dark:text-mist/70">
          <p className="font-[var(--font-fraunces)] text-2xl text-ink dark:text-mist">Start the conversation</p>
          <p className="mt-2 max-w-xs">
            Ask anything about your PDF after uploading it. The assistant will only answer from the document.
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
