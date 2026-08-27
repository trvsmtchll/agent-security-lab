import { useCallback, useEffect, useRef, useState } from "react";
import { InjectionPreview } from "./InjectionPreview";
import "../styles.css";

/* -----------------------------------------------------------------------
   Types
   ----------------------------------------------------------------------- */

/** Shape of the /api/state response from the devbot-agent backend. */
interface AgentStatus {
  mode: "live" | "scripted";
  wiki_page: string;
  act: "idle" | "act1" | "act2" | "act3";
  agent_state: "normal" | "compromised" | "blocked";
  prompt_style: "default" | "moderate";
  conversation_history: unknown[];
  tool_log: unknown[];
}

/** Shape of the /attacker/exfil response from the attacker server. */
interface ExfilStatus {
  count: number;
  entries: ExfilEntry[];
}

interface ExfilEntry {
  timestamp: string;
  title: string;
  body: string;
  size_bytes: number;
}

/** An entry in the local activity log shown at the bottom. */
interface LogEntry {
  time: string;
  message: string;
  status: "success" | "error";
}

/** A toast notification. */
interface Toast {
  id: number;
  message: string;
  variant: "success" | "error";
}

/** Injection technique option. */
interface TechniqueOption {
  id: "v2" | "v3" | "v4";
  label: string;
  description: string;
}

const TECHNIQUES: TechniqueOption[] = [
  { id: "v2", label: "v2", description: "Semantic Camouflage" },
  { id: "v3", label: "v3", description: "Authority Escalation" },
  { id: "v4", label: "v4", description: "Incremental Normalization" },
];

/* -----------------------------------------------------------------------
   Helpers
   ----------------------------------------------------------------------- */

let toastCounter = 0;

/**
 * Returns the current time as HH:MM:SS for log entries.
 */
