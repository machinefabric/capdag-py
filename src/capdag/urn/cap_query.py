"""Asking the fabric for a cap.

A request is not a cap. A cap takes this and gives that; a request is a QUESTION
about caps. A call always says what it sends, but a search may leave a side
unasked: "what gives me this file, whatever it takes?", "what can this input
become?". Those are not cap URNs with ``media:`` on a side — ``media:`` is the
type "anything", a claim about every input — they are queries with that side
unknown.

A query asks of what a cap GIVES for what is sent: a declared output, read
complete — what it does not mention, the cap does not give — or, for an
``effect=none`` or ``effect=patch`` cap, what it was sent with its effect applied.

:class:`CapQuery` is such a question, and :class:`MatchGrade` is how a registered
cap answers it. A cap URN read as a typed call or as a pattern is one
(:meth:`CapQuery.from_call`, :meth:`CapQuery.from_pattern`) — which is what
``CapUrn.is_dispatchable`` and ``CapUrn.accepts`` ask — and so are the questions
no cap URN can spell (:meth:`CapQuery.producing`, :meth:`CapQuery.consuming`,
:meth:`CapQuery.between`).

Every answer is decided by the proved model (``formal/CapDAG/Query.lean``).
"""

from enum import Enum
from typing import Dict, Optional

from tagged_urn import Constraint, TaggedUrn

from capdag import _formal
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


class MatchGrade(Enum):
    """How a registered cap answers a :class:`CapQuery`."""

    #: Guaranteed, and exactly what was asked on every side that was asked.
    EXACT = "exact"
    #: Guaranteed: whatever the cap takes and gives, it is what was asked.
    GUARANTEED = "guaranteed"
    #: Not guaranteed and not excluded: only running it tells. For exploring;
    #: a call is never routed on it.
    POSSIBLE = "possible"
    #: Excluded.
    NONE = "none"

    def is_guaranteed(self) -> bool:
        """Whether routing may act on it."""
        return self in (MatchGrade.EXACT, MatchGrade.GUARANTEED)

    def is_possible(self) -> bool:
        """Whether a search should show it."""
        return self is not MatchGrade.NONE


def _tag_pattern(tags: Optional[Dict[str, Constraint]]) -> TaggedUrn:
    """The cap-tag pattern a query asks for: ``cap:`` with these tags, as
    constraints. None, or an empty map, asks for none."""
    return TaggedUrn(CapUrn.PREFIX, dict(tags or {}))


class CapQuery:
    """A question about caps."""

    def __init__(self, formal: "_formal.WfQuery", asked: str) -> None:
        self._formal = formal
        self._asked = asked

    def __repr__(self) -> str:
        return f"CapQuery({self._asked!r})"

    def __str__(self) -> str:
        return self._asked

    @classmethod
    def from_call(cls, call: CapUrn) -> "CapQuery":
        """The cap URN ``call``, read as a typed call: it sends what its input
        says — ``media:``, if it says nothing, is anything — and asks for its
        output, tags and effect. What ``CapUrn.is_dispatchable`` asks."""
        return cls(_formal.query_of_call(call.formal), f"call {call}")

    @classmethod
    def from_pattern(cls, pattern: CapUrn) -> "CapQuery":
        """The cap URN ``pattern``, read as a pattern over caps: caps taking
        within its input, everything they give of the type its output names; an
        output it leaves open asks nothing. What ``CapUrn.accepts`` asks."""
        return cls(_formal.query_of_pattern(pattern.formal), f"pattern {pattern}")

    @classmethod
    def producing(cls, output: MediaUrn, tags: Optional[Dict[str, Constraint]] = None) -> "CapQuery":
        """Caps that GIVE ``output``, whatever they take, with the cap-tags
        ``tags`` asks for."""
        return cls(
            _formal.query_producing(output.inner().formal, _tag_pattern(tags).formal),
            f"anything giving {output}",
        )

    @classmethod
    def consuming(cls, input: MediaUrn, tags: Optional[Dict[str, Constraint]] = None) -> "CapQuery":
        """Caps that TAKE ``input``, whatever they give: what this input can
        become in one step."""
        return cls(
            _formal.query_consuming(input.inner().formal, _tag_pattern(tags).formal),
            f"anything taking {input}",
        )

    @classmethod
    def between(
        cls, input: MediaUrn, output: MediaUrn, tags: Optional[Dict[str, Constraint]] = None
    ) -> "CapQuery":
        """Caps that take ``input`` and give ``output``: nothing unknown."""
        return cls(
            _formal.query_between(
                input.inner().formal, output.inner().formal, _tag_pattern(tags).formal
            ),
            f"anything taking {input} and giving {output}",
        )

    def admits(self, cap: CapUrn) -> bool:
        """Whether ``cap`` is guaranteed to be what is asked."""
        return _formal.query_admits(self._formal, cap.formal)

    def may_admit(self, cap: CapUrn) -> bool:
        """Whether ``cap`` could be what is asked."""
        return _formal.query_may_admit(self._formal, cap.formal)

    def grade(self, cap: CapUrn) -> MatchGrade:
        """How ``cap`` answers."""
        answer = _formal.query_grade(self._formal, cap.formal)
        if isinstance(answer, _formal.GradeExact):
            return MatchGrade.EXACT
        if isinstance(answer, _formal.GradeGuaranteed):
            return MatchGrade.GUARANTEED
        if isinstance(answer, _formal.GradePossible):
            return MatchGrade.POSSIBLE
        if isinstance(answer, _formal.GradeNone_):
            return MatchGrade.NONE
        raise RuntimeError(f"the model answered with a grade this mirror does not know: {answer!r}")
