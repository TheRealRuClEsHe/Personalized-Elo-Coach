# Triage Labels

Five canonical labels organize issues by role and readiness:

| Label | Meaning | When to apply |
|-------|---------|---------------|
| `needs-triage` | New issue, not yet assigned a role | On creation; remove once categorized |
| `needs-info` | Waiting on more information | When you need clarification from reporter |
| `ready-for-agent` | Ready for Claude to work on | When the spec is clear and unblocked |
| `ready-for-human` | Needs human review or decision | When Claude hit a decision point |
| `wontfix` | Acknowledged but not fixing | When explicitly closing without action |

## Usage

Issues flow through these states. An issue typically moves: `needs-triage` → (one of: `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`).
