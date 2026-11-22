"""Flat Tag-Based Cap Identifier System

This module provides a flat, tag-based cap URN system that replaces
hierarchical naming with key-value tags to handle cross-cutting concerns and
multi-dimensional cap classification.

Cap URNs use the tagged URN format with "cap" prefix. Missing `in` or `out`
tags default to "media:" (wildcard). Explicit "*" also expands to "media:".
"""

from enum import Enum
from typing import Dict, List, Optional
from tagged_urn import TaggedUrn, TaggedUrnBuilder, TaggedUrnError
from capdag.urn.media_urn import MediaUrn, MediaUrnError
from capdag import _formal


class CapUrnError(Exception):
    """Base exception for cap URN errors"""
    pass


class IllegalDeclarationError(CapUrnError):
    """A cap that parses but cannot be declared: the bare top form, or an
    ``effect=none`` cap whose input is not inside its output."""
    pass


class CapKind(Enum):
    """Functional category of a cap, derived from all three axes
    (``in``, ``out``, and the remaining tags).

    The classification is **logical** — the dispatch protocol does
    not branch on ``CapKind``. Exposed so tools, UIs, planners, and
    tests can reason about a cap's role without re-deriving the rules.

    ``media:void`` is the **unit type** (the nullary value, no
    meaningful data). ``media:`` is the **top type** (the universal
    wildcard). With those anchors the five kinds fall out:

    +-----------+--------------+--------------+------------+--------------+
    | Kind      | in           | out          | other tags | reads as     |
    +===========+==============+==============+============+==============+
    | Identity  | ``media:``   | ``media:``   | none       | ``A → A``    |
    | Source    | ``media:void``| not void    | any        | ``() → B``   |
    | Sink      | not void     | ``media:void``| any       | ``A → ()``   |
    | Effect    | ``media:void``| ``media:void``| any      | ``() → ()``  |
    | Transform | anything else                                          |
    +-----------+--------------+--------------+------------+--------------+

    Identity is the **fully generic** cap on every axis: input wide
    open, output wide open, no operation/metadata tags. Adding any tag
    specifies something on the third axis and demotes the morphism to
    a Transform whose in/out happen to be the wildcards.
    """

    IDENTITY = "identity"
    SOURCE = "source"
    SINK = "sink"
    EFFECT = "effect"
    TRANSFORM = "transform"


class CapEffect(Enum):
    DECLARED = "declared"
    NONE = "none"
    PATCH = "patch"
    ANY = "?"


