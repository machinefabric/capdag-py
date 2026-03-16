"""Cardinality and Structure Detection from Media URNs

This module provides shape analysis for cap inputs and outputs across two orthogonal dimensions:

1. Cardinality (how many items)
   Detected from the `list` marker tag:
   - media:pdf → Single (scalar, no list marker)
   - media:pdf;list → Sequence (array, has list marker)

2. Structure (internal shape of each item)
   Detected from the `record` marker tag:
   - media:textable → Opaque (no internal fields, no record marker)
   - media:json;record → Record (has key-value fields, record marker)

The Four Combinations:
| Cardinality | Structure | Example                          |
|-------------|-----------|----------------------------------|
| scalar      | opaque    | media:textable - one string      |
| scalar      | record    | media:json;record - one JSON obj |
| list        | opaque    | media:file-path;list - paths     |
| list        | record    | media:json;list;record - objects  |

Design principle: URN handling uses proper parsing via MediaUrn, never string comparison.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from capdag.urn.media_urn import MediaUrn


class InputCardinality(Enum):
    """Cardinality of cap inputs/outputs."""
    SINGLE = "single"       # Exactly 1 item (no list marker = scalar by default)
    SEQUENCE = "sequence"   # Array of items (has list marker)
    AT_LEAST_ONE = "at_least_one"  # 1 or more items (cap can handle either)

    @staticmethod
    def from_media_urn(urn_str: str) -> InputCardinality:
        """Parse cardinality from a media URN string.

        Uses the `list` marker tag to determine if this represents an array.
        No list marker = scalar (default), list marker = sequence.
        """
        media_urn = MediaUrn.from_string(urn_str)
        if media_urn.is_list():
            return InputCardinality.SEQUENCE
        return InputCardinality.SINGLE

    def is_multiple(self) -> bool:
        """Check if this cardinality accepts multiple items."""
        return self in (InputCardinality.SEQUENCE, InputCardinality.AT_LEAST_ONE)

    def accepts_single(self) -> bool:
        """Check if this cardinality can accept a single item."""
        return self in (InputCardinality.SINGLE, InputCardinality.AT_LEAST_ONE)

    def is_compatible_with(self, source: InputCardinality) -> CardinalityCompatibility:
        """Check if cardinalities are compatible for data flow.

        Returns how data with `source` cardinality can flow into
        an input expecting `self` cardinality.
        """
        if source == InputCardinality.AT_LEAST_ONE or self == InputCardinality.AT_LEAST_ONE:
            return CardinalityCompatibility.DIRECT

        if source == InputCardinality.SINGLE and self == InputCardinality.SINGLE:
            return CardinalityCompatibility.DIRECT
        if source == InputCardinality.SINGLE and self == InputCardinality.SEQUENCE:
            return CardinalityCompatibility.WRAP_IN_ARRAY
        if source == InputCardinality.SEQUENCE and self == InputCardinality.SINGLE:
            return CardinalityCompatibility.REQUIRES_FAN_OUT
        if source == InputCardinality.SEQUENCE and self == InputCardinality.SEQUENCE:
            return CardinalityCompatibility.DIRECT

        return CardinalityCompatibility.DIRECT

    def apply_to_urn(self, base_urn: str) -> str:
        """Create a media URN with this cardinality from a base URN."""
        media_urn = MediaUrn.from_string(base_urn)
        has_list = media_urn.is_list()

        if self in (InputCardinality.SINGLE, InputCardinality.AT_LEAST_ONE):
            if has_list:
                return str(media_urn.without_list())
            return base_urn
        else:  # SEQUENCE
            if has_list:
                return base_urn
            return str(media_urn.with_list())


class CardinalityCompatibility(Enum):
    """Result of checking cardinality compatibility."""
    DIRECT = "direct"                     # Direct flow, no transformation needed
    WRAP_IN_ARRAY = "wrap_in_array"       # Need to wrap single item in array
    REQUIRES_FAN_OUT = "requires_fan_out" # Need to fan-out: iterate over sequence


class InputStructure(Enum):
    """Structure of media data — whether it has internal fields or is opaque."""
    OPAQUE = "opaque"  # Indivisible, no internal fields (no record marker)
    RECORD = "record"  # Has internal key-value fields (record marker present)

    @staticmethod
    def from_media_urn(urn_str: str) -> InputStructure:
        """Parse structure from a media URN string.

        Uses the `record` marker tag to determine if this has internal fields.
        No record marker = opaque (default), record marker = record.
        """
        media_urn = MediaUrn.from_string(urn_str)
        if media_urn.is_record():
            return InputStructure.RECORD
        return InputStructure.OPAQUE

    def is_compatible_with(self, source: InputStructure) -> StructureCompatibility:
        """Check if structures are compatible for data flow.

        Structure compatibility is strict — no coercion allowed:
        - Opaque → Opaque: Direct
        - Record → Record: Direct
        - Opaque → Record: Error (can't add structure)
        - Record → Opaque: Error (can't discard structure)
        """
        if source == InputStructure.OPAQUE and self == InputStructure.OPAQUE:
            return StructureCompatibility.DIRECT
        if source == InputStructure.RECORD and self == InputStructure.RECORD:
            return StructureCompatibility.DIRECT
        if source == InputStructure.OPAQUE and self == InputStructure.RECORD:
            return StructureCompatibility.incompatible("cannot add structure to opaque data")
        # Record → Opaque
        return StructureCompatibility.incompatible("cannot discard structure from record")

    def apply_to_urn(self, base_urn: str) -> str:
        """Create a media URN with this structure from a base URN."""
        media_urn = MediaUrn.from_string(base_urn)
        has_record = media_urn.is_record()

        if self == InputStructure.OPAQUE:
            if has_record:
                return str(media_urn.without_tag("record"))
            return base_urn
        else:  # RECORD
            if has_record:
                return base_urn
            return str(media_urn.with_tag("record", "*"))


class StructureCompatibility:
    """Result of checking structure compatibility."""

    def __init__(self, is_direct: bool, message: Optional[str] = None):
        self._is_direct = is_direct
        self._message = message

    DIRECT: StructureCompatibility  # assigned below

    @classmethod
    def incompatible(cls, message: str) -> StructureCompatibility:
        return cls(is_direct=False, message=message)

    def is_error(self) -> bool:
        return not self._is_direct

    @property
    def message(self) -> Optional[str]:
        return self._message

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, StructureCompatibility):
            return NotImplemented
        return self._is_direct == other._is_direct and self._message == other._message

    def __repr__(self) -> str:
        if self._is_direct:
            return "StructureCompatibility.DIRECT"
        return f"StructureCompatibility.Incompatible({self._message!r})"


StructureCompatibility.DIRECT = StructureCompatibility(is_direct=True)


class MediaShape:
    """Complete shape of media data combining cardinality and structure."""

    __slots__ = ("cardinality", "structure")

    def __init__(
        self,
        cardinality: InputCardinality = InputCardinality.SINGLE,
        structure: InputStructure = InputStructure.OPAQUE,
    ):
        self.cardinality = cardinality
        self.structure = structure

    @staticmethod
    def from_media_urn(urn_str: str) -> MediaShape:
        """Parse complete shape from a media URN string."""
        return MediaShape(
            cardinality=InputCardinality.from_media_urn(urn_str),
            structure=InputStructure.from_media_urn(urn_str),
        )

    @staticmethod
    def scalar_opaque() -> MediaShape:
        return MediaShape(InputCardinality.SINGLE, InputStructure.OPAQUE)

    @staticmethod
    def scalar_record() -> MediaShape:
        return MediaShape(InputCardinality.SINGLE, InputStructure.RECORD)

    @staticmethod
    def list_opaque() -> MediaShape:
        return MediaShape(InputCardinality.SEQUENCE, InputStructure.OPAQUE)

    @staticmethod
    def list_record() -> MediaShape:
        return MediaShape(InputCardinality.SEQUENCE, InputStructure.RECORD)

    def is_compatible_with(self, source: MediaShape) -> ShapeCompatibility:
        """Check if shapes are compatible for data flow."""
        structure_compat = self.structure.is_compatible_with(source.structure)

        # Structure incompatibility is always an error
        if structure_compat.is_error():
            return ShapeCompatibility.incompatible(structure_compat.message or "structure mismatch")

        # Structure is OK, return cardinality compatibility
        cardinality_compat = self.cardinality.is_compatible_with(source.cardinality)
        if cardinality_compat == CardinalityCompatibility.DIRECT:
            return ShapeCompatibility.DIRECT
        elif cardinality_compat == CardinalityCompatibility.WRAP_IN_ARRAY:
            return ShapeCompatibility.WRAP_IN_ARRAY
        else:
            return ShapeCompatibility.REQUIRES_FAN_OUT

    def apply_to_urn(self, base_urn: str) -> str:
        """Apply this shape to a base URN."""
        with_cardinality = self.cardinality.apply_to_urn(base_urn)
        return self.structure.apply_to_urn(with_cardinality)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MediaShape):
            return NotImplemented
        return self.cardinality == other.cardinality and self.structure == other.structure

    def __repr__(self) -> str:
        return f"MediaShape({self.cardinality.value}, {self.structure.value})"


class ShapeCompatibility:
    """Result of checking complete shape compatibility."""

    def __init__(self, kind: str, message: Optional[str] = None):
        self._kind = kind
        self._message = message

    DIRECT: ShapeCompatibility      # assigned below
    WRAP_IN_ARRAY: ShapeCompatibility
    REQUIRES_FAN_OUT: ShapeCompatibility

    @classmethod
    def incompatible(cls, message: str) -> ShapeCompatibility:
        return cls(kind="incompatible", message=message)

    def is_error(self) -> bool:
        return self._kind == "incompatible"

    def requires_fan_out(self) -> bool:
        return self._kind == "requires_fan_out"

    def requires_wrap(self) -> bool:
        return self._kind == "wrap_in_array"

    @property
    def message(self) -> Optional[str]:
        return self._message

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ShapeCompatibility):
            return NotImplemented
        return self._kind == other._kind

    def __repr__(self) -> str:
        if self._kind == "incompatible":
            return f"ShapeCompatibility.Incompatible({self._message!r})"
        return f"ShapeCompatibility.{self._kind.upper()}"


ShapeCompatibility.DIRECT = ShapeCompatibility(kind="direct")
ShapeCompatibility.WRAP_IN_ARRAY = ShapeCompatibility(kind="wrap_in_array")
ShapeCompatibility.REQUIRES_FAN_OUT = ShapeCompatibility(kind="requires_fan_out")


class CapShapeInfo:
    """Complete shape analysis for a cap transformation."""

    __slots__ = ("input", "output", "cap_urn")

    def __init__(self, input_shape: MediaShape, output_shape: MediaShape, cap_urn: str):
        self.input = input_shape
        self.output = output_shape
        self.cap_urn = cap_urn

    @staticmethod
    def from_cap_specs(cap_urn: str, in_spec: str, out_spec: str) -> CapShapeInfo:
        """Create shape info by parsing a cap's input and output specs."""
        return CapShapeInfo(
            input_shape=MediaShape.from_media_urn(in_spec),
            output_shape=MediaShape.from_media_urn(out_spec),
            cap_urn=cap_urn,
        )

    def cardinality_pattern(self) -> CardinalityPattern:
        """Describe the cardinality transformation pattern."""
        inp = self.input.cardinality
        out = self.output.cardinality

        if inp == InputCardinality.SINGLE and out == InputCardinality.SINGLE:
            return CardinalityPattern.ONE_TO_ONE
        if inp == InputCardinality.SINGLE and out == InputCardinality.SEQUENCE:
            return CardinalityPattern.ONE_TO_MANY
        if inp == InputCardinality.SEQUENCE and out == InputCardinality.SINGLE:
            return CardinalityPattern.MANY_TO_ONE
        if inp == InputCardinality.SEQUENCE and out == InputCardinality.SEQUENCE:
            return CardinalityPattern.MANY_TO_MANY

        # AtLeastOne cases
        if inp == InputCardinality.AT_LEAST_ONE and out == InputCardinality.SINGLE:
            return CardinalityPattern.ONE_TO_ONE
        if inp == InputCardinality.AT_LEAST_ONE and out == InputCardinality.SEQUENCE:
            return CardinalityPattern.ONE_TO_MANY
        if inp == InputCardinality.SINGLE and out == InputCardinality.AT_LEAST_ONE:
            return CardinalityPattern.ONE_TO_ONE
        if inp == InputCardinality.SEQUENCE and out == InputCardinality.AT_LEAST_ONE:
            return CardinalityPattern.MANY_TO_MANY
        # AT_LEAST_ONE, AT_LEAST_ONE
        return CardinalityPattern.ONE_TO_ONE

    def structures_match(self) -> bool:
        """Check if input/output structures match."""
        return self.input.structure == self.output.structure


class CardinalityPattern(Enum):
    """Pattern describing input/output cardinality relationship."""
    ONE_TO_ONE = "one_to_one"      # Single input → Single output
    ONE_TO_MANY = "one_to_many"    # Single input → Multiple outputs
    MANY_TO_ONE = "many_to_one"    # Multiple inputs → Single output
    MANY_TO_MANY = "many_to_many"  # Multiple inputs → Multiple outputs

    def produces_vector(self) -> bool:
        """Check if this pattern may produce multiple outputs."""
        return self in (CardinalityPattern.ONE_TO_MANY, CardinalityPattern.MANY_TO_MANY)

    def requires_vector(self) -> bool:
        """Check if this pattern requires multiple inputs."""
        return self in (CardinalityPattern.MANY_TO_ONE, CardinalityPattern.MANY_TO_MANY)


class ShapeChainAnalysis:
    """Analyze shape chain for a sequence of caps."""

    __slots__ = ("cap_infos", "fan_out_points", "fan_in_points", "is_valid", "error")

    def __init__(
        self,
        cap_infos: List[CapShapeInfo],
        fan_out_points: List[int],
        fan_in_points: List[int],
        is_valid: bool,
        error: Optional[str],
    ):
        self.cap_infos = cap_infos
        self.fan_out_points = fan_out_points
        self.fan_in_points = fan_in_points
        self.is_valid = is_valid
        self.error = error

    @staticmethod
    def analyze(cap_infos: List[CapShapeInfo]) -> ShapeChainAnalysis:
        """Analyze a chain of caps for shape transitions."""
        if not cap_infos:
            return ShapeChainAnalysis(
                cap_infos=[],
                fan_out_points=[],
                fan_in_points=[],
                is_valid=True,
                error=None,
            )

        fan_out_points: List[int] = []
        fan_in_points: List[int] = []
        current_shape = cap_infos[0].input
        error_msg: Optional[str] = None

        for i, info in enumerate(cap_infos):
            compatibility = info.input.is_compatible_with(current_shape)

            if compatibility == ShapeCompatibility.DIRECT:
                pass
            elif compatibility == ShapeCompatibility.WRAP_IN_ARRAY:
                pass
            elif compatibility.requires_fan_out():
                fan_out_points.append(i)
            elif compatibility.is_error():
                error_msg = (
                    f"Shape mismatch at cap {i} ({info.cap_urn}): {compatibility.message} "
                    f"- source has {current_shape.cardinality.value}/{current_shape.structure.value}, "
                    f"cap expects {info.input.cardinality.value}/{info.input.structure.value}"
                )
                break

            current_shape = info.output

        if error_msg is not None:
            return ShapeChainAnalysis(
                cap_infos=cap_infos,
                fan_out_points=fan_out_points,
                fan_in_points=fan_in_points,
                is_valid=False,
                error=error_msg,
            )

        if fan_out_points:
            fan_in_points.append(len(cap_infos))

        return ShapeChainAnalysis(
            cap_infos=cap_infos,
            fan_out_points=fan_out_points,
            fan_in_points=fan_in_points,
            is_valid=True,
            error=None,
        )

    def requires_transformation(self) -> bool:
        """Check if this chain requires any cardinality transformations."""
        return bool(self.fan_out_points) or bool(self.fan_in_points)

    def final_output_shape(self) -> Optional[MediaShape]:
        """Get the final output shape of the chain."""
        if not self.cap_infos:
            return None
        return self.cap_infos[-1].output
