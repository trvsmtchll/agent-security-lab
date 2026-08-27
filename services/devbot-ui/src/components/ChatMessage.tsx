import React from "react";
import type { ChatMessage as ChatMessageType } from "../types";

interface ChatMessageProps {
  message: ChatMessageType;
}

/**
 * Renders a single chat message bubble.
 *
 * User messages are right-aligned with a blue background.
 * Assistant messages are left-aligned with a darker background.
 * Content containing "BLOCKED" shows an inline red badge.
 * Newlines in content are rendered as separate paragraphs.
 *
 * Args:
 *   message: The ChatMessage object to display.
 */
export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.role === "user";
  const isBlocked = message.content.includes("BLOCKED");

  // Reason: Format the ISO timestamp into a short HH:MM display
  // for a cleaner look in the chat bubble.
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  const lines = message.content.split("\n");

  return (
    <div className={`chat-message ${isUser ? "user" : "assistant"}`}>
      <div className="message-bubble">
        {lines.map((line, i) => (
          <p key={i} className="message-line">
            {line || "\u00A0"}
          </p>
        ))}
        {isBlocked && <span className="badge badge-blocked">BLOCKED</span>}
      </div>
      <span className="message-time">{time}</span>
    </div>
  );
};
