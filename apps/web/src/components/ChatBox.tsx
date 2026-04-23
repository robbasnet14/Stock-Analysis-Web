import { FormEvent, useState } from "react";
import { ChatMessage } from "../types/api";

interface ChatBoxProps {
  messages: ChatMessage[];
  onSend: (message: string) => Promise<void>;
  loading: boolean;
}

export function ChatBox({ messages, onSend, loading }: ChatBoxProps) {
  const [text, setText] = useState("");

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim() || loading) return;
    const value = text.trim();
    setText("");
    await onSend(value);
  }

  return (
    <section className="panel chat-panel">
      <div className="panel-head">
        <h2>Quant Chat</h2>
        <span>Ask: what to expect, entries, catalysts, risk</span>
      </div>
      <div className="chat-log">
        {messages.map((msg, index) => (
          <article key={`${msg.role}-${index}`} className={`chat-msg ${msg.role}`}>
            <p className="chat-role">{msg.role}</p>
            <p>{msg.content}</p>
          </article>
        ))}
      </div>
      <form className="chat-form" onSubmit={submit}>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask about a ticker setup..." />
        <button type="submit" disabled={loading}>
          {loading ? "Thinking..." : "Send"}
        </button>
      </form>
    </section>
  );
}
