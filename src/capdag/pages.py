"""The page/index selection grammar shared by page-producing cartridges.

Grammar (1-based, inclusive): comma-separated segments, each one of

- ``N``   — a single page
- ``A-B`` — a contiguous range
- ``A-``  — from A to the end of the document

Semantics:

- A range extending PAST the end is clamped to the document — "give me 1-100"
  of a ten-page document renders the ten that exist, which is what the reader
  meant.
- A segment that STARTS past the end is a hard error naming both numbers: the
  request cannot be satisfied at all, and returning nothing would hide that.
- Segments emit in the order written, and a duplicate index keeps its first
  occurrence — ``5,1,3`` is a deliberate ordering, not a set.
- ``None`` or an empty spec selects every page.

Returned indices are 0-based.
"""

from __future__ import annotations

from typing import Optional

__all__ = ["parse_index_range"]


def parse_index_range(spec: Optional[str], total: int) -> list[int]:
    """Parse a page-selection spec against a document of ``total`` pages.

    Raises :class:`ValueError` with a message naming the spec and the numbers
    involved. The message is read by whoever typed the selection, so it says
    which segment and which page rather than "invalid range".
    """
    cleaned = spec.strip() if spec is not None else ""
    if not cleaned:
        return list(range(total))
    if total == 0:
        raise ValueError(
            f"index range '{cleaned}' selects from an empty document (0 pages)"
        )

    out: list[int] = []
    seen = [False] * total

    for segment in cleaned.split(","):
        segment = segment.strip()
        if not segment:
            raise ValueError(
                f"index range '{cleaned}' contains an empty segment (stray comma)"
            )
        start, end = _parse_segment(segment, cleaned, total)
        for index in range(start - 1, end):
            if not seen[index]:
                seen[index] = True
                out.append(index)

    return out


def _parse_segment(segment: str, spec: str, total: int) -> tuple[int, int]:
    """One ``N`` / ``A-B`` / ``A-`` segment as a 1-based inclusive pair."""

    def number(text: str, what: str) -> int:
        stripped = text.strip()
        try:
            value = int(stripped)
        except ValueError:
            raise ValueError(
                f"index range '{spec}': {what} '{stripped}' is not a positive number "
                "(grammar: N, A-B, A-, comma-separated)"
            ) from None
        if value < 0:
            raise ValueError(
                f"index range '{spec}': {what} '{stripped}' is not a positive number "
                "(grammar: N, A-B, A-, comma-separated)"
            )
        if value == 0:
            raise ValueError(
                f"index range '{spec}': pages are 1-based, 0 is not a valid page"
            )
        return value

    head, sep, tail = segment.partition("-")
    if not sep:
        start = end = number(segment, "page")
    else:
        start = number(head, "range start")
        end = total if not tail.strip() else number(tail, "range end")

    if start > end:
        raise ValueError(
            f"index range '{spec}': segment '{segment}' runs backwards ({start} > {end})"
        )
    if start > total:
        raise ValueError(
            f"index range '{spec}': segment '{segment}' starts at page {start} but the "
            f"document has only {total} page{'' if total == 1 else 's'}"
        )
    # Clamp the end to the document.
    return start, min(end, total)
