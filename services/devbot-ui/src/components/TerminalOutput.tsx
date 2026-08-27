import React, { useEffect, useRef } from "react";
import type { TerminalEntry } from "../types";

interface TerminalOutputProps {
  entries: TerminalEntry[];
}

/**
 * Terminal-style display for command execution output.
 *
 * Renders green-on-black monospace text with a command prompt ($ command)
 * followed by output. Auto-scrolls to bottom as new entries arrive.
 * Entries are separated by a horizontal divider.
 *
 * Args:
 *   entries: Array of TerminalEntry objects (command + output pairs).
 */
export const TerminalOutput: React.FC<TerminalOutputProps> = ({ entries }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // Reason: Auto-scroll the terminal container to the bottom so
  // the user always sees the most recent command output.
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [entries]);

  return (
    <div className="terminal-output" ref={containerRef}>
      {entries.length === 0 && (
        <div className="empty-state terminal-empty">
          No terminal output yet
        </div>
      )}
      {entries.map((entry, i) => (
        <div key={i} className="terminal-entry">
          <div className="terminal-prompt">
            <span className="prompt-symbol">$</span>
            <span className="terminal-command">{entry.command}</span>
          </div>
          {entry.output && (
            <pre className="terminal-text">{entry.output}</pre>
          )}
          {i < entries.length - 1 && <hr className="terminal-divider" />}
        </div>
      ))}
    </div>
  );
};
