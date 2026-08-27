export type AgentState = "normal" | "compromised" | "blocked";

export type WSMessageType =
  | "chat_token"
  | "chat_complete"
  | "tool_start"
  | "tool_result"
  | "terminal_output"
  | "network_event"
  | "state_change"
  | "error";

export interface WSMessage {
  type: WSMessageType;
  data: Record<string, unknown>;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface ToolLogEntry {
  tool: string;
  args: Record<string, unknown>;
  result: string;
  status: "success" | "error" | "blocked";
  timestamp: string;
}

export interface TerminalEntry {
  command: string;
  output: string;
  timestamp: string;
}

export interface NetworkEntry {
  tool: string;
  target: string;
  status: "success" | "error" | "blocked";
  timestamp: string;
}
