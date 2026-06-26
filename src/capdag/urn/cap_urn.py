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


class CapUrnError(Exception):
    """Base exception for cap URN errors"""
    pass


# Per-tag truth-table specificity scoring is owned by tagged_urn —
# the same scorer applies uniformly to media-URN tags, cap-tag y-axis,
# and any other Tagged URN dimension. We re-use the canonical
# implementation rather than duplicate it; any drift here would be a
# wire-level inconsistency.
from tagged_urn import score_tag_value as _score_tag_value


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
        self._validate_admissible()

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
        TaggedUrn.from_string(TaggedUrn("cap", tags).to_string())

    def _validate_admissible(self) -> None:
        in_media = self.in_media_urn()
        out_media = self.out_media_urn()
        if (
            in_media.is_top()
            and out_media.is_top()
            and not self.tags
            and self.effect_kind() == CapEffect.DECLARED
        ):
            raise CapUrnError(
                "illegal bare top cap; use cap:effect=none for identity, or declare a non-vacuous input/output/effect/tag"
            )
        if self.effect_kind() in (CapEffect.DECLARED, CapEffect.ANY):
            return
        if self.effect_kind() == CapEffect.NONE:
            if not in_media.conforms_to(out_media):
                raise CapUrnError(
                    f"effect=none requires declared input '{in_media}' to conform to declared output '{out_media}'"
                )
            return
        if self.effect_kind() == CapEffect.PATCH:
            delta = out_media.delta_from(in_media)
            witness = in_media.apply_delta(delta)
            if not witness.conforms_to(out_media):
                raise CapUrnError(
                    f"effect=patch witness '{witness}' does not conform to declared output '{out_media}'"
                )
            return

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
        instance._validate_admissible()
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

    def accepts(self, request: "CapUrn") -> bool:
        """Check if this cap (pattern/handler) accepts the given request (instance).

        Direction specs use semantic TaggedUrn matching via MediaUrn:
        - Input: `cap_in.accepts(request_in)` — cap's input pattern accepts request's input
        - Output: `cap_out.conforms_to(request_out)` — cap's output conforms to request's expectation

        For other tags: cap satisfies request's tag constraints.
        Missing cap tags are wildcards (cap accepts any value for that tag).
        """
        # Input direction: self.in_urn is pattern, request.in_urn is instance
        # "media:" on the PATTERN side means "I accept any input" — skip check.
        # "media:" on the INSTANCE side is just the least specific — still check.
        if self.in_urn != "media:":
            cap_in = MediaUrn.from_string(self.in_urn)
            request_in = MediaUrn.from_string(request.in_urn)
            if not cap_in.accepts(request_in):
                return False

        # Output direction: self.out_urn is pattern, request.out_urn is instance
        # "media:" on the PATTERN side means "I accept any output" — skip check.
        # "media:" on the INSTANCE side is just the least specific — still check.
        if self.out_urn != "media:":
            cap_out = MediaUrn.from_string(self.out_urn)
            request_out = MediaUrn.from_string(request.out_urn)
            if not cap_out.conforms_to(request_out):
                return False

        if self.effect != CapEffect.ANY.value and self.effect != request.effect:
            return False

        # Y-axis: every tag's per-key match runs through the six-form
        # truth table (TaggedUrn._values_match). Walk the union of
        # all keys appearing on either side so missing-on-pattern and
        # missing-on-instance cells both get evaluated.
        all_keys = set(self.tags.keys()) | set(request.tags.keys())
        for key in all_keys:
            patt = self.tags.get(key)     # self is the pattern
            inst = request.tags.get(key)  # request is the instance
            if not TaggedUrn._values_match(inst, patt):
                return False

        return True

    def conforms_to(self, cap: "CapUrn") -> bool:
        """Check if this cap URN (as a request) conforms to another cap (handler).

        Delegates to cap.accepts(self).
        """
        return cap.accepts(self)

    def _input_dispatchable(self, request: "CapUrn") -> bool:
        """Check if provider's input is dispatchable for request's input.

        Input is CONTRAVARIANT: provider with looser input constraint can handle
        request with stricter input. media: is the identity (top) and means
        "unconstrained" — vacuously true on either side.

        - Request in=media: (unconstrained) + any provider -> YES (no constraint)
        - Provider in=media: (accepts any) + Request in=media:ext=pdf -> YES
        - Both specific -> request input must conform to provider's accepted input
        """
        # Request wildcard: any provider input is fine
        if request.in_urn == "media:":
            return True

        # Provider wildcard: provider accepts any input
        if self.in_urn == "media:":
            return True

        # Both specific: request input must conform to provider input requirement
        try:
            req_in = MediaUrn.from_string(request.in_urn)
        except Exception:
            return False
        try:
            prov_in = MediaUrn.from_string(self.in_urn)
        except Exception:
            return False

        return req_in.conforms_to(prov_in)

    def _output_dispatchable(self, request: "CapUrn") -> bool:
        """Check if provider's output is dispatchable for request's output.

        Output is COVARIANT: provider must produce at least what request needs.

        - Request out=media: (unconstrained): any provider output is fine
        - Provider out=media: + request specific: FAIL (cannot guarantee)
        - Both specific: provider output must conform to request output
        """
        # Request wildcard: any provider output is fine
        if request.out_urn == "media:":
            return True

        # Provider wildcard: cannot guarantee specific output request needs
        # This is asymmetric with input! Generic output doesn't satisfy specific requirement.
        if self.out_urn == "media:":
            return False

        # Both specific: provider output must conform to request output
        try:
            req_out = MediaUrn.from_string(request.out_urn)
        except Exception:
            return False
        try:
            prov_out = MediaUrn.from_string(self.out_urn)
        except Exception:
            return False

        return prov_out.conforms_to(req_out)

    def _cap_tags_dispatchable(self, request: "CapUrn") -> bool:
        """Check if provider's cap-tags are dispatchable for request's cap-tags.

        Every explicit request tag must be satisfied by provider.
        Provider may have extra tags (refinement is OK).
        Wildcard (*) in request means any value acceptable.
        Wildcard (*) in provider means provider can handle any value.
        """
        all_keys = set(self.tags.keys()) | set(request.tags.keys())
        for key in all_keys:
            provider_value = self.tags.get(key)
            request_value = request.tags.get(key)
            if not TaggedUrn._values_match(provider_value, request_value):
                return False
        return True

    def _effect_dispatchable(self, request: "CapUrn") -> bool:
        return request.effect == CapEffect.ANY.value or self.effect == request.effect

    def is_dispatchable(self, request: "CapUrn") -> bool:
        """Check if this provider can dispatch (handle) the given request.

        This is the PRIMARY predicate for routing/dispatch decisions.

        A provider is dispatchable for a request iff:
        1. Input axis: provider can handle request's input (contravariant)
        2. Output axis: provider meets request's output needs (covariant)
        3. Cap-tags: provider satisfies all explicit request tags, may add more

        Key insight: This is NOT symmetric. provider.is_dispatchable(request) may
        be true while request.is_dispatchable(provider) is false.
        """
        if not self._input_dispatchable(request):
            return False
        if not self._output_dispatchable(request):
            return False
        if not self._effect_dispatchable(request):
            return False
        if not self._cap_tags_dispatchable(request):
            return False
        return True

    def is_comparable(self, other: "CapUrn") -> bool:
        """Check if two cap URNs are comparable in the order-theoretic sense.

        Two URNs are comparable if either one accepts the other.
        """
        return self.accepts(other) or other.accepts(self)

    def is_equivalent(self, other: "CapUrn") -> bool:
        """Check if two cap URNs are equivalent in the order-theoretic sense.

        Two URNs are equivalent if each accepts the other.
        """
        return self.accepts(other) and other.accepts(self)

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
        if not runtime_input.conforms_to(declared_in):
            raise CapUrnError(
                f"Runtime input '{runtime_input}' does not conform to declared input '{declared_in}'"
            )
        if self.effect_kind() == CapEffect.DECLARED:
            runtime_out = declared_out
        elif self.effect_kind() == CapEffect.NONE:
            runtime_out = runtime_input
        elif self.effect_kind() == CapEffect.PATCH:
            delta = declared_out.delta_from(declared_in)
            runtime_out = runtime_input.apply_delta(delta)
        else:
            raise CapUrnError("Cannot infer runtime output for an unconstrained effect request")
        if not runtime_out.conforms_to(declared_out):
            raise CapUrnError(
                f"Inferred runtime output '{runtime_out}' does not conform to declared output '{declared_out}'"
            )
        return runtime_out

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
        """
        in_media = MediaUrn.from_string(self.in_urn)
        out_media = MediaUrn.from_string(self.out_urn)

        y_score = sum(_score_tag_value(v) for v in self.tags.values())
        return (
            CapUrn.WEIGHT_OUT * out_media.inner().specificity()
            + CapUrn.WEIGHT_IN * in_media.inner().specificity()
            + y_score
        )

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

    def _cmp_key(self) -> tuple:
        """Return a comparison key for structural total ordering.

        Ordering routes through the canonical string forms of the parsed
        MediaUrn values for `in` / `out` (which are already canonicalized
        at construction time), then the sorted tag items — exactly mirroring
        the Rust `Ord` impl and Go `Less()`.

        Using canonical strings rather than re-parsing through MediaUrn is
        safe because `CapUrn.__init__` always canonicalizes `in_urn` /
        `out_urn` on construction.  The sorted-tags tuple produces the same
        lexicographic order as Rust's `BTreeMap<String,String>::cmp`.

        This MUST NOT use the full `to_string()` form — that would collapse
        the three comparison axes (in, out, tags) into one opaque string and
        give wrong results for URNs whose canonical representations differ
        only in tag ordering.
        """
        return (
            self.in_media_urn()._cmp_key(),
            self.out_media_urn()._cmp_key(),
            self.effect,
            tuple(sorted(self.tags.items())),
        )

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
    """Cap matching and selection utilities"""

    @staticmethod
    def find_best_match(caps: List[CapUrn], request: CapUrn) -> Optional[CapUrn]:
        """Find the most specific cap that accepts a request"""
        matches = [cap for cap in caps if request.accepts(cap)]
        if not matches:
            return None
        return max(matches, key=lambda cap: cap.specificity())

    @staticmethod
    def find_all_matches(caps: List[CapUrn], request: CapUrn) -> List[CapUrn]:
        """Find all caps that match a request, sorted by specificity (most specific first)"""
        matches = [cap for cap in caps if request.accepts(cap)]
        # Sort by specificity (most specific first)
        matches.sort(key=lambda cap: cap.specificity(), reverse=True)
        return matches

    @staticmethod
    def are_compatible(caps1: List[CapUrn], caps2: List[CapUrn]) -> bool:
        """Check if two cap sets overlap (any pair where one accepts the other)"""
        return any(
            c1.accepts(c2) or c2.accepts(c1)
            for c1 in caps1
            for c2 in caps2
        )


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
