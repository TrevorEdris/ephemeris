# ephemeris — LLM Wiki Plugin for Claude Code

**Status:** Draft — Awaiting Approval

---

## Problem Statement

Every Claude Code session starts with amnesia. Decisions made three weeks ago, naming conventions established last sprint, and architectural rationale buried in PR descriptions do not reach the next session automatically. Engineers spend real time re-explaining context that was already established, and Claude reconstructs understanding from scratch that it already derived before.

The problem compounds in two distinct ways. First, within-session knowledge evaporates at session end: what Claude learned about this codebase, this user's preferences, and this project's conventions is discarded. Second, historical decision context is technically preserved in git history and PR comments but is practically inaccessible — it exists as raw text requiring archaeology to query, not as a structured knowledge base built for answering questions.

These two failures reinforce each other: context that should transfer between sessions doesn't, and the compounding knowledge that should build over months stays fragmented instead. The result is that every session pays a re-orientation tax that should not exist.

---

## User Personas

### Alex — The Solo Developer

- **Goals:**
  - Start new sessions without re-explaining project context and conventions to Claude
  - Get answers to "why did we choose X?" from past decisions without grepping commit history
- **Pain Points:**
  - Spends the first 5–10 minutes of each session re-orienting Claude to project conventions
  - Loses rationale for past decisions unless they write personal documentation (which they don't)

### Morgan — The Team Lead

- **Goals:**
  - New team members can ask contextual questions about the project without interrupting senior developers
  - Architectural decisions have accessible, queryable rationale — not just code
- **Pain Points:**
  - Onboarding time is high because project context lives in people's heads
  - "Why does this work this way?" questions recur regardless of how well the code is commented

### Jordan — The Tinkerer

- **Goals:**
  - Understand exactly what the plugin captures and maintains; no black-box surprises
  - Optionally explore, query, or customize the wiki for their own purposes
- **Pain Points:**
  - Background tools that do things without visibility make them uncomfortable
  - No way to verify or correct what an AI has captured about their work

---

## Functional Requirements

### FR-001: Automatic Post-Session Ingestion

**Description:** The plugin automatically processes each Claude Code session upon completion, extracting key information (decisions, conventions, patterns, rationale) and integrating it into the local wiki without any user action.

**Priority:** Must

**Acceptance Criteria:**
- [ ] After a session ends, new or updated wiki pages appear reflecting that session's content
- [ ] Ingestion triggers without any user command, prompt, or configuration
- [ ] Ingestion operates entirely locally — no network requests are issued to external services

### FR-002: Zero-Config Install

**Description:** Installing the plugin activates all core functionality with no setup steps — no environment variables, API keys, configuration files, or onboarding flow required.

**Priority:** Must

**Acceptance Criteria:**
- [ ] A user who installs the plugin and completes one session sees wiki content without any configuration
- [ ] No prompt, dialog, or warning appears asking for credentials, setup, or preferences
- [ ] The plugin is fully functional on a machine that has never configured it before

### FR-003: Local Markdown Wiki Storage

**Description:** The wiki is stored as human-readable markdown files in a single global location on the local filesystem, shared across all projects.

**Priority:** Must

**Acceptance Criteria:**
- [ ] Wiki pages are readable by the user as plain markdown files using any text editor
- [ ] A single global wiki directory is used regardless of which project the user is working on
- [ ] The wiki directory location is consistent across sessions and discoverable in the plugin documentation
- [ ] No proprietary format, binary encoding, or database file is used as the primary storage medium

### FR-004: Incremental Wiki Updates

**Description:** Each session ingestion updates and extends the existing wiki rather than replacing it, so that knowledge compounds over time and prior content is preserved and refined.

**Priority:** Must

**Acceptance Criteria:**
- [ ] A wiki page updated in one session retains all content from prior sessions
- [ ] New information on a topic is integrated with (not substituted for) prior content on that topic
- [ ] When new session content contradicts a prior wiki claim, the contradiction is flagged in the relevant page

### FR-005: Manual Ingest Trigger

**Description:** Users can manually trigger a wiki ingestion pass on demand via a slash command, without waiting for an automatic post-session trigger.

**Priority:** Should

**Acceptance Criteria:**
- [ ] A slash command triggers an ingestion pass and provides in-progress feedback
- [ ] The command indicates when ingestion completes and what changed
- [ ] Running the command on already-ingested sessions produces no duplicate content (idempotent)

### FR-006: Wiki Query via Slash Command

**Description:** Users can ask the wiki a natural language question via a slash command and receive an answer synthesized from captured wiki content.

**Priority:** Should

**Acceptance Criteria:**
- [ ] A slash command accepts a natural language question and returns an answer drawn from wiki pages
- [ ] Answers cite the specific wiki pages used to construct them
- [ ] Queries the wiki cannot answer are stated explicitly; the plugin does not fabricate answers

### FR-007: Capture Scope Configuration

**Description:** Users can configure which projects, directories, or topic areas are included in or excluded from wiki capture.

**Priority:** Could

**Acceptance Criteria:**
- [ ] A configuration file or slash command accepts include/exclude rules for project paths or topics
- [ ] Scope changes take effect on the next ingestion pass with no plugin restart required
- [ ] Excluded content is not ingested; existing wiki content from newly excluded sources is not automatically removed

### FR-008: User-Provided Wiki Schema

**Description:** Users can provide a schema document defining wiki structure, naming conventions, and page organization that the plugin follows during ingestion. Without a user schema, a built-in default is used.

**Priority:** Could

**Acceptance Criteria:**
- [ ] A user-provided schema file in plain text or markdown is recognized and applied during ingestion
- [ ] The default schema applies automatically when no user schema is present; no error or warning is shown
- [ ] Switching from the default schema to a user schema does not corrupt or delete existing wiki content

---

## Non-Functional Requirements

### NFR-001: Local-First — No External Dependencies

**Description:** All core plugin functionality operates entirely offline. No external API calls, authentication flows, or cloud services are required for the plugin to function. Ingestion uses the Claude model already active in the user's session.

**Measurable Target:** Zero external network requests issued during a standard automatic ingestion pass.

### NFR-002: Ingestion Latency

**Description:** Background ingestion must not noticeably delay session close or the start of a subsequent session.

**Measurable Target:** Ingestion for a typical 60-minute coding session completes within 60 seconds of session end.

### NFR-003: Storage Growth Rate

**Description:** The wiki must not consume unbounded disk space. Storage growth is proportional to unique knowledge gained, not raw session volume.

**Measurable Target:** Wiki storage grows by less than 1 MB per 10 hours of cumulative coding activity under typical single-project usage.

### NFR-004: Ingestion Failure Isolation

**Description:** A failure during ingestion — including crashes, timeouts, and partial runs — must leave the existing wiki intact and must not impact Claude Code session functionality.

**Measurable Target:** Any ingestion failure leaves prior wiki state byte-for-byte unchanged, produces a diagnostic log entry, and does not prevent a new Claude Code session from starting.

### NFR-005: No Telemetry

**Description:** No session content, wiki content, or plugin usage data is transmitted to any remote endpoint by the plugin.

**Measurable Target:** Zero outbound network connections initiated by the plugin except calls routed through the active Claude Code model already in use by the session.

---

## Scope Boundary

### In Scope

- Automatic post-session wiki ingestion using the active Claude model (no additional API key)
- Local markdown wiki storage in a predictable, human-readable location
- Incremental wiki updates with contradiction flagging
- Default wiki schema applied without user configuration
- Slash command for manual ingest trigger (FR-005)
- Slash command for wiki query (FR-006)
- Configuration file for capture scope: include/exclude rules (FR-007)
- User-overridable wiki schema in plain text or markdown (FR-008)

### Out of Scope

- **Cross-machine sync:** The wiki lives on the local machine. Syncing it via git, cloud storage, or other means is the user's responsibility and is not implemented by this plugin.
- **External integrations:** No connectors to GitHub Issues, Notion, Slack, Jira, Linear, or any other third-party tool.
- **Manual curation UI:** No tagging interfaces, categorization wizards, or required user labeling of sessions. The plugin infers structure from session content.
- **External LLM API dependency:** No additional API key beyond the active Claude Code model. Graphiti, OpenAI, and third-party knowledge graph services are explicitly excluded.
- **Multi-user / team sharing:** The wiki is a personal, local knowledge base. Team access, role-based permissions, and shared wikis are not addressed.
- **Non-Claude-Code interfaces:** The plugin targets the Claude Code CLI and its hook/agent system. Mobile, web, and IDE extension surfaces are out of scope.

---

## Milestones / Phases

### Milestone 1: Silent Wiki

**Includes:** FR-001, FR-002, FR-003, FR-004

**Deliverable:** Install the plugin and open one coding session. When the session ends, a local markdown wiki is automatically created and incrementally updated — no setup, no commands, no configuration required.

**Depends on:** Claude Code post-session and pre-compaction hooks (confirmed available)

### Milestone 2: Power-User Surface

**Includes:** FR-005, FR-006

**Deliverable:** Users can trigger ingestion on demand via slash command and query the wiki with natural language questions.

**Depends on:** Milestone 1

### Milestone 3: Customization Layer

**Includes:** FR-007, FR-008

**Deliverable:** Users can configure what gets captured and provide a custom wiki schema to control wiki structure and organization.

**Depends on:** Milestone 2

---

## Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Zero-config activation | 100% of installs produce a wiki entry after the first session | Manual test: install on a clean machine, run one session, verify wiki directory and content exist |
| Ingestion latency | P90 < 60 seconds for a 60-minute session | Timed ingestion runs across representative session lengths |
| Storage growth rate | < 1 MB per 10 hours of coding | Filesystem measurement over a 40-hour usage period on a single project |
| Ingestion reliability | Zero wiki corruptions in 100 fault-injection test sessions | Kill ingestion mid-run across 100 runs; verify prior wiki state is intact each time |
| Query precision | User-rated correct answers on ≥ 80% of queries drawn from captured sessions | Manual evaluation of 20 natural language queries against a test wiki |

---

## Dependencies

- **Claude Code hook system:** Post-session hooks and pre-compaction hooks are available and expose session transcript content. Both hook points can be used for ingestion triggers.
- **Active Claude model access:** Ingestion relies on the Claude model already running in the user's session. The ingestion strategy must operate within Claude Code's tool-calling or hook-invocation context without requiring a separate model instantiation.
- **Local filesystem write access:** The plugin requires write access to a global wiki directory (e.g., within `~/.claude/`) to store wiki markdown files.

---

## Open Questions

All questions resolved as of 2026-04-15.

| Question | Resolution |
|----------|------------|
| What hook events does Claude Code expose post-session? | **Resolved:** Post-session hooks and pre-compaction hooks are available, both expose transcript content. |
| Does ingestion require chunking for long sessions? | **Resolved:** Claude's 200K token context window accommodates typical sessions (50-100K tokens). Very long sessions may need chunking — handle as an implementation detail, not a blocker. |
| One wiki per project vs. global? | **Resolved:** Global wiki. Single wiki instance regardless of which project is active. |
| Default wiki schema — separate artifact? | **Resolved:** Default schema is an implementation detail for Milestone 1, not a separate PRD-level artifact. |
