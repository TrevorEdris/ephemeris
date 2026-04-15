---
description: Query the ephemeris wiki with a natural language question. Returns a grounded answer with citations, or an explicit "cannot answer" message if the wiki has no relevant content.
argument-hint: "<question>"
allowed-tools:
  - Bash
---

# /ephemeris:query

Ask a question about your personal wiki. The command retrieves relevant wiki pages, assembles a grounded prompt, and synthesizes an answer that cites the specific pages used. The model is explicitly instructed to answer only from wiki excerpts — if the wiki lacks relevant content, the command returns an explicit "cannot answer" message rather than drawing on model training knowledge.

## Usage

- `/ephemeris:query Where is Rivendell?`
- `/ephemeris:query What did we decide about error handling?`
- `/ephemeris:query Tell me about the TranscriptCapture entity`

## Behavior

1. Run `python3 -m ephemeris.query "$ARGUMENTS"` using the Bash tool.
2. Stream stdout to the user as output arrives.
3. When the command finishes, display all output verbatim.
4. If the command exits non-zero, surface the error output to the user.

## Instructions

Run the command using the Bash tool:

```bash
python3 -m ephemeris.query "$ARGUMENTS"
```

The double-quotes around `$ARGUMENTS` are required to preserve spaces in the question.

Display all stdout verbatim. Do not interpret, reformat, or summarize the output.

### Exit codes

- **0** — success (answer + citations), or wiki is empty, or no relevant pages found. All three are shown as user-facing messages in stdout.
- **non-zero** — usage error (empty question) or retrieval error. Surface the stderr output to the user.

### Output format

On success, the command prints:
1. The synthesized answer.
2. A blank line.
3. A `**Sources:**` citations block listing every retrieved page by title and path.

On no-match: `Cannot answer this from the wiki — no relevant pages found.`

On empty wiki: `Wiki is empty — no pages have been built yet.`
