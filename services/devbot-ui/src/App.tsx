import { useCallback, useState } from "react";
import type {
  AgentState,
  ChatMessage,
  NetworkEntry,
  TerminalEntry,
  ToolLogEntry,
  WSMessage,
} from "./types";
import { useWebSocket } from "./hooks/useWebSocket";
import { ChatPane } from "./components/ChatPane";
import { ActivityPanel } from "./components/ActivityPanel";
import type { ActiveTab } from "./components/ActivityPanel";

/**
 * Root application component for the DevBot chat UI.
 *
 * Manages all application state and dispatches incoming WebSocket messages
 * to the appropriate state updaters. Renders a CSS Grid split-pane layout
 * with the chat pane (60%) on the left and the activity panel (40%) on the
 * right. The root div carries a CSS class based on the current agent state
 * to drive color transitions during the demo.
 */
function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [toolLog, setToolLog] = useState<ToolLogEntry[]>([]);
  const [terminalEntries, setTerminalEntries] = useState<TerminalEntry[]>([]);
  const [networkEntries, setNetworkEntries] = useState<NetworkEntry[]>([]);
  const [agentState, setAgentState] = useState<AgentState>("normal");
  const [currentResponse, setCurrentResponse] = useState("");
  const [activeTab, setActiveTab] = useState<ActiveTab>("tools");

  /**
   * Dispatches incoming WebSocket messages to the correct state handler.
   *
   * Message types and their actions:
   * - chat_token: Append token to the streaming response accumulator.
   * - chat_complete: Commit the accumulated response as a completed message.
   * - tool_start: Add a new pending entry to the tool log.
   * - tool_result: Update the most recent tool log entry with its result.
   * - terminal_output: Append a new entry to the terminal display.
   * - network_event: Append a new entry to the network traffic log.
   * - state_change: Transition the visual state (normal/compromised/blocked).
   * - error: Display the error as an assistant message.
   */
  const handleMessage = useCallback((msg: WSMessage) => {
    const { type, data } = msg;

    switch (type) {
      case "chat_token":
        setCurrentResponse((prev) => prev + (data.token as string));
        break;

      case "chat_complete":
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: (data.content as string) || "",
            timestamp: new Date().toISOString(),
          },
        ]);
        setCurrentResponse("");
        break;

      case "tool_start":
        setToolLog((prev) => [
          ...prev,
          {
            tool: data.tool as string,
            args: (data.args as Record<string, unknown>) || {},
            result: "",
            status: "success",
            timestamp: new Date().toISOString(),
          },
        ]);
        break;

      case "tool_result":
        setToolLog((prev) => {
          const updated = [...prev];
          if (updated.length > 0) {
            const last = { ...updated[updated.length - 1] };
            last.result = (data.result as string) || "";
            last.status =
              (data.status as ToolLogEntry["status"]) || "success";
            updated[updated.length - 1] = last;
          }
          return updated;
        });
        break;

      case "terminal_output":
        setTerminalEntries((prev) => [
          ...prev,
          {
            command: (data.command as string) || "",
            output: (data.output as string) || "",
            timestamp: new Date().toISOString(),
          },
        ]);
        break;

      case "network_event":
        setNetworkEntries((prev) => [
          ...prev,
          {
            tool: (data.tool as string) || "",
            target: (data.target as string) || "",
            status:
              (data.status as NetworkEntry["status"]) || "success",
            timestamp: new Date().toISOString(),
          },
        ]);
        break;

      case "state_change":
        setAgentState((data.state as AgentState) || "normal");
        break;

      case "error":
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `Error: ${(data.message as string) || "Unknown error"}`,
            timestamp: new Date().toISOString(),
          },
        ]);
        break;
    }
  }, []);

  const { sendMessage, isConnected } = useWebSocket(handleMessage);

  /**
   * Handles sending a user message: adds it to the messages array
   * and forwards it to the backend via WebSocket.
   */
  const handleSendMessage = useCallback(
    (message: string) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "user",
          content: message,
          timestamp: new Date().toISOString(),
        },
      ]);
      sendMessage(message);
    },
    [sendMessage],
  );

  return (
    <div className={`app state-${agentState}`}>
      <ChatPane
        messages={messages}
        currentResponse={currentResponse}
        isConnected={isConnected}
        onSendMessage={handleSendMessage}
      />
      <ActivityPanel
        activeTab={activeTab}
        onTabChange={setActiveTab}
        toolLog={toolLog}
        terminalEntries={terminalEntries}
        networkEntries={networkEntries}
      />
    </div>
  );
}

export default App;
