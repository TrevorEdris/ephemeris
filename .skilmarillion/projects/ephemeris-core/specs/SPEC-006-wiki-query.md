# SPEC-006: Wiki Query

**Feature ID:** P1-B
**Size:** SMALL
**Risk:** MODERATE
**Status:** IMPLEMENTED

## Problem Statement

Users need to retrieve information from their personal wiki without reading individual pages manually. The wiki is only as useful as it is queryable. A slash command must accept a natural language question, locate relevant wiki pages, and synthesize a grounded answer with citations. Because the wiki is built from the user's own session history, answers must be traceable to specific pages — the command must never substitute model training knowledge when no relevant wiki content exists. The "I don't know" path is not a fallback; it is a primary success condition.

## Acceptance Criteria

- AC-1: Given a populated wiki with at least one page relevant to the user's question, when the user runs the query command with a natural language question, then the command returns a synthesized answer that cites the specific wiki page(s) used (by title or path).

- AC-2: Given a populated wiki with no pages relevant to the user's question, when the user runs the query command, then the command responds with an explicit "cannot answer from wiki" message and does NOT produce a synthesized answer.

- AC-3: Given an empty wiki (no pages have been built yet), when the user runs the query command with any question, then the command responds with an explicit "wiki is empty" message and does NOT produce a synthesized answer.

- AC-4: Given a question that partially overlaps with wiki content (some relevant pages exist but none fully answer the question), when the command synthesizes a response, then the answer is limited to what the retrieved pages actually state, and any gap between the question and the available content is surfaced explicitly.

- AC-5: Given multiple wiki pages are relevant to the question, when the answer is synthesized, then citations reference all pages that contributed to the answer, not just the highest-ranked one.

- AC-6: Given the question is empty or consists only of whitespace, when the command is invoked, then it returns a usage error without querying the wiki.

- AC-7: Given a retrieved set of wiki page excerpts, when the answer is synthesized, then the model prompt explicitly instructs the model to use only the provided excerpts and to say it cannot answer if the excerpts are insufficient — this constraint is verifiable from the prompt string passed to the model.

- AC-8: Given a wiki query returns an answer with citations, when the user inspects the cited pages, then every factual claim in the answer can be traced to a passage in at least one cited page.

- AC-9: Given the wiki contains pages but a retrieval error occurs (e.g., index read failure), when the command runs, then the error is surfaced to the user and no partial or fabricated answer is returned.

## Architecture Recommendation

The command implements a search-then-synthesize pipeline with an explicit grounding contract enforced at the prompt layer.

**Pipeline stages:**

1. **Input validation** — reject empty or whitespace-only questions before any I/O.
2. **Retrieval** — search the wiki index for pages relevant to the question. Retrieval uses the index built by P0-D (incremental update). Candidate approaches: BM25 keyword match over page text, or embedding similarity if an embedding store is available. For SMALL size, start with BM25 or a simple TF-IDF scan over page content; do not over-engineer retrieval.
3. **No-match gate** — if retrieval returns zero pages, emit the explicit "cannot answer" response immediately. No model call is made. This is the grounding contract's first enforcement point.
4. **Context assembly** — concatenate the text of the top-N retrieved pages (with their titles and paths) into a context block. Cap total tokens to a safe limit (e.g., 8 000 tokens) by truncating lower-ranked pages first.
5. **Grounded synthesis** — invoke the model with a prompt that:
   - Provides the assembled wiki excerpts verbatim.
   - Contains an explicit instruction: "Answer the question using only the wiki excerpts provided below. If the excerpts do not contain enough information to answer the question, respond with: 'I cannot answer this from the wiki.'"
   - Places the question after the excerpts, not before, to reduce the model's tendency to answer from prior knowledge.
6. **Citation attachment** — parse the model's response and append a citations block listing the title and path of every page included in the context. Citations are appended regardless of whether the model acknowledged them, ensuring AC-5.
7. **Output** — print the synthesized answer (or the explicit cannot-answer message) with citations to stdout.

**Grounding enforcement:**

Grounding is enforced structurally, not by trusting the model alone:
- The no-match gate (stage 3) prevents any model call when the wiki has no relevant content.
- The prompt instruction (stage 5) is a hard constraint in the system prompt, not a suggestion.
- Citations are appended by the host code (stage 6), not generated by the model, so they always reflect what was actually retrieved.
- Tests verify the literal prompt string passed to the model contains the grounding instruction (AC-7).

## TDD Plan

Tests target the pipeline stages in isolation. The model call is injected as an interface so tests can verify prompt construction without a live model.

**Step 1 — RED:** `TestQuery_EmptyQuestion`
- Call the query handler with an empty string and with a whitespace-only string.
- Assert a usage error is returned and no retrieval or model call is made.
- Run: FAIL.

**Step 2 — RED:** `TestQuery_EmptyWiki`
- Call the handler with a valid question against an empty wiki index (zero pages).
- Assert the response contains the explicit "wiki is empty" message and no model call is made.
- Run: FAIL.

**Step 3 — RED:** `TestQuery_NoMatchingPages`
- Populate a small wiki with pages on topic A; ask a question about unrelated topic B.
- Assert retrieval returns zero pages, the response contains the explicit "cannot answer" message, and no model call is made.
- Run: FAIL.

**Step 4 — RED:** `TestQuery_SingleMatchReturnsAnswer`
- Populate a wiki with one page containing a known fact.
- Ask a question whose answer is on that page.
- Assert the model receives a prompt containing the page's text and the grounding instruction.
- Assert the response cites the page by title or path.
- Run: FAIL.

**Step 5 — RED:** `TestQuery_MultipleMatchesCiteAll`
- Populate a wiki with three pages, all relevant to the question.
- Assert the citations block in the response lists all three pages.
- Run: FAIL.

**Step 6 — RED:** `TestQuery_PromptContainsGroundingInstruction`
- Capture the prompt passed to the model interface.
- Assert it contains the literal grounding instruction (the "only use these excerpts" clause).
- Run: FAIL.

**Step 7 — RED:** `TestQuery_RetrievalError`
- Inject a retrieval function that returns an error.
- Assert the command surfaces the error and returns no answer.
- Run: FAIL.

**Step 8 — GREEN:** Implement the pipeline minimally to pass all RED tests.
- Implement input validation, retrieval stub, no-match gate, context assembly, prompt construction with grounding instruction, model interface call, and citation attachment.
- Run all tests: PASS.

**Step 9 — REFACTOR:**
- Extract retrieval into a `Retriever` interface with a concrete BM25/scan implementation.
- Extract prompt construction into a `BuildGroundedPrompt(question string, pages []WikiPage) string` function.
- Extract citation attachment into a `FormatCitations(pages []WikiPage) string` function.
- Confirm all tests still PASS.
- Confirm no test reaches into unexported symbols that would lock the structure.
