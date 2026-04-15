# Ephemeris Wiki Schema

This document defines the structure and conventions for all wiki pages
managed by the ephemeris ingestion engine. All generated pages must
conform to the conventions described here.

---

## Page Types

### Topic Pages

- **Directory:** `wiki/topics/`
- **Naming:** `kebab-case.md` (e.g., `error-handling-strategy.md`)
- **Required Sections:**
  - `## Overview` — concise summary of the topic (1-3 sentences)
  - `## Details` — extended discussion; each session may append a subsection
  - `## Sessions` — citation list; one line per contributing session

**Example:**

```markdown
# Error Handling Strategy

## Overview
All errors are wrapped in domain-specific exception types before propagation.

## Details

### 2026-04-15 (session-abc123)
The team decided to use a base `AppError` class with typed subclasses.
...

## Sessions
> Source: [2026-04-15 session-abc123]
```

---

### Entity Pages

- **Directory:** `wiki/entities/`
- **Naming:** `PascalCase.md` (e.g., `TranscriptCapture.md`)
- **Required Sections:**
  - `## Role` — what this component/system does in one paragraph
  - `## Relationships` — bulleted list of named relationships to other entities
  - `## Sessions` — citation list; one line per contributing session

**Example:**

```markdown
# TranscriptCapture

## Role
Captures raw session transcripts from Claude Code hooks and persists them
atomically to a staging directory keyed by session ID.

## Relationships
- [IngestEngine](IngestEngine.md) — consumes staged transcripts
- [HookPayload](HookPayload.md) — provides the source transcript path

## Sessions
> Source: [2026-04-15 session-abc123]
```

---

### Decision Log

- **File:** `wiki/DECISIONS.md` (single shared file, newest-first)
- **Entry format:** `## [YYYY-MM-DD] <title>`
  - `**Decision:**` — what was decided
  - `**Rationale:**` — why this decision was made
  - `**Session:**` — citation linking to the source session

**Example:**

```markdown
## [2026-04-15] Use atomic rename for staging writes

**Decision:** All staging writes use `os.replace()` after writing to a
temp file in the destination directory.

**Rationale:** Atomic rename guarantees readers never see partial data
and no orphaned temp files remain on crash.

**Session:** > Source: [2026-04-15 session-abc123]
```

---

## Cross-References

Use standard markdown links relative to the wiki root:

- From a topic page to an entity: `[EntityName](../entities/EntityName.md)`
- From an entity page to a topic: `[topic-name](../topics/topic-name.md)`
- From a decision to an entity: `[EntityName](entities/EntityName.md)`

---

## Citation Format

Every page must include a `## Sessions` section (or inline `**Session:**`
for decision entries) with citations in the following format:

```
> Source: [YYYY-MM-DD session-id]
```

Citations are appended by the ingestion engine; they are never generated
by the model.

---

## Naming Conventions

| Type | Convention | Examples |
|------|-----------|---------|
| Topic | `kebab-case` | `error-handling-strategy`, `api-design-patterns` |
| Entity | `PascalCase` | `TranscriptCapture`, `IngestEngine`, `ModelClient` |
| Decision | Date-prefixed title | `[2026-04-15] Use atomic rename` |

---

## Model Output Format

When the ingestion engine queries the model, it expects a JSON response
with the following structure:

```json
{
  "operations": [
    {
      "action": "create",
      "page_type": "topic",
      "page_name": "error-handling-strategy",
      "content": {
        "overview": "All errors are wrapped in domain-specific types.",
        "details": "The team decided to use a base AppError class..."
      },
      "cross_references": ["TranscriptCapture"]
    }
  ]
}
```

If the transcript contains no extractable knowledge, the model must return:
```json
{"operations": []}
```
