import React, { useEffect, useRef, useState } from "react";
import type { ChatMessage as ChatMessageType } from "../types";
import { ChatMessage } from "./ChatMessage";

interface ChatPaneProps {
  messages: ChatMessageType[];
  currentResponse: string;
  isConnected: boolean;
  onSendMessage: (message: string) => void;
}

/**
 * Left pane of the split-pane layout containing the chat interface.
 *
 * Displays a header with connection status, a scrollable message list
 * (with auto-scroll to bottom), the current streaming response as a
 * typing indicator, and an input field with send button.
 *
 * Args:
 *   messages: Array of completed chat messages.
 *   currentResponse: Accumulated streaming tokens for the in-progress response.
 *   isConnected: Whether the WebSocket is currently connected.
 *   onSendMessage: Callback to send a new user message.
 */
export const ChatPane: React.FC<ChatPaneProps> = ({
  messages,
  currentResponse,
  isConnected,
  onSendMessage,
}) => {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Reason: Auto-scroll to the bottom whenever messages change or
  // new streaming tokens arrive, so the user always sees the latest content.
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, currentResponse]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed) return;
    onSendMessage(trimmed);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-pane">
      <div className="chat-header">
        <div>
          <img src="/logo.svg" alt="Sentinel" className="header-logo" />
          <h1 className="chat-title">AI Assistant</h1>
        </div>
        <div className="connection-status">
          <span
            className={`status-dot ${isConnected ? "connected" : "disconnected"}`}
          />
          <span className="status-text">
            {isConnected ? "Connected" : "Disconnected"}
          </span>
        </div>
      </div>

      <div className="messages-container">
        {messages.map((msg, i) => (
          <ChatMessage key={i} message={msg} />
        ))}
        {currentResponse && (
          <div className="chat-message assistant">
            <div className="message-bubble typing">
              {currentResponse.split("\n").map((line, i) => (
                <p key={i} className="message-line">
                  {line || "\u00A0"}
                </p>
              ))}
              <span className="typing-cursor" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <input
          type="text"
          className="chat-input"
          placeholder="Ask DevBot something..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={!isConnected}
        />
        <button
          className="send-button"
          onClick={handleSend}
          disabled={!isConnected || !input.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
};
