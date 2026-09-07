# Domain Docs: Single-Context Layout

This repo uses a single-context layout for domain documentation:

## Structure

- **`CONTEXT.md`** at repo root: overview, key concepts, architecture snapshot
- **`docs/adr/`**: Architecture Decision Records (one file per decision)

## What to write in CONTEXT.md

- **Overview**: what the project does, who owns it, key goals
- **Architecture**: high-level system design, key modules, data flow
- **Key concepts**: domain vocabulary, mental models
- **How to add an ADR**: link to `docs/adr/` with one-liner for each

## ADRs

Create one file per decision:

```
docs/adr/0001-decision-title.md
docs/adr/0002-another-decision.md
```

Each ADR should include:
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Context**: Why we needed to decide
- **Decision**: What we chose
- **Consequences**: Trade-offs and implications

## How skills use these

- **research**: reads CONTEXT.md to understand the domain before working
- **to-spec**: references CONTEXT.md for context when generating specs
- **grilling**: uses domain vocab and concepts to frame questions
