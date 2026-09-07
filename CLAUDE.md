# Project: Personalized Elo Coach

## Agent skills

### Issue tracker

Issues are tracked in GitHub Issues. See `docs/agents/issue-tracker.md`.

### Triage labels

The repo uses default triage labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: `CONTEXT.md` at repo root, ADRs under `docs/adr/`. See `docs/agents/domain.md`.

## Issue logging protocol

When the user reports a bug, error, or unexpected behavior, OR when you propose 
and apply a fix during this session:

1. Append a new entry to `ISSUES.md` using the format defined in that file.
2. Auto-increment the ID (check the last ISSUE-XXX in the file).
3. Fill all five fields: Problem, Proposed fix, Method, Result, Tags.
4. If the result is unknown at the time (fix not yet verified), mark Result as 
   "PENDING" and update it once verified.
5. Before starting a new task, read ISSUES.md and check whether a similar problem 
   has been solved before.