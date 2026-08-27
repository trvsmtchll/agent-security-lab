# Architecture & Threat Model

## Components

| Service | Stack | Role in the scenario |
|---------|-------|----------------------|
| `devbot-agent` | FastAPI + LangGraph | The victim: an AI assistant with 4 real tools and a WebSocket stream to the UI |
| `devbot-ui` | React/TS + Vite | Chat surface; shows the conversation and a live tool/terminal/network activity feed |
| `demo-panel` | React/TS + Vite | Operator console that selects the act and injection technique |
| `demo-cli` | Python + Click | Same control surface from the terminal |
| `postgres` | PostgreSQL | `api_docs` (benign runbook metadata) and `customers` (Faker PII) |
| `wiki` | nginx | Serves the clean runbook and the poisoned variants |
| `attacker-server` | FastAPI | Local webhook that records what the agent tried to exfiltrate |

## Trust boundaries

The agent treats **tool output as trusted input to its own reasoning**. That is the flaw
the demo exercises: content fetched from the wiki (`fetch_webpage`) flows straight into
the model's context, so instructions hidden in a wiki page become instructions to the
agent. The three injection techniques differ only in how they disguise that content:

- **Semantic camouflage** — malicious steps framed as routine compliance checks.
- **Authority escalation** — steps framed as directives from a trusted authority.
- **Incremental normalization** — a benign-looking sequence that escalates step by step.

## Where the controls live

The Act 3 defense is not a smarter prompt — it is the assumption that the tools' reach is
constrained by policy. Mapped to the kill chain:

1. **Network recon** is stopped by default-deny east-west segmentation.
2. **PII access** is stopped by per-workload credentials and least-privilege grants, so a
   dev-facing agent simply cannot read the customers table.
3. **Exfiltration** is stopped by an egress allow-list — the agent has no route to
   arbitrary internet destinations or unapproved repos.
4. **The injection itself** is mitigated upstream by treating fetched content as
   untrusted and screening tool output before it re-enters the model's context.

`scripted.py` encodes both the compromised and the defended flows deterministically so the
contrast is reproducible without depending on a model's nondeterminism.
