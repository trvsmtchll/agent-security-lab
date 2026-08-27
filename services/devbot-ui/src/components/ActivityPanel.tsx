import React from "react";
import type { ToolLogEntry, TerminalEntry, NetworkEntry } from "../types";
import { ToolLog } from "./ToolLog";
import { TerminalOutput } from "./TerminalOutput";
import { NetworkTraffic } from "./NetworkTraffic";

export type ActiveTab = "tools" | "terminal" | "network";

interface ActivityPanelProps {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  toolLog: ToolLogEntry[];
  terminalEntries: TerminalEntry[];
  networkEntries: NetworkEntry[];
}

/**
 * Right pane of the split-pane layout showing agent activity.
 *
 * Contains a tab bar with three tabs: MCP Tools, Terminal, and Network.
 * Each tab displays a badge count of its entries. The active tab's
 * content component is rendered below the tab bar.
 *
 * Args:
 *   activeTab: Currently selected tab identifier.
 *   onTabChange: Callback when user clicks a different tab.
 *   toolLog: Array of MCP tool invocation entries.
 *   terminalEntries: Array of terminal command/output entries.
 *   networkEntries: Array of network connection entries.
 */
export const ActivityPanel: React.FC<ActivityPanelProps> = ({
  activeTab,
  onTabChange,
  toolLog,
  terminalEntries,
  networkEntries,
}) => {
  const tabs: { id: ActiveTab; label: string; count: number }[] = [
    { id: "tools", label: "MCP Tools", count: toolLog.length },
    { id: "terminal", label: "Terminal", count: terminalEntries.length },
    { id: "network", label: "Network", count: networkEntries.length },
  ];

  return (
    <div className="activity-panel">
      <div className="tab-bar">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className="tab-badge">{tab.count}</span>
            )}
          </button>
        ))}
      </div>

      <div className="tab-content">
        {activeTab === "tools" && <ToolLog entries={toolLog} />}
        {activeTab === "terminal" && (
          <TerminalOutput entries={terminalEntries} />
        )}
        {activeTab === "network" && (
          <NetworkTraffic entries={networkEntries} />
        )}
      </div>
    </div>
  );
};
