---
name: session-index
description: "Generate and maintain a session index with cross-session dependencies. Scans .ai/sessions/ directories and produces INDEX.md."
user-invocable: true
argument-hint: "[generate|link <from> <relationship> <to>]"
allowed-tools: Bash(python:*), Bash(git log:*), Bash(git status), Bash(ls:*), Read, Write, Glob, Grep
model: sonnet
tags: [meta]
---

# Session Index

Generates and maintains an index of AI coding sessions with cross-session dependency tracking and topic grouping.

---

## When to Use

- Periodically, to keep the session index current
- When starting work that depends on or relates to a previous session
- When reviewing what work has been done on a topic

---

## Usage

```
/session-index                                        # Generate/update INDEX.md
/session-index generate                               # Same as above
/session-index link BOP-1074 blocks ENT-1750          # Record a dependency
/session-index link ENT-1700 relates-to BOP-1000      # Record a relationship
```

---

## Mode: generate

Scans all session directories and produces or updates INDEX.md at the session root.

### Steps

1. Run from the skill directory (`skills/session-index/`):
   ```bash
   python scripts/update_session_index.py --sessions-root ~/src/.ai/sessions/
   ```
   To use a custom topic keywords file:
   ```bash
   python scripts/update_session_index.py --sessions-root ~/src/.ai/sessions/ --topics-file path/to/keywords.txt
   ```

2. Present a summary:
   - Total sessions found
   - Sessions with DISCOVERY.md / PLAN.md
   - Dependencies recorded
   - Topic clusters identified

---

## Mode: link

Records a dependency or relationship between two sessions.

### Relationship Types

| Type | Meaning |
|------|---------|
| `blocks` | First session must complete before second can start |
| `blocked-by` | Inverse of blocks |
| `relates-to` | Related work, no ordering constraint |
| `continues` | Second session is a continuation of the first |
| `supersedes` | Second session replaces the first |

### Steps

1. Run:
   ```bash
   python scripts/update_session_index.py --sessions-root ~/src/.ai/sessions/ --link "<from> <relationship> <to>"
   ```

2. Confirm the link was recorded in INDEX.md

---

## INDEX.md Format

```markdown
# Session Index

Generated: YYYY-MM-DD

## Sessions

| Date | Ticket | Title | Discovery | Plan | Session |
|------|--------|-------|-----------|------|---------|
| 2026-03-09 | FOTW | Workflow-Enhancement | Y | Y | Y |

## Dependencies

| From | Relationship | To |
|------|-------------|-----|
| BOP-1074 | blocks | ENT-1750 |

## By Topic

### eligibility
- 2026-01-23_BOP-1000_CareFirst-Eligibility
- 2026-01-23_ENT-1700_Highmark-Eligibility-Migration

### sftp
- 2026-01-27_ENT-1642_SFTP-Cipher-Suites
```

---

## Limitations

- Topic keyword matching uses case-insensitive substring matching against the title slug. A keyword like "config" will match "Partner-Config" but not "configuration". Add both forms to the keywords file if needed.
- Topics with fewer than 2 sessions are omitted from the index to reduce noise.

## Resources

### scripts/

| Script | Purpose |
|--------|---------|
| `update_session_index.py [--sessions-root <path>] [--topics-file <path>] [--link "<from> <rel> <to>"]` | Scan sessions, generate INDEX.md |

### references/

| File | Purpose |
|------|---------|
| `topic-keywords.txt` | Configurable list of topic keywords for session grouping. One per line. |
