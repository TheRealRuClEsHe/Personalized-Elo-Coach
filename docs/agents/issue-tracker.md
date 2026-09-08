# Issue Tracker: GitHub Issues

Issues for this repo are tracked in GitHub Issues at:
https://github.com/herculesli/Personalized-Elo-Coach/issues

## How skills use it

- **to-tickets**: creates issues from spec documents
- **triage**: reads and labels issues, filters by status
- **to-spec**: reads issues to generate specs

## Commands

```bash
# Create an issue
gh issue create --title "..." --body "..."

# List issues with a label
gh issue list --label needs-triage

# Add a label
gh issue edit <number> --add-label ready-for-agent
```

## PRs as a request surface

By default, PRs are not triaged as a separate request stream. If you want to include PRs in the triage queue (e.g., for external contributors), uncomment the `triage_prs` flag in this file.
