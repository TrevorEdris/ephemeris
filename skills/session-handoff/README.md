# session-handoff

Creates handoff documents for AI agent session transfers when context is running low.

## Usage

```
/session-handoff create [task-slug]  # Generate handoff from current session
/session-handoff resume [path]       # Resume from a previous handoff
```

## When to Use

- Context window is approaching capacity on a long task
- Ending a work session and want to resume later
- Handing off work to a different agent or session
- Major milestone completed and you want to checkpoint progress

## What It Does

- Generates pre-filled handoff scaffolds with git state, branch info, and recent commits
- Captures decisions made, files modified, and next steps
- Enables resume workflow so a fresh agent can continue without ramp-up time

## References

- `references/handoff-template.md` — Handoff document structure
- `references/resume-checklist.md` — Steps for resuming from a handoff