function timeNow(): string {
  return new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/* -----------------------------------------------------------------------
   Component
   ----------------------------------------------------------------------- */

/**
 * Demo Control Panel -- Sentinel-themed orchestration for the Shadow Agent demo.
 *
 * Provides action buttons for demo flow control, injection technique
 * selection, a real-time status dashboard via polling, and a timestamped
 * activity log.
 */
export function ControlPanel() {
  /* --- State ---------------------------------------------------------- */
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [exfilStatus, setExfilStatus] = useState<ExfilStatus | null>(null);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [log, setLog] = useState<LogEntry[]>([]);
  const [selectedTechnique, setSelectedTechnique] = useState<"v2" | "v3" | "v4">("v2");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /* --- Toast helper --------------------------------------------------- */
  const addToast = useCallback(
    (message: string, variant: "success" | "error") => {
      const id = ++toastCounter;
      setToasts((prev) => [...prev, { id, message, variant }]);
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, 3000);
    },
    [],
  );

  /* --- Log helper ----------------------------------------------------- */
  const addLog = useCallback(
    (message: string, status: "success" | "error" = "success") => {
      setLog((prev) => [{ time: timeNow(), message, status }, ...prev]);
    },
    [],
  );

  /* --- Polling -------------------------------------------------------- */
  const fetchStatus = useCallback(async () => {
    try {
      const [agentRes, exfilRes] = await Promise.all([
        fetch("/api/state"),
        fetch("/attacker/exfil"),
      ]);
      if (agentRes.ok) {
        setAgentStatus(await agentRes.json());
      }
      if (exfilRes.ok) {
        setExfilStatus(await exfilRes.json());
      }
    } catch {
      // Silently ignore polling errors -- services may not be up yet
    }
  }, []);

  useEffect(() => {
    // Reason: Initial fetch + 2-second polling interval for live updates
    fetchStatus();
    pollRef.current = setInterval(fetchStatus, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [fetchStatus]);

  /* --- Action handlers ------------------------------------------------ */

  /**
   * Generic action dispatcher. Makes the API call(s), shows loading state,
   * logs the result, and fires a toast notification.
   */
  const runAction = useCallback(
    async (actionKey: string, label: string, calls: () => Promise<void>) => {
      setLoadingAction(actionKey);
      try {
        await calls();
        addLog(label, "success");
        addToast(label, "success");
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : "Unknown error";
        addLog(`${label} -- FAILED: ${msg}`, "error");
        addToast(`Failed: ${label}`, "error");
      } finally {
        setLoadingAction(null);
        fetchStatus();
      }
    },
    [addLog, addToast, fetchStatus],
  );

  const handleReset = useCallback(() => {
    runAction("reset", "Reset demo", async () => {
      const r1 = await fetch("/api/reset", { method: "POST" });
      if (!r1.ok) throw new Error(`Agent reset failed (${r1.status})`);
      const r2 = await fetch("/attacker/exfil", { method: "DELETE" });
      if (!r2.ok) throw new Error(`Exfil clear failed (${r2.status})`);
    });
  }, [runAction]);

  const handleAct1 = useCallback(() => {
    runAction("act1", "Act 1: Normal Operation", async () => {
      const res = await fetch("/api/set-act", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ act: "act1" }),
      });
      if (!res.ok) throw new Error(`Set act failed (${res.status})`);
    });
  }, [runAction]);

  const handleAct2 = useCallback(() => {
    const tech = TECHNIQUES.find((t) => t.id === selectedTechnique)!;
    runAction("act2", `Act 2: The Attack (${tech.label} - ${tech.description})`, async () => {
      const res = await fetch("/api/set-act", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ act: "act2", injection_technique: selectedTechnique }),
      });
      if (!res.ok) throw new Error(`Set act failed (${res.status})`);
    });
  }, [runAction, selectedTechnique]);

  const handleAct3 = useCallback(() => {
    runAction("act3", "Act 3: Sentinel Defends", async () => {
      const res = await fetch("/api/set-act", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ act: "act3", injection_technique: selectedTechnique }),
      });
      if (!res.ok) throw new Error(`Set act failed (${res.status})`);
    });
  }, [runAction, selectedTechnique]);

  /* --- Derived values ------------------------------------------------- */
  const messageCount = agentStatus?.conversation_history?.length ?? 0;
  const toolCallCount = agentStatus?.tool_log?.length ?? 0;
  const exfilCount = exfilStatus?.count ?? 0;
  const currentPromptStyle = agentStatus?.prompt_style ?? "default";
  const currentWikiPage = agentStatus?.wiki_page ?? "clean";

  // Reason: Derive the active technique from the wiki_page state
  // (e.g. "poisoned-v3" → "v3") for display in the status card.
  const activeTechnique = currentWikiPage.startsWith("poisoned-")
    ? currentWikiPage.replace("poisoned-", "")
    : "--";

  /* --- Render --------------------------------------------------------- */
  return (
    <div className="panel">
      {/* Header */}
      <div className="panel-header">
        <div>
          <img src="/logo.svg" alt="Sentinel" className="header-logo" />
          <div className="panel-title">Demo Control</div>
          <div className="panel-subtitle">
            Shadow Agent exfiltration demo orchestration
          </div>
        </div>
        <div className="panel-connection">
          <span className={`panel-connection-dot${agentStatus ? "" : " offline"}`} />
          {agentStatus ? "Connected" : "Connecting..."}
        </div>
      </div>

      {/* Left: Actions */}
      <div className="actions-section">
        <div>
          <div className="section-title">Demo Flow</div>
          <div className="button-group">
            <button
              className="action-btn btn-reset"
              onClick={handleReset}
              disabled={loadingAction !== null}
            >
              {loadingAction === "reset" && <span className="spinner" />}
              Reset Demo
            </button>

            <button
              className="action-btn btn-act1"
              onClick={handleAct1}
              disabled={loadingAction !== null}
            >
              {loadingAction === "act1" && <span className="spinner" />}
              Act 1: Normal Operation
            </button>

            <button
              className="action-btn btn-act2"
              onClick={handleAct2}
              disabled={loadingAction !== null}
            >
              {loadingAction === "act2" && <span className="spinner" />}
              Act 2: The Attack
            </button>

            <button
              className="action-btn btn-act3"
              onClick={handleAct3}
              disabled={loadingAction !== null}
            >
              {loadingAction === "act3" && <span className="spinner" />}
              Act 3: Sentinel Defends
            </button>
          </div>
        </div>

        {/* Injection Technique Selector */}
        <div className="technique-selector">
          <div className="section-title">Injection Technique</div>
          <div className="technique-chips">
            {TECHNIQUES.map((tech) => (
              <div
                key={tech.id}
                className={`technique-chip${selectedTechnique === tech.id ? " selected" : ""}`}
                onClick={() => setSelectedTechnique(tech.id)}
              >
                <div className="technique-chip-radio">
                  <div className="technique-chip-radio-inner" />
                </div>
                <span className="technique-chip-label">{tech.label}</span>
                <span className="technique-chip-desc">{tech.description}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Injection Preview */}
        <InjectionPreview key={selectedTechnique} technique={selectedTechnique} />
      </div>

      {/* Right: Status */}
      <div className="status-section">
        <div className="section-title">Status</div>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-card-label">Current Act</div>
            <div
              className={`status-card-value val-${agentStatus?.act ?? "idle"}`}
            >
              {agentStatus?.act ?? "--"}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Agent State</div>
            <div
              className={`status-card-value val-${agentStatus?.agent_state ?? "normal"}`}
            >
              <span
                className={`state-indicator dot-${agentStatus?.agent_state ?? "normal"}`}
              />
              {agentStatus?.agent_state ?? "--"}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Prompt Style</div>
            <div
              className={`status-card-value val-${currentPromptStyle}`}
            >
              {currentPromptStyle}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Technique</div>
            <div
              className={`status-card-value${activeTechnique !== "--" ? " val-compromised" : ""}`}
            >
              {activeTechnique}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Wiki Page</div>
            <div
              className={`status-card-value val-${currentWikiPage.startsWith("poisoned") ? "poisoned" : "clean"}`}
            >
              {currentWikiPage}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Demo Mode</div>
            <div
              className={`status-card-value val-${agentStatus?.mode ?? "live"}`}
            >
              {agentStatus?.mode ?? "--"}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Messages</div>
            <div className="status-card-value">{messageCount}</div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Tool Calls</div>
            <div className="status-card-value">{toolCallCount}</div>
          </div>

          <div
            className={`status-card${exfilCount > 0 ? " exfil-alert" : ""}`}
          >
            <div className="status-card-label">Exfil Payloads</div>
            <div
              className={`status-card-value${exfilCount > 0 ? " val-compromised" : ""}`}
            >
              {exfilCount}
            </div>
          </div>

          <div className="status-card">
            <div className="status-card-label">Polling</div>
            <div className="status-card-value val-normal">2s</div>
          </div>
        </div>

        {/* Exfil entries preview */}
        {exfilStatus && exfilStatus.entries.length > 0 && (
          <div className="exfil-list">
            <div className="section-title">Exfiltrated Data</div>
            {exfilStatus.entries.map((entry, i) => (
              <div className="exfil-entry" key={i}>
                <div className="exfil-entry-title">{entry.title || "Untitled"}</div>
                <div className="exfil-entry-preview">
                  {entry.body.length > 120
                    ? entry.body.substring(0, 120) + "..."
                    : entry.body}
                </div>
                <div className="exfil-entry-meta">
                  {entry.size_bytes} bytes -- {entry.timestamp}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Bottom: Activity Log */}
      <div className="log-section">
        <div className="section-title">Activity Log</div>
        {log.length === 0 ? (
          <div className="log-empty">No actions yet. Press a button above.</div>
        ) : (
          <div className="log-entries">
            {log.map((entry, i) => (
              <div className="log-entry" key={i}>
                <span className="log-time">{entry.time}</span>
                <span className="log-separator">--</span>
                <span
                  className={`log-message ${entry.status === "error" ? "log-error" : "log-success"}`}
                >
                  {entry.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Toasts */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.variant}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </div>
  );
}