class CapUrn:
    """A cap URN using flat, ordered tags with required direction specifiers

    Direction (in→out) is integral to a cap's identity. The `in_urn` and `out_urn`
    fields specify the input and output media URNs respectively.

    Examples:
    - `cap:in="media:binary";generate;out="media:binary";target=thumbnail`
    - `cap:in="media:void";dimensions;out="media:integer"`
    - `cap:in="media:string";out="media:object";key="Value With Spaces"`
    """

    PREFIX = "cap"

    def __init__(self, in_urn: str, out_urn: str, tags: Dict[str, str], effect: str = "declared"):
        """Create a new cap URN from direction specs and additional tags

        Keys are normalized to lowercase; values are preserved as-is.
        in_urn and out_urn are required direction specifiers (media URN strings).
        Specs are canonicalized through MediaUrn parsing for consistent tag ordering.
        'in' and 'out' keys in tags dict are filtered out.
        """
        # Canonicalize specs through MediaUrn parsing for consistent tag ordering.
        # Invalid direction specs are a hard error; silent fallthrough would hide
        # broken CapUrn construction and diverge from the reference regime.
        if in_urn and in_urn not in ("media:", "*"):
            if not in_urn.startswith("media:"):
                raise CapUrnError(f"Invalid media URN for in spec '{in_urn}'")
            try:
                in_urn = str(MediaUrn.from_string(in_urn))
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for in spec '{in_urn}': {e}") from e
        if out_urn and out_urn not in ("media:", "*"):
            if not out_urn.startswith("media:"):
                raise CapUrnError(f"Invalid media URN for out spec '{out_urn}'")
            try:
                out_urn = str(MediaUrn.from_string(out_urn))
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for out spec '{out_urn}': {e}") from e
        # Filter out 'in' and 'out' from tags, normalize remaining keys
        self.in_urn = "media:" if in_urn in ("", "*") else in_urn
        self.out_urn = "media:" if out_urn in ("", "*") else out_urn
        self.effect = self._normalize_effect_value(effect)
        self.tags: Dict[str, str] = {
            k.lower(): v
            for k, v in tags.items()
            if k.lower() not in ("in", "out", "effect")
        }
        self._validate_non_structural_tags(self.tags)
        self._assemble()

    @staticmethod
    def _normalize_effect_value(raw: Optional[str]) -> str:
        if raw is None:
            return CapEffect.DECLARED.value
        if raw in ("*", "?"):
            return CapEffect.ANY.value
        if raw in (CapEffect.DECLARED.value, CapEffect.NONE.value, CapEffect.PATCH.value):
            return raw
        if raw == "":
            raise CapUrnError("Empty value for 'effect' tag is not allowed")
        raise CapUrnError(
            f"Unsupported effect '{raw}'. Supported values are declared, none, patch, or explicit unconstrained ?effect/effect=*"
        )

    @staticmethod
    def _validate_non_structural_tags(tags: Dict[str, str]) -> None:
        # Round-trip the tags through the tagged-urn layer so its key/value
        # constraints (e.g. a purely numeric tag key) are enforced. Surface any
        # violation as CapUrnError — the cap-URN API must raise its own error
        # type, not leak the substrate's TaggedUrnError. Mirrors the mirrors
        # (Go's capUrnErrorFromTaggedUrn → ErrorNumericKey) and matches the
        # wrapping from_string() already applies.
        try:
            TaggedUrn.from_string(TaggedUrn("cap", tags).to_string())
        except TaggedUrnError as e:
            raise CapUrnError(f"Invalid cap URN: {e}") from e

    _EFFECTS = {
        CapEffect.DECLARED.value: _formal.EffectDeclared(),
        CapEffect.NONE.value: _formal.EffectNone_(),
        CapEffect.PATCH.value: _formal.EffectPatch(),
        CapEffect.ANY.value: _formal.EffectUnspecified(),
    }

    def _assemble(self) -> None:
        """Build the same cap on the proved model's side — its three URNs and its
        effect — from exactly the fields, and check admissibility. Dispatch,
        acceptance, equivalence and specificity are asked of it, through the module
        generated from ../formal (``capdag._formal``). Every constructor ends here,
        and nothing changes the fields afterwards, so it can never describe a
        different cap from the one beside it."""
        self._formal = _formal.WfCap(
            MediaUrn.from_string(self.in_urn).inner().formal,
            MediaUrn.from_string(self.out_urn).inner().formal,
            TaggedUrn(self.PREFIX, self.tags).formal,
            self._EFFECTS[self.effect],
        )
        self._validate_admissible()

    def _validate_admissible(self) -> None:
        """Refuse a cap that cannot be declared, as the model decides
        (``Cap.illegal``): the bare top form, and an ``effect=none`` cap whose
        input is not inside its output."""
        illegal = _formal.cap_illegal(self._formal)
        if illegal is None:
            return
        if isinstance(illegal, _formal.IllegalBareTop):
            raise IllegalDeclarationError(
                "illegal bare top cap; use cap:effect=none for identity, or declare a non-vacuous input/output/effect/tag"
            )
        if isinstance(illegal, _formal.IllegalNoneNotInside):
            raise IllegalDeclarationError(
                f"effect=none requires declared input '{self.in_urn}' to conform to declared output '{self.out_urn}'"
            )
        raise RuntimeError(f"the model named a reason a cap is illegal that this mirror does not know: {illegal!r}")

    @classmethod
    def _from_preserved_parts(
        cls,
        in_urn: str,
        out_urn: str,
        tags: Dict[str, str],
        effect: str,
    ) -> "CapUrn":
        normalized_tags: Dict[str, str] = {
            k.lower(): v
            for k, v in tags.items()
            if k.lower() not in ("in", "out", "effect")
        }
        cls._validate_non_structural_tags(normalized_tags)

        if in_urn and in_urn != "media:":
            if not in_urn.startswith("media:"):
                raise CapUrnError(f"Invalid media URN for in spec '{in_urn}'")
            try:
                MediaUrn.from_string(in_urn)
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for in spec '{in_urn}': {e}") from e

        if out_urn and out_urn != "media:":
            if not out_urn.startswith("media:"):
                raise CapUrnError(f"Invalid media URN for out spec '{out_urn}'")
            try:
                MediaUrn.from_string(out_urn)
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for out spec '{out_urn}': {e}") from e

        instance = object.__new__(cls)
        instance.in_urn = "media:" if in_urn == "" else in_urn
        instance.out_urn = "media:" if out_urn == "" else out_urn
        instance.effect = cls._normalize_effect_value(effect)
        instance.tags = normalized_tags
        instance._assemble()
        return instance

    @classmethod
    def from_tags(cls, tags: Dict[str, str]) -> "CapUrn":
        """Create a cap URN from tags map that must contain 'in' and 'out'

        This is a convenience method for deserialization.
        Raises CapUrnError if 'in' or 'out' is missing.
        """
        tags_copy = tags.copy()
        in_urn = tags_copy.pop("in", "media:")
        out_urn = tags_copy.pop("out", "media:")
        effect = tags_copy.pop("effect", "declared")
        return cls(in_urn, out_urn, tags_copy, effect=effect)

    @staticmethod
    def _process_direction_tag(tagged: TaggedUrn, tag_name: str) -> str:
        """Process a direction tag (in or out) with wildcard expansion

        - Missing tag → "media:" (wildcard)
        - tag=* → "media:" (wildcard)
        - tag= (empty) → error
        - tag=value → value (validated later)
        """
        value = tagged.get_tag(tag_name)
        if value is None:
            # Tag is missing - default to media: wildcard
            return "media:"
        elif value == "*":
            # Replace * with media: wildcard
            return "media:"
        elif value == "":
            # Empty value is not allowed (in= or out= with nothing after =)
            raise CapUrnError(f"Empty value for '{tag_name}' tag is not allowed")
        else:
            # Regular value - will be validated as MediaUrn later
            return value

    @classmethod
    def from_string(cls, s: str) -> "CapUrn":
        """Create a cap URN from a string representation

        Format: `cap:in="media:...";out="media:...";key1=value1;...`
        The "cap:" prefix is mandatory.
        Missing 'in' or 'out' tags default to "media:" (wildcard).
        Trailing semicolons are optional and ignored.
        Tags are automatically sorted alphabetically for canonical form.

        Case handling (inherited from TaggedUrn):
        - Keys: Always normalized to lowercase
        - Unquoted values: Normalized to lowercase
        - Quoted values: Case preserved exactly as specified
        """
        # Parse using TaggedUrn
        try:
            tagged = TaggedUrn.from_string(s)
        except TaggedUrnError as e:
            raise CapUrnError(f"Invalid cap URN: {e}") from e

        # Verify cap prefix
        if tagged.get_prefix() != cls.PREFIX:
            raise CapUrnError(f"Cap identifier must start with '{cls.PREFIX}:'")

        # Process direction tags with wildcard expansion
        in_urn = cls._process_direction_tag(tagged, "in")
        out_urn = cls._process_direction_tag(tagged, "out")

        # Validate and canonicalize in/out specs as media URNs.
        # Parse through MediaUrn and re-serialize to get canonical tag ordering.
        # After processing, "media:" is the wildcard (not "*").
        if in_urn != "media:":
            try:
                in_media = MediaUrn.from_string(in_urn)
                in_urn = str(in_media)
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for in spec '{in_urn}': {e}") from e

        if out_urn != "media:":
            try:
                out_media = MediaUrn.from_string(out_urn)
                out_urn = str(out_media)
            except Exception as e:
                raise CapUrnError(f"Invalid media URN for out spec '{out_urn}': {e}") from e

        effect = cls._normalize_effect_value(tagged.tags.get("effect"))
        tags = {k: v for k, v in tagged.tags.items() if k not in ("in", "out", "effect")}
        return cls(in_urn, out_urn, tags, effect=effect)

    def _build_tagged_urn(self) -> TaggedUrn:
        """Build a TaggedUrn representation of this CapUrn

        Internal helper for serialization and tag manipulation. ``in`` and
        ``out`` are emitted only when they refine beyond the trivial wildcard
        ``media:``. ``effect=declared`` is omitted because it is the default
        on admissible caps. ``effect=none`` is never omitted; identity is the
        explicit ``cap:effect=none``, never bare ``cap:``.
        """
        from .media_urn import MEDIA_IDENTITY

        # Constraints from the underlying tagged-urn layer (e.g. a purely
        # numeric tag key) are cap-URN validity failures at this boundary, so
        # surface them as CapUrnError — the same wrapping from_string() applies
        # to parse-time TaggedUrnError. Letting the raw TaggedUrnError escape
        # would make the cap-URN API leak its substrate's exception type, which
        # the mirrors (Go's capUrnErrorFromTaggedUrn / ErrorNumericKey) do not.
        try:
            builder = TaggedUrnBuilder(self.PREFIX)
            if self.in_urn != MEDIA_IDENTITY:
                builder.tag("in", self.in_urn)
            if self.out_urn != MEDIA_IDENTITY:
                builder.tag("out", self.out_urn)
            if self.effect != CapEffect.DECLARED.value:
                builder.tag("effect", self.effect)

            for k, v in self.tags.items():
                builder.tag(k, v)

            return builder.build_allow_empty()
        except TaggedUrnError as e:
            raise CapUrnError(f"Invalid cap URN: {e}") from e

    def tags_to_string(self) -> str:
        """Serialize just the tags portion (without "cap:" prefix)

        Returns tags in canonical form with proper quoting and sorting.
        """
        return self._build_tagged_urn().tags_to_string()

    def to_string(self) -> str:
        """Get the canonical string representation of this cap URN

        Always includes "cap:" prefix.
        All tags (including in/out) are sorted alphabetically.
        No trailing semicolon in canonical form.
        Values are quoted only when necessary (smart quoting via TaggedUrn).
        """
        return self._build_tagged_urn().to_string()

    def get_tag(self, key: str) -> Optional[str]:
        """Get a specific tag value

        Key is normalized to lowercase for lookup.
        For structural coordinates, returns the dedicated fields.
        """
        key_lower = key.lower()
        if key_lower == "in":
            return self.in_urn
        elif key_lower == "out":
            return self.out_urn
        elif key_lower == "effect":
            return self.effect
        else:
            return self.tags.get(key_lower)

    def in_spec(self) -> str:
        """Get the input media URN string"""
        return self.in_urn

    def out_spec(self) -> str:
        """Get the output media URN string"""
        return self.out_urn

    def effect_spec(self) -> str:
        return self.effect

    def effect_kind(self) -> CapEffect:
        return CapEffect(self.effect)

    def in_media_urn(self) -> MediaUrn:
        """Get the input as a parsed MediaUrn"""
        return MediaUrn.from_string(self.in_urn)

    def out_media_urn(self) -> MediaUrn:
        """Get the output as a parsed MediaUrn"""
        return MediaUrn.from_string(self.out_urn)

    def kind(self) -> CapKind:
        in_media = self.in_media_urn()
        out_media = self.out_media_urn()

        in_void = in_media.is_void()
        out_void = out_media.is_void()
        in_top = in_media.is_top()
        out_top = out_media.is_top()
        # self.tags does NOT include in/out; those live in self.in_urn /
        # self.out_urn. So `not self.tags` correctly tests "no tags
        # beyond the directional axes."
        no_extra_tags = not self.tags

        if in_top and out_top and no_extra_tags and self.effect_kind() == CapEffect.NONE:
            return CapKind.IDENTITY
        if in_void and out_void:
            return CapKind.EFFECT
        if in_void:
            return CapKind.SOURCE
        if out_void:
            return CapKind.SINK
        return CapKind.TRANSFORM

    def has_tag(self, key: str, value: str) -> bool:
        """Check if this cap has a specific tag with a specific value

        Key is normalized to lowercase; value comparison is case-sensitive.
        For structural coordinates, checks the dedicated fields.
        """
        key_lower = key.lower()
        if key_lower == "in":
            return self.in_urn == value
        elif key_lower == "out":
            return self.out_urn == value
        elif key_lower == "effect":
            return self.effect == value
        else:
            return self.tags.get(key_lower) == value

    def has_marker_tag(self, tag_name: str) -> bool:
        """Check if a marker tag (solo tag with no value) is present.
        A marker tag is stored as key="*" in the cap URN.
        Example: `cap:constrained;...` has marker tag "constrained"
        """
        return self.tags.get(tag_name.lower()) == "*"

    def with_tag(self, key: str, value: str) -> "CapUrn":
        """Add or update a tag

        Key is normalized to lowercase; value is preserved as-is.
        Note: Cannot modify structural coordinates here.
        Returns error if value is empty (use "*" for wildcard).
        """
        if not value:
            raise CapUrnError(f"Empty value for key '{key}' (use '*' for wildcard)")

        key_lower = key.lower()
        if key_lower in ("in", "out", "effect"):
            raise CapUrnError(
                f"reserved structural key '{key_lower}' must be changed via dedicated CapUrn accessors"
            )

        new_tags = self.tags.copy()
        new_tags[key_lower] = value
        return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, new_tags, effect=self.effect)

    def with_in_spec(self, in_urn: str) -> "CapUrn":
        """Create a new cap URN with a different input spec"""
        return CapUrn._from_preserved_parts(in_urn, self.out_urn, self.tags, effect=self.effect)

    def with_out_spec(self, out_urn: str) -> "CapUrn":
        """Create a new cap URN with a different output spec"""
        return CapUrn._from_preserved_parts(self.in_urn, out_urn, self.tags, effect=self.effect)

    def with_effect(self, effect: CapEffect) -> "CapUrn":
        return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, self.tags, effect=effect.value)

    def without_tag(self, key: str) -> "CapUrn":
        """Remove a tag

        Key is normalized to lowercase for case-insensitive removal.
        Note: Cannot remove structural coordinates.
        """
        key_lower = key.lower()
        if key_lower in ("in", "out", "effect"):
            raise CapUrnError(
                f"CapUrn.without_tag cannot remove reserved structural key '{key_lower}'"
            )

        new_tags = self.tags.copy()
        new_tags.pop(key_lower, None)
        return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, new_tags, effect=self.effect)

    def accepts(self, cap: "CapUrn") -> bool:
        """Whether ``cap`` fits this cap read as a PATTERN over caps — what a
        search asks: ``cap``'s input is within this pattern's, its output is
        within the pattern's — everything it gives is of the type the pattern
        names, its declared output read complete — its effect is the pattern's
        (a pattern's ``?effect`` fits any), and its cap-tags — complete: a cap
        has the tags it has — satisfy the pattern's. ``cap:out="media:ext=pdf"``
        fits caps giving ``media:ext=pdf`` or ``media:document;ext=pdf``, and
        not one giving ``media:``, which gives a thing with no tags.

        An output the pattern leaves open asks nothing. ``cap:candle`` fits
        every cap tagged ``candle``, whatever it gives.

        Decided by the proved model (``CapDAG.Exec.accepts``, which is
        ``CapDAG.fits``). For a question no cap URN can spell — "what gives this,
        whatever it takes" — ask a :class:`capdag.CapQuery`.
        """
        return _formal.accepts(self._formal, cap._formal)

    def conforms_to(self, pattern: "CapUrn") -> bool:
        """Whether this cap fits ``pattern``: ``pattern.accepts(self)``."""
        return pattern.accepts(self)

    def is_dispatchable(self, request: "CapUrn") -> bool:
        """Whether this candidate SERVES ``request`` — the predicate routing and
        dispatch act on.

        The request is a call: it sends what its input says and asks for its
        output. The candidate takes at least what the call sends; what it gives
        for that is inside what the call asks for; it has the effect asked for
        unless the call says ``?effect``; and it has the cap-tags asked for —
        its own tags being complete, so a request for ``!x`` is served by a
        candidate that does not mention ``x``, and a candidate may carry tags
        the request does not ask about.

        What the candidate gives is what its effect says: a declared output,
        read complete — what it does not mention, the candidate does not give —
        or, for ``effect=none`` and ``effect=patch``, what the call sends with
        the effect applied. A call always says what it sends: one whose input
        is ``media:`` (or omitted) sends anything, and only a candidate that
        takes anything serves it.

        This is a guarantee. What only could serve does not; see
        :meth:`may_dispatch` and :meth:`capdag.CapQuery.grade`.

        Decided by the proved model (``CapDAG.Exec.dispatch``, which is
        ``CapDAG.serves``). Not symmetric.
        """
        return _formal.dispatch(self._formal, request._formal)

    @staticmethod
    def select(candidates: List["CapUrn"], request: "CapUrn") -> Optional[int]:
        """The position in ``candidates`` of the cap the proved ranking chooses
        to serve ``request`` (``CapDAG.Exec.select``): among the candidates
        that serve it, the one whose ranking key is least, and of equal keys
        the first. ``None`` when none serves it."""
        chosen = _formal.select([c._formal for c in candidates], request._formal)
        if chosen is None:
            return None
        # The model returns the cap it chose; it is the first candidate that
        # serves the request with the chosen cap's key, since the model keeps
        # the first of equal keys.
        key = _formal.ranking_key(chosen, request._formal)
        for index, candidate in enumerate(candidates):
            if candidate.is_dispatchable(request) and candidate._ranking_key(request) == key:
                return index
        raise RuntimeError(
            f"capdag: the model chose a cap to serve {request} that is none of the candidates"
        )

    def _ranking_key(self, request: "CapUrn") -> tuple:
        """This candidate's key in the proved ranking for ``request``
        (``CapDAG.Exec.rankingKey``): the smaller key ranks first."""
        return _formal.ranking_key(self._formal, request._formal)

    def may_dispatch(self, request: "CapUrn") -> bool:
        """Whether this candidate COULD serve ``request``: not guaranteed, not
        excluded. For exploring what the fabric might do — never for routing a
        call, which must be served."""
        return _formal.may_dispatch(self._formal, request._formal)

    def flows_into(self, next_cap: "CapUrn") -> bool:
        """Whether what this cap gives, ``next_cap`` takes: the edge of a route."""
        return _formal.flows(self._formal, next_cap._formal)

    def may_flow_into(self, next_cap: "CapUrn") -> bool:
        """Whether what this cap gives COULD be something ``next_cap`` takes: an
        edge a search may explore and a run has to check."""
        return _formal.may_flow(self._formal, next_cap._formal)

    def is_comparable(self, other: "CapUrn") -> bool:
        """Whether the two caps are on one chain: one stands in for the other on
        every side. Both are read as descriptions — nothing is unknown."""
        return _formal.comparable(self._formal, other._formal)

    def is_equivalent(self, other: "CapUrn") -> bool:
        """Whether the two are the SAME cap: equivalent on every side, the
        effects agreeing. What resolving a name to its cap asks. Nothing is read
        as unknown: a cap that promises no particular output is not the same
        cap as one that promises pages, though as a pattern it fits it."""
        return _formal.equivalent(self._formal, other._formal)

    @property
    def formal(self) -> "_formal.WfCap":
        """This cap on the proved model's side, for generated code."""
        return self._formal

    def accepts_str(self, request_str: str) -> bool:
        """Check if this cap accepts a string-specified request"""
        request = CapUrn.from_string(request_str)
        return self.accepts(request)

    def conforms_to_str(self, cap_str: str) -> bool:
        """Check if this cap conforms to a string-specified cap"""
        cap = CapUrn.from_string(cap_str)
        return self.conforms_to(cap)

    def infer_runtime_output_media(self, runtime_input: MediaUrn) -> MediaUrn:
        declared_in = self.in_media_urn()
        declared_out = self.out_media_urn()
        # A runtime media URN is the media of a value that exists, so it is read
        # complete: it SATISFIES the declared type, or does not.
        if not runtime_input.satisfies(declared_in):
            raise CapUrnError(
                f"Runtime input '{runtime_input}' does not conform to declared input '{declared_in}'"
            )
        if self.effect_kind() == CapEffect.ANY:
            raise CapUrnError("Cannot infer runtime output for an unconstrained effect request")
        # What the cap gives for it is the proved model's (CapDAG.Exec.capGives,
        # which is Cap.gives): its declared output, the input itself, or the
        # input with the keys the declared input and output disagree on set to
        # the output's.
        given = _formal.cap_gives(self._formal, runtime_input.inner().formal)
        runtime_out = MediaUrn(TaggedUrn("media", dict(given)))
        if not runtime_out.satisfies(declared_out):
            raise CapUrnError(
                f"Inferred runtime output '{runtime_out}' does not conform to declared output '{declared_out}'"
            )
        return runtime_out

    def is_conformant_runtime_output(
        self, runtime_input: MediaUrn, runtime_output: MediaUrn
    ) -> bool:
        """Does an actually-emitted runtime output keep this cap's effect
        contract for the given runtime input?

        This is THE effect-audit predicate: every check of "did the cap emit
        what its effect promised" goes through it, so the contract has exactly
        one definition — the proved model's (``CapDAG.Exec.audit``, which is
        ``Cap.audits``). Both media are those of values that exist, read
        complete:

        - ``effect=declared`` promises its declared ``out=``, read complete —
          what it does not mention, the cap does not give — so the emission
          must be inside it, read complete: a cap declaring
          ``out=media:record`` may emit ``media:record``, and not
          ``media:enc=utf8;fmt=json;record``.
        - ``effect=none`` and ``effect=patch`` give exactly what their effect
          makes of the input (:meth:`infer_runtime_output_media`), so the
          emission must be that.

        Raises (rather than returning ``False``) when the input itself is
        wrong: the runtime input does not conform to the declared input, the
        effect is the unconstrained request form (``?effect``), or the URN
        state is internally inconsistent — those are upstream contract breaks,
        not emission mismatches, and must surface as such.
        """
        if self.effect_kind() == CapEffect.ANY:
            raise CapUrnError(
                "Cannot audit an emission against an unconstrained effect request"
            )
        self.infer_runtime_output_media(runtime_input)
        return _formal.audit(
            self._formal, runtime_input.inner().formal, runtime_output.inner().formal
        )

    # Per-axis weights for cap-URN specificity. Two orders of
    # magnitude separate each axis to keep them in distinct digit
    # slots while folding into a single comparable integer.
    WEIGHT_OUT = 10_000
    WEIGHT_IN = 100

    def specificity(self) -> int:
        """Calculate specificity score for cap matching.

        Weighted sum of the per-tag truth-table score across the
        three axes (``out``, ``in``, ``y``):

        .. code-block:: text

            spec_C(c) = WEIGHT_OUT * spec_U(c.out)
                      + WEIGHT_IN  * spec_U(c.in)
                      +              spec_U(c.y)

        Per-tag scoring (see :func:`tagged_urn.score_tag_value`):

        +--------------------+-------+----------------------+
        | Stored tag value   | Score | Form                 |
        +====================+=======+======================+
        | ``"?"``            | 0     | ``?x`` no constraint |
        | starts with ``?=`` | 1     | ``x?=v``             |
        | ``"*"``            | 2     | ``x`` (``x=*``)      |
        | starts with ``!=`` | 3     | ``x!=v``             |
        | exact value        | 4     | ``x=v``              |
        | ``"!"``            | 5     | ``!x``               |
        +--------------------+-------+----------------------+

        The lexicographic priority ``(out, in, y)`` reflects the
        routing intent: producing different things is the largest
        semantic difference between two caps; consuming different
        things is next; descriptive y-axis metadata is last.

        Computed by the proved model (``CapDAG.Exec.specificity``).
        """
        return _formal.specificity(self._formal)

    def is_more_specific_than(self, other: "CapUrn") -> bool:
        """Check if this cap is more specific than another"""
        return self.specificity() > other.specificity()

    def with_wildcard_tag(self, key: str) -> "CapUrn":
        """Create a wildcard version by replacing specific values with wildcards

        For structural coordinates, sets the explicit unconstrained value.
        """
        key_lower = key.lower()

        if key_lower == "in":
            return CapUrn._from_preserved_parts("media:", self.out_urn, self.tags, effect=self.effect)
        elif key_lower == "out":
            return CapUrn._from_preserved_parts(self.in_urn, "media:", self.tags, effect=self.effect)
        elif key_lower == "effect":
            return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, self.tags, effect=CapEffect.ANY.value)
        else:
            if key_lower in self.tags:
                new_tags = self.tags.copy()
                new_tags[key_lower] = "*"
                return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, new_tags, effect=self.effect)
            else:
                return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, self.tags, effect=self.effect)

    def subset(self, keys: List[str]) -> "CapUrn":
        """Create a subset cap with only specified tags

        Structural coordinates remain intact; y-axis tags are filtered.
        """
        new_tags = {}
        for key in keys:
            key_lower = key.lower()
            if key_lower in ("in", "out", "effect"):
                continue
            if key_lower in self.tags:
                new_tags[key_lower] = self.tags[key_lower]

        return CapUrn._from_preserved_parts(self.in_urn, self.out_urn, new_tags, effect=self.effect)

    def merge(self, other: "CapUrn") -> "CapUrn":
        """Merge with another cap (other takes precedence for conflicts)

        Direction specs from other override this one's.
        """
        new_tags = self.tags.copy()
        new_tags.update(other.tags)

        return CapUrn._from_preserved_parts(other.in_urn, other.out_urn, new_tags, effect=other.effect)

    @staticmethod
    def canonical(cap_urn: str) -> str:
        """Get the canonical form of a cap URN string"""
        cap = CapUrn.from_string(cap_urn)
        return cap.to_string()

    @staticmethod
    def canonical_option(cap_urn: Optional[str]) -> Optional[str]:
        """Get the canonical form of an optional cap URN string"""
        if cap_urn is not None:
            cap = CapUrn.from_string(cap_urn)
            return cap.to_string()
        return None

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"CapUrn('{self.to_string()}')"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CapUrn):
            return False
        return (
            self.in_urn == other.in_urn
            and self.out_urn == other.out_urn
            and self.effect == other.effect
            and self.tags == other.tags
        )

    def __hash__(self) -> int:
        return hash((self.in_urn, self.out_urn, self.effect, tuple(sorted(self.tags.items()))))

    #: Where each effect stands in the order of caps: as the reference
    #: declares them, the unspecified effect last.
    _EFFECT_ORDER = {
        CapEffect.DECLARED.value: 0,
        CapEffect.NONE.value: 1,
        CapEffect.PATCH.value: 2,
        CapEffect.ANY.value: 3,
    }

    def ordering_key(self) -> tuple:
        """The key cap URNs are ordered by: `in=` and `out=` as media URNs
        (see ``MediaUrn.ordering_key``), then the effect, then the remaining
        tags as (key, stored value) pairs in key order. This is the
        reference's structural order, not the order of the canonical text:
        the text would fold the four axes into one string and order them by
        whatever characters happen to meet."""
        return (
            self.in_media_urn().ordering_key(),
            self.out_media_urn().ordering_key(),
            self._EFFECT_ORDER[self.effect],
            tuple(sorted(self.tags.items())),
        )

    def _cmp_key(self) -> tuple:
        return self.ordering_key()

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, CapUrn):
            return NotImplemented
        return self._cmp_key() < other._cmp_key()

    def __le__(self, other: object) -> bool:
        if not isinstance(other, CapUrn):
            return NotImplemented
        return self._cmp_key() <= other._cmp_key()

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, CapUrn):
            return NotImplemented
        return self._cmp_key() > other._cmp_key()

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, CapUrn):
            return NotImplemented
        return self._cmp_key() >= other._cmp_key()


