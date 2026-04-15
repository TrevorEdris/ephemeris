# SPEC-002: Transcript Capture

**Feature ID:** P0-B
**Size:** SMALL
**Risk:** MODERATE
**Status:** IMPLEMENTED

## Problem Statement

Before the ingestion engine can build the wiki, raw session transcripts must be reliably captured from hook events and persisted locally. Claude Code fires hooks at two distinct points—pre-compaction and post-session—each with a different payload shape. Capture must be idempotent so that re-running a hook (e.g., on crash recovery or duplicate delivery) does not corrupt or duplicate stored data, and it must detect truncated payloads before writing so that incomplete transcripts are never silently accepted as complete.

## Acceptance Criteria

- AC-1: Given a `PreCompact` hook fires with a valid payload containing a session ID and full conversation transcript, when the handler processes the payload, then the transcript is persisted to staging storage keyed by that session ID.

- AC-2: Given a `Stop` hook fires with a valid payload containing a session ID and transcript or session metadata, when the handler processes the payload, then the available transcript content is persisted to staging storage keyed by that session ID.

- AC-3: Given the same session ID is received more than once with identical content, when the handler processes the duplicate, then the stored result is unchanged and no error is returned.

- AC-4: Given the same session ID is received more than once with differing content, when the handler processes the second delivery, then the stored result reflects the latest content and no error is returned.

- AC-5: Given a hook payload arrives with a session ID but an empty or missing transcript field, when the handler processes the payload, then no file is written and the error is surfaced with enough detail to identify the session ID and hook type.

- AC-6: Given a hook payload is malformed JSON or is missing the session ID field, when the handler attempts to parse it, then no file is written and the error is surfaced without panicking.

- AC-7: Given a transcript for a typical 60-minute session is captured via `PreCompact`, when the stored file is read back, then its byte length matches the byte length of the original payload transcript field with no truncation.

- AC-8: Given staging storage is unavailable (e.g., directory missing, permission denied), when the handler attempts to write, then the error is surfaced and no partial file is left behind.

- AC-9: Given a `PreCompact` payload and a `Stop` payload arrive for the same session ID, when both are processed, then each is stored without overwriting the other (distinguished by hook type in the storage key or path).

## Architecture Recommendation

Hook payloads arrive on stdin as JSON. The capture component reads all of stdin, parses the JSON envelope, extracts `session_id` and the transcript field (field name differs by hook type—confirm exact field names against the P0-A scaffold), then writes the raw transcript bytes atomically to the staging directory.

**Storage path convention:**

```
~/.claude/ephemeris/staging/<hook_type>/<session_id>.json
```

Where `<hook_type>` is `pre-compact` or `stop`. This satisfies AC-9 (no collision between hook types for the same session) and AC-3/AC-4 (last-write-wins per session per hook type, which is idempotent for identical content and deterministic for differing content).

**Atomic write pattern:** Write to a `.tmp` file in the same directory, then `os.Rename` to the final path. Rename is atomic on POSIX filesystems; this prevents partial files on crash (AC-8) and ensures readers never see incomplete data.

**Truncation detection (AC-7):** After writing, stat the file and compare byte length against `len(transcriptBytes)`. If they differ, delete the file and return an error. Alternatively, embed a byte-count field in a thin wrapper JSON envelope stored alongside the raw transcript.

**Staging directory bootstrap:** On first write, create `~/.claude/ephemeris/staging/pre-compact/` and `~/.claude/ephemeris/staging/stop/` with `os.MkdirAll`. This belongs in P0-A but must be verified here.

## TDD Plan

Tests target the capture handler in isolation. Stdin injection and filesystem abstraction (via an `afero`-style interface or a real temp directory) keep tests hermetic.

**Step 1 — RED:** `TestCapture_PreCompact_ValidPayload`
- Inject a synthetic `PreCompact` JSON payload with a known `session_id` and transcript string.
- Assert the file `<tmpdir>/pre-compact/<session_id>.json` exists and its contents match the transcript.
- Run: FAIL (handler not implemented).

**Step 2 — RED:** `TestCapture_Stop_ValidPayload`
- Same as Step 1 but for a `Stop` payload; assert file lands under `<tmpdir>/stop/`.
- Run: FAIL.

**Step 3 — RED:** `TestCapture_Idempotent_SameContent`
- Call the handler twice with identical payload for the same session ID.
- Assert exactly one file exists with correct content; no error.
- Run: FAIL.

**Step 4 — RED:** `TestCapture_Idempotent_DifferentContent`
- Call the handler twice for the same session ID with different transcript content.
- Assert file contains the second payload's transcript; no error.
- Run: FAIL.

**Step 5 — RED:** `TestCapture_EmptyTranscript`
- Inject a payload with a valid session ID but empty transcript field.
- Assert no file is written and error is non-nil.
- Run: FAIL.

**Step 6 — RED:** `TestCapture_MalformedJSON`
- Inject `{not valid json`.
- Assert no file is written and error is non-nil (no panic).
- Run: FAIL.

**Step 7 — RED:** `TestCapture_MissingSessionID`
- Inject valid JSON with no `session_id` field.
- Assert no file is written and error is non-nil.
- Run: FAIL.

**Step 8 — RED:** `TestCapture_NoTruncation_LargeTranscript`
- Generate a synthetic transcript of ~1 MB (approximating a 60-minute session).
- Capture it, read it back, assert byte lengths match exactly.
- Run: FAIL.

**Step 9 — GREEN:** Implement the capture handler minimally to pass all RED tests.
- Parse stdin JSON, validate `session_id` and transcript field presence.
- Write atomically via tmp-then-rename to the correct subdirectory path.
- Return typed errors for each failure mode.
- Run all tests: PASS.

**Step 10 — REFACTOR:**
- Extract payload parsing into a `ParseHookPayload(hookType, r io.Reader)` function.
- Extract atomic write into a `StageTranscript(dir, sessionID string, data []byte) error` function.
- Confirm all tests still PASS.
- Confirm no test reaches into unexported symbols that would lock the refactored structure.
