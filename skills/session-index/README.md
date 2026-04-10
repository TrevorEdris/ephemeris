# session-index

Generates and maintains a cross-session index with dependency tracking.

## Usage

```
/session-index generate             # Scan .ai/sessions/ and produce INDEX.md
/session-index link <from> <rel> <to>  # Record a dependency between sessions
```

## When to Use

- After completing a session that relates to prior work
- When you need to find a previous session's context
- Tracking blocking relationships between multi-session efforts

## What It Does

- Scans `.ai/sessions/` directories and produces a structured INDEX.md
- Records blocking/relates-to relationships between sessions
- Groups sessions by topic using keyword-based classification

## References

- `references/topic-keywords.txt` — Keywords for topic classification