class CapMatcher:
    """Choosing among registered caps for a request, as the proved ranking does
    (``CapDAG.Exec.select``): only the caps that serve the request
    (:meth:`CapUrn.is_dispatchable`) are considered, the one whose specificity
    is closest to the request's ranks first (an exact match, then the nearest
    refinement, then the nearest fallback), and of caps that rank alike the
    first registered comes first. ``caps`` is in registration order."""

    @staticmethod
    def find_best_match(caps: List[CapUrn], request: CapUrn) -> Optional[CapUrn]:
        """The cap the ranking chooses to serve ``request``
        (:meth:`CapUrn.select`), or ``None`` when no cap serves it."""
        index = CapUrn.select(caps, request)
        return None if index is None else caps[index]

    @staticmethod
    def find_all_matches(caps: List[CapUrn], request: CapUrn) -> List[CapUrn]:
        """Every cap that serves ``request``, in ranking order: the one
        :meth:`find_best_match` chooses first, and caps that rank alike in
        registration order."""
        ranked = [(cap._ranking_key(request), cap) for cap in caps if cap.is_dispatchable(request)]
        # A stable sort, so caps of equal key keep their registration order.
        ranked.sort(key=lambda entry: entry[0])
        return [cap for _, cap in ranked]

    @staticmethod
    def are_compatible(caps1: List[CapUrn], caps2: List[CapUrn]) -> bool:
        """Whether two cap sets overlap: some cap of one is comparable with
        some cap of the other (:meth:`CapUrn.is_comparable`)."""
        return any(c1.is_comparable(c2) for c1 in caps1 for c2 in caps2)


