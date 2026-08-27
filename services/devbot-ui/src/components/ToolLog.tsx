import React from "react";
import type { ToolLogEntry } from "../types";

interface ToolLogProps {
  entries: ToolLogEntry[];
}

/**
 * Displays a chronological list of MCP tool invocations.
 *
 * Each entry shows the tool name, formatted JSON arguments, truncated result,
 * and a color-coded status badge (SUCCESS/BLOCKED/ERROR). Most recent entries
 * appear at the top with a slide-in animation.
 *
 * Args:
 *   entries: Array of ToolLogEntry objects from the agent.
 */
export const ToolLog: React.FC<ToolLogProps> = ({ entries }) => {
  // Reason: Reverse so newest entries appear at the top of the list.
  const sorted = [...entries].reverse();

  const statusClass = (status: ToolLogEntry["status"]) => {
    switch (status) {
      case "success":
        return "badge-success";
      case "blocked":
        return "badge-blocked";
      case "error":
        return "badge-error";
    }
  };

  const truncate = (text: string, max: number = 200): string => {
    if (text.length <= max) return text;
    return text.slice(0, max) + "...";
  };

  return (
    <div className="tool-log">
      {sorted.length === 0 && (
        <div className="empty-state">No tool invocations yet</div>
      )}
      {sorted.map((entry, i) => (
        <div key={i} className="tool-entry slide-in">
          <div className="tool-entry-header">
            <span className="tool-name">{entry.tool}</span>
            <span className={`badge ${statusClass(entry.status)}`}>
              {entry.status.toUpperCase()}
            </span>
          </div>
          <div className="tool-entry-args">
            <span className="label">Args:</span>
            <pre className="json-display">
              {JSON.stringify(entry.args, null, 2)}
            </pre>
          </div>
          {entry.result && (
            <div className="tool-entry-result">
              <span className="label">Result:</span>
              <pre className="result-display">{truncate(entry.result)}</pre>
            </div>
          )}
          <span className="tool-timestamp">
            {new Date(entry.timestamp).toLocaleTimeString()}
          </span>
        </div>
      ))}
    </div>
  );
};
