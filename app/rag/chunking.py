"""Heading-aware text chunking.

Two-stage strategy (documented in README):
1. split_by_headings(): break page text into sections at markdown
   heading markers — each section is single-topic and carries its
   heading path (e.g. 'Sessions > Security').
2. chunk_section(): split each section into <= max_chars pieces,
   never cutting a paragraph/code block in half (unless it alone
   exceeds the limit), with optional paragraph-boundary overlap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import Chunk


@dataclass
class Heading:
    """One heading entry (level = 1..6, text = cleaned heading text)."""
    level: int
    text: str


@dataclass
class ChunkWithHeading:
    """A chunk plus the heading path it belongs to (kept for retrieval context)."""
    content: str
    heading_path: str


def split_by_headings(content: str) -> list[tuple[str, str]]:
    """Split page text into sections at markdown heading markers (# ...).

    The extractor writes headings as '# text' (with '#' repeated per
    level), so we can reconstruct the section structure from the stored
    text alone.

    The heading hierarchy is maintained as a stack: a level-2 heading
    truncates the path back to depth 1 and appends itself, so the path
    always reflects the true document tree, e.g.:

        '# Sessions'        -> ['Sessions']
        '## Clearing'       -> ['Sessions', 'Clearing']
        '# Cache'           -> ['Cache']

    Returns:
        List of (heading_path, section_text) tuples, in document order.
        heading_path uses ' > ' as separator; the preamble before the
        first heading gets an empty path.
    """
    lines = content.split("\n")
    sections: list[tuple[str, str]] = []
    current_path: list[str] = []   # current heading hierarchy (the stack)
    current_lines: list[str] = []  # accumulated lines of the open section

    def flush() -> None:
        """Close the open section: store it if non-empty, reset the buffer."""
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((" > ".join(current_path), text))
        current_lines.clear()

    for line in lines:
        # A heading line: 1-4 '#' followed by the heading text.
        m = re.match(r"^(#{1,4}) (.+)$", line)
        if m:
            # Heading found: the previous section is complete.
            flush()
            level = len(m.group(1))
            # Cut the hierarchy stack back to the parent level, then
            # push the new heading — this handles skipping levels too.
            current_path = current_path[: level - 1]
            current_path.append(m.group(2).strip())
        else:
            current_lines.append(line)
    # Don't forget the final section after the last heading.
    flush()

    return sections


def chunk_section(
    text: str,
    max_chars: int = 1200,
    overlap_chars: int = 150,
) -> list[str]:
    """Split one section into pieces of at most max_chars characters.

    Design rules (documented in README):
    - Paragraphs (blank-line-separated blocks) are the atomic unit.
      A code block or sentence is never cut in half — the single
      exception is an oversized paragraph (usually a long code block),
      which is broken with a sliding window so even that stays usable.
    - Overlap is applied only at paragraph boundaries: the last few
      small paragraphs of a chunk are repeated at the start of the
      next one, so a concept straddling the boundary survives.

    Args:
        text: section body (no heading markers).
        max_chars: soft maximum chunk size.
        overlap_chars: how much trailing content to carry into the
            next chunk (0 disables overlap — used in config B/C of
            the evaluation).

    Returns:
        List of chunk strings.
    """
    # Split into paragraphs on blank lines; drop empties.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []   # paragraphs accumulated for the open chunk
    current_len = 0           # their total length (incl. separators)

    for para in paragraphs:
        plen = len(para)
        if plen > max_chars:
            # Oversized paragraph (usually a big code block):
            # flush what we have first so it doesn't get mixed in...
            if current:
                chunks.append("\n\n".join(current))
                current, current_len = [], 0
            # ...then slide a fixed-size window over it. step < max_chars
            # creates the overlap so the cut in the code stays recoverable.
            step = max_chars - overlap_chars
            for i in range(0, plen, step):
                chunks.append(para[i: i + max_chars])
            continue

        # Would adding this paragraph exceed the limit? If yes and we
        # already have content, close the current chunk...
        if current_len + plen + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            # ...and build the overlap: keep trailing paragraphs (in
            # order) as long as they fit within overlap_chars.
            tail: list[str] = []
            tail_len = 0
            for p in reversed(current):
                if tail_len + len(p) + 2 > overlap_chars:
                    break
                tail.insert(0, p)
                tail_len += len(p) + 2
            current = tail
            current_len = tail_len

        current.append(para)
        current_len += plen + 2  # +2 accounts for the "\n\n" separator

    # Whatever is left open is the final chunk.
    if current:
        chunks.append("\n\n".join(current))

    return chunks
