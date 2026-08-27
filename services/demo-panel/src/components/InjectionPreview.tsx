import { injectionContent, type ThreatTag } from "../data/injectionContent";
import "../injection-preview.css";

interface InjectionPreviewProps {
  technique: "v2" | "v3" | "v4";
}

/**
 * Renders a visual preview of the prompt injection content for the
 * selected technique. Shows the social engineering framing, fake
 * authority warning, and each injected step with color-coded threat
 * tags and highlighted dangerous commands.
 */
export function InjectionPreview({ technique }: InjectionPreviewProps) {
  const content = injectionContent[technique];

  return (
    <div className="injection-preview">
      {/* Header */}
      <div className="injection-header">
        <span className="injection-icon">⚠</span>
        <span className="injection-label">Injection Preview</span>
        <span className="injection-badge">{technique}</span>
      </div>

      {/* Tactic summary */}
      <div className="injection-tactic">{content.tactic}</div>

      {/* Fake authority warning box */}
      <div className="injection-warning-box">{content.warningText}</div>

      {/* Steps */}
      <div className="injection-steps">
        {content.steps.map((step, i) => (
          <div className="injection-step" key={i}>
            <div className="injection-step-header">
              <span className="injection-step-label">
                Step {i + 1}: {step.label}
              </span>
              <ThreatBadge tag={step.threatTag} />
            </div>
            <div className="injection-step-text">{step.text}</div>
            <code
              className={`injection-command${step.threatTag === "BENIGN" ? " benign" : ""}`}
            >
              {step.dangerousCommand}
            </code>
          </div>
        ))}
      </div>
    </div>
  );
}

function ThreatBadge({ tag }: { tag: ThreatTag }) {
  const cls =
    tag === "BENIGN"
      ? "threat-benign"
      : tag === "RECON"
        ? "threat-recon"
        : tag === "DATA THEFT"
          ? "threat-data"
          : "threat-exfil";

  return <span className={`threat-badge ${cls}`}>{tag}</span>;
}
