---
description: Trigger wiki ingestion on all pending sessions or a specific session by ID. Prints per-session progress and a structured summary.
argument-hint: "[<session-id>]"
allowed-tools:
  - Bash
---

# /ephemeris:ingest

Manually trigger the ephemeris wiki ingestion pipeline. Useful for mid-session wiki updates, recovering from a failed auto-trigger, or backfilling skipped sessions.

## Usage

- `/ephemeris:ingest` — process all pending sessions
- `/ephemeris:ingest <session-id>` — process one specific session

## Behavior

1. Run `python3 -m ephemeris.ingest $ARGUMENTS` using the Bash tool.
2. Stream stdout to the user as each progress line arrives.
3. When the command finishes, display the final summary block verbatim.
4. If the command exits non-zero, surface the error output to the user.

## Instructions

Parse `$ARGUMENTS`:
- If empty, run: `python3 -m ephemeris.ingest`
- If a session ID is provided, run: `python3 -m ephemeris.ingest <session-id>`

Run the command using the Bash tool. Stream or display all output as it arrives. Do not interpret or reformat the output — show it verbatim so the user sees the exact progress lines and summary block from the CLI.

If the exit code is non-zero, indicate that ingestion encountered errors and refer the user to the error lines in the output for details.
