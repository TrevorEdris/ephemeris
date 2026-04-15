"""query.py — Wiki query pipeline for ephemeris.

Implements a search-then-synthesize pipeline with an explicit grounding
contract enforced at the prompt layer. Never substitutes model training
knowledge when the wiki has no relevant content.

Pipeline stages:
    1. Input validation — reject empty/whitespace questions before any I/O.
    2. Retrieval — token-overlap scan over wiki pages; excludes SCHEMA.md.
    3. Empty-wiki gate — if no pages exist, emit "wiki is empty" immediately.
    4. No-match gate — if retrieval returns zero pages, emit "cannot answer".
    5. Context assembly — concatenate top-N retrieved pages with titles/paths.
    6. Grounded synthesis — invoke model with grounding instruction + excerpts.
    7. Citation attachment — append all retrieved pages as citations (host
       code, not model output — ensures AC-5 always holds).
    8. Output — print answer + citations, or the appropriate gate message.

Public API:
    WikiPage          — dataclass(path, title, content, score)
    QueryResult       — dataclass(answer, citations, no_match, empty_wiki,
                                  usage_error, retrieval_error)
    Retriever         — Protocol with retrieve(question, top_n) -> list[WikiPage]
    FilesystemRetriever(wiki_root)  — token-overlap scan implementation
    build_grounded_prompt(question, pages) -> str
    format_citations(pages) -> str
    run_query(question, wiki_root, model_client, retriever, top_n) -> QueryResult
    main(argv) -> int

CLI:
    python3 -m ephemeris.query "<question>"

Environment overrides:
    EPHEMERIS_WIKI_ROOT  — wiki root (default: ~/.claude/ephemeris/wiki)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ephemeris.model import ModelClient


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class WikiPage:
    """A retrieved wiki page with its relevance score.

    Attributes:
        path: Path to the markdown file (absolute or wiki-root-relative).
        title: Human-readable title extracted from the page.
        content: Full text content of the page.
        score: Token-overlap score (0.0 if not yet ranked).
    """

    path: Path
    title: str
    content: str
    score: float = 0.0


@dataclass
class QueryResult:
    """Result of a wiki query pipeline run.

    Attributes:
        answer: Synthesized answer text (empty if no answer was produced).
        citations: Pages retrieved and included in the prompt context.
        no_match: True if retrieval returned zero relevant pages.
        empty_wiki: True if the wiki contained no pages at all.
        usage_error: True if the question was empty or whitespace-only.
        retrieval_error: Non-None error message if retrieval raised an exception.
    """

    answer: str = ""
    citations: list[WikiPage] = field(default_factory=list)
    no_match: bool = False
    empty_wiki: bool = False
    usage_error: bool = False
    retrieval_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Retriever Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class Retriever(Protocol):
    """Protocol for wiki page retrieval.

    Any object with a ``retrieve`` method satisfies this protocol.
    """

    def retrieve(self, question: str, top_n: int = 5) -> list[WikiPage]:
        """Retrieve the most relevant wiki pages for the question.

        Args:
            question: Natural-language question string.
            top_n: Maximum number of pages to return.

        Returns:
            Ranked list of WikiPage objects (highest relevance first).
            May return fewer than top_n pages, or an empty list.

        Raises:
            Any exception on I/O failure (caller must handle).
        """
        ...


# ---------------------------------------------------------------------------
# FilesystemRetriever
# ---------------------------------------------------------------------------

class FilesystemRetriever:
    """Concrete Retriever that scans wiki pages by token-overlap.

    Uses ``re.findall(r"\\w+", ...)`` for tokenization. Ranks pages by the
    count of overlapping tokens with the question (case-insensitive). Returns
    only pages with overlap > 0, capped at top_n.

    SCHEMA.md is explicitly excluded from results — it is a meta-document,
    not wiki content.

    Note on symlinks: ``wiki_root.rglob("*.md")`` does not follow symlinks
    that escape ``wiki_root`` (Python's Path.rglob default). Pages under
    symlinks within ``wiki_root`` are included. If the wiki root contains
    adversarial symlinks this is a concern, but wiki_root is user-controlled.

    Args:
        wiki_root: Root directory of the wiki. Must be an existing directory.
    """

    def __init__(self, wiki_root: Path) -> None:
        self._wiki_root = wiki_root

    def retrieve(self, question: str, top_n: int = 5) -> list[WikiPage]:
        """Scan all markdown pages under wiki_root for token overlap.

        Args:
            question: Question string to tokenize and match against.
            top_n: Maximum pages to return.

        Returns:
            List of WikiPage objects ranked by token overlap, descending.
            Pages with zero overlap are excluded. SCHEMA.md is excluded.
        """
        question_tokens = set(re.findall(r"\w+", question.lower()))
        if not question_tokens:
            return []

        scored: list[WikiPage] = []

        for md_path in self._wiki_root.rglob("*.md"):
            # Exclude SCHEMA.md regardless of location
            if md_path.name == "SCHEMA.md":
                continue

            try:
                content = md_path.read_text(encoding="utf-8")
            except OSError:
                continue

            page_tokens = set(re.findall(r"\w+", content.lower()))
            overlap = len(question_tokens & page_tokens)
            if overlap == 0:
                continue

            # Extract title from first H1 line, fallback to stem
            title = md_path.stem
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    title = stripped[2:].strip()
                    break

            scored.append(WikiPage(
                path=md_path,
                title=title,
                content=content,
                score=float(overlap),
            ))

        # Sort descending by score
        scored.sort(key=lambda p: p.score, reverse=True)
        return scored[:top_n]


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def build_grounded_prompt(question: str, pages: list[WikiPage]) -> str:
    """Assemble a grounded query prompt.

    The prompt contains:
    1. The grounding instruction (verifiable by tests — AC-7).
    2. Numbered wiki excerpts with title and path.
    3. The question (placed AFTER excerpts to reduce prior-knowledge leakage).

    Args:
        question: Natural-language question string.
        pages: Retrieved wiki pages to include as context.

    Returns:
        Fully assembled prompt string ready for the model.
    """
    from ephemeris.prompts import GROUNDING_INSTRUCTION

    parts: list[str] = [GROUNDING_INSTRUCTION, ""]

    parts.append("## Wiki Excerpts")
    parts.append("")
    for i, page in enumerate(pages, start=1):
        parts.append(f"### Excerpt {i}: {page.title} ({page.path})")
        parts.append("")
        parts.append(page.content.strip())
        parts.append("")

    parts.append("## Question")
    parts.append("")
    parts.append(question)

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Citation formatting
# ---------------------------------------------------------------------------

def format_citations(pages: list[WikiPage]) -> str:
    """Format a list of retrieved pages as a markdown citations block.

    Each page produces one list item:
        - [<title>](<path>)

    Args:
        pages: WikiPage objects to cite.

    Returns:
        Markdown string with one list item per page, or empty string if none.
    """
    if not pages:
        return ""

    lines = ["**Sources:**", ""]
    for page in pages:
        lines.append(f"- [{page.title}]({page.path})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

def run_query(
    question: str,
    wiki_root: Path,
    model_client: "ModelClient",
    retriever: Optional[Retriever] = None,
    top_n: int = 5,
) -> QueryResult:
    """Run the full wiki query pipeline.

    Stages:
    1. Input validation (AC-6).
    2. Determine if wiki is empty (AC-3).
    3. Retrieve relevant pages (AC-2, AC-9).
    4. No-match gate (AC-2).
    5. Build grounded prompt (AC-7).
    6. Invoke model (AC-1).
    7. Attach citations (AC-5, AC-8).

    Args:
        question: Natural-language question string.
        wiki_root: Root directory of the wiki.
        model_client: Model client with an ``answer_query(prompt) -> str`` method.
        retriever: Optional custom retriever. Defaults to FilesystemRetriever.
        top_n: Maximum pages to retrieve and include in context.

    Returns:
        QueryResult with the appropriate flags and content set.
    """
    # --- Stage 1: Input validation (AC-6) ---
    if not question or not question.strip():
        return QueryResult(usage_error=True)

    # --- Stage 2: Empty-wiki check (AC-3) ---
    # Count all .md files under wiki_root excluding SCHEMA.md
    has_pages = any(
        p.name != "SCHEMA.md"
        for p in wiki_root.rglob("*.md")
    )
    if not has_pages:
        return QueryResult(empty_wiki=True)

    # --- Stage 3: Retrieval (AC-9) ---
    if retriever is None:
        retriever = FilesystemRetriever(wiki_root)

    try:
        pages = retriever.retrieve(question, top_n=top_n)
    except Exception as exc:
        return QueryResult(retrieval_error=str(exc))

    # --- Stage 4: No-match gate (AC-2) ---
    if not pages:
        return QueryResult(no_match=True)

    # --- Stage 5: Build grounded prompt (AC-7) ---
    prompt = build_grounded_prompt(question, pages)

    # --- Stage 6: Invoke model (AC-1) ---
    answer = model_client.answer_query(prompt)

    # --- Stage 7: Attach citations (AC-5, AC-8) ---
    return QueryResult(answer=answer, citations=pages)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: "list[str] | None" = None) -> int:
    """CLI entry point for ephemeris.query.

    Parses the question as a required positional argument, runs the query
    pipeline, and prints the answer with citations (or an appropriate
    message for each gate case).

    Args:
        argv: Argument list (default: sys.argv[1:]). Tests pass explicit lists.

    Returns:
        Exit code: 0 on success (including no-match and empty-wiki), non-zero
        on usage error or retrieval error.
    """
    import argparse
    import os

    def _resolve_env(var: str, default: str) -> Path:
        val = os.environ.get(var, default)
        return Path(val).expanduser()

    parser = argparse.ArgumentParser(
        description="ephemeris wiki query",
        prog="python3 -m ephemeris.query",
    )
    parser.add_argument(
        "question",
        help="Natural-language question to answer from the wiki",
    )
    parser.add_argument(
        "--wiki-root",
        dest="wiki_root",
        default=None,
        help="Wiki root directory (overrides EPHEMERIS_WIKI_ROOT env var)",
    )
    parser.add_argument(
        "--top-n",
        dest="top_n",
        type=int,
        default=5,
        help="Maximum number of pages to retrieve (default: 5)",
    )

    args = parser.parse_args(argv)

    # Resolve wiki root
    if args.wiki_root is not None:
        wiki_root = Path(args.wiki_root)
    else:
        wiki_root = _resolve_env("EPHEMERIS_WIKI_ROOT", "~/.claude/ephemeris/wiki")

    # Validate question (AC-6) — before any I/O
    if not args.question or not args.question.strip():
        print("ephemeris.query: question must not be empty or whitespace", file=sys.stderr)
        return 1

    # Early gates (AC-3 and AC-2): run before building model client so we
    # never need credentials for wiki-structural responses.
    retriever = FilesystemRetriever(wiki_root)

    # AC-3: empty wiki check
    has_pages = any(
        p.name != "SCHEMA.md"
        for p in wiki_root.rglob("*.md")
    )
    if not has_pages:
        print("Wiki is empty — no pages have been built yet.")
        print("Run /ephemeris:ingest to populate the wiki from your session history.")
        return 0

    # AC-2: no-match check — retrieve before building model client
    # AC-9: retrieval error check
    try:
        pages = retriever.retrieve(args.question, top_n=args.top_n)
    except Exception as exc:
        print(f"ephemeris.query: retrieval error — {exc}", file=sys.stderr)
        return 1

    if not pages:
        print("Cannot answer this from the wiki — no relevant pages found.")
        return 0

    # Build model client (deferred until we know we need synthesis)
    model_client_type = os.environ.get("EPHEMERIS_MODEL_CLIENT", "anthropic")
    if model_client_type == "fake":
        from ephemeris.model import FakeModelClient
        model: "ModelClient" = FakeModelClient()
    else:
        try:
            from ephemeris.model import AnthropicModelClient
            model = AnthropicModelClient()
        except Exception as exc:
            print(f"ephemeris.query: cannot create model client: {exc}", file=sys.stderr)
            return 1

    # AC-1, AC-5, AC-7, AC-8: synthesize answer with grounding
    prompt = build_grounded_prompt(args.question, pages)
    answer = model.answer_query(prompt)

    # Fabricate a result to reuse the output logic below
    result = QueryResult(answer=answer, citations=pages)

    # Success: print answer + citations (all gate cases handled above)
    print(result.answer)
    if result.citations:
        print("")
        print(format_citations(result.citations))

    return 0


if __name__ == "__main__":
    sys.exit(main())