class CapUrnBuilder:
    """Builder for creating cap URNs fluently"""

    def __init__(self):
        """Create a new builder (in_spec and out_spec are required)"""
        self._in_urn: Optional[str] = None
        self._out_urn: Optional[str] = None
        self._effect: str = CapEffect.DECLARED.value
        self._tags: Dict[str, str] = {}

    def in_spec(self, in_urn: str) -> "CapUrnBuilder":
        """Set the input spec (required)"""
        self._in_urn = in_urn
        return self

    def out_spec(self, out_urn: str) -> "CapUrnBuilder":
        """Set the output spec (required)"""
        self._out_urn = out_urn
        return self

    def effect(self, effect: CapEffect) -> "CapUrnBuilder":
        self._effect = effect.value
        return self

    def tag(self, key: str, value: str) -> "CapUrnBuilder":
        """Add a tag with key (normalized to lowercase) and value (preserved as-is)

        Raises CapUrnError if value is empty (use "*" for wildcard).
        """
        if not value:
            raise CapUrnError(f"Empty value for key '{key}' (use '*' for wildcard)")
        if key.lower() in ("in", "out", "effect"):
            raise CapUrnError(
                f"CapUrnBuilder.tag cannot set reserved structural key '{key.lower()}'; use in_spec/out_spec/effect"
            )
        self._tags[key.lower()] = value
        return self

    def marker(self, key: str) -> "CapUrnBuilder":
        """Add a tag with wildcard value ("*") without requiring explicit value parameter"""
        key_lower = key.lower()
        if key_lower in ("in", "out", "effect"):
            raise CapUrnError(
                f"CapUrnBuilder.marker cannot set reserved structural key '{key_lower}'; use in_spec/out_spec/effect"
            )
        self._tags[key_lower] = "*"
        return self

    def build(self) -> CapUrn:
        """Build the cap URN

        Raises CapUrnError if in_spec or out_spec is missing.
        """
        if self._in_urn is None:
            raise CapUrnError("Missing required 'in' spec - use in_spec() to set it")
        if self._out_urn is None:
            raise CapUrnError("Missing required 'out' spec - use out_spec() to set it")

        return CapUrn(self._in_urn, self._out_urn, self._tags, effect=self._effect)
