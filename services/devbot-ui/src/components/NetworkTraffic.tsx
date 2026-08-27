import React from "react";
import type { NetworkEntry } from "../types";

interface NetworkTrafficProps {
  entries: NetworkEntry[];
}

/**
 * Displays a log of network connections made by MCP tools.
 *
 * Each entry shows a timestamp, the tool that initiated the connection,
 * the target endpoint, and a color-coded status badge. Blocked connections
 * are highlighted in red; successful ones in green. Most recent at top.
 *
 * Args:
 *   entries: Array of NetworkEntry objects from the agent.
 */
export const NetworkTraffic: React.FC<NetworkTrafficProps> = ({ entries }) => {
  // Reason: Reverse so newest entries appear at the top.
  const sorted = [...entries].reverse();

  const statusClass = (status: NetworkEntry["status"]) => {
    switch (status) {
      case "success":
        return "badge-success";
      case "blocked":
        return "badge-blocked";
      case "error":
        return "badge-error";
    }
  };

  return (
    <div className="network-traffic">
      {sorted.length === 0 && (
        <div className="empty-state">No network activity yet</div>
      )}
      {sorted.map((entry, i) => (
        <div
          key={i}
          className={`network-entry slide-in ${entry.status === "blocked" ? "network-blocked" : ""}`}
        >
          <div className="network-entry-header">
            <span className="network-tool">{entry.tool}</span>
            <span className={`badge ${statusClass(entry.status)}`}>
              {entry.status.toUpperCase()}
            </span>
          </div>
          <div className="network-route">
            <span className="network-source">agent</span>
            <span className="network-arrow">&rarr;</span>
            <span className="network-target">{entry.target}</span>
          </div>
          <span className="network-timestamp">
            {new Date(entry.timestamp).toLocaleTimeString()}
          </span>
        </div>
      ))}
    </div>
  );
};
