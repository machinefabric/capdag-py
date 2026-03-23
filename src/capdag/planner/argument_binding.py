"""Argument binding and resolution for cap execution.

This module defines how arguments are bound to values at plan-build time
and resolved to concrete bytes at execution time. It mirrors Rust's
planner/argument_binding.rs exactly.

Key types:
- CapInputFile: Uniform file representation passed to every cap
- ArgumentBinding: How to resolve one argument value (10 variants)
- ArgumentBindings: Collection of named bindings for one cap node
- ArgumentResolutionContext: Borrowed context for resolution
- StrandInput: Input specification for a machine
- resolve_binding(): Core resolution function
"""

from __future__ import annotations

import json
import os
from enum import Enum
from typing import Any, Dict, List, Optional

from capdag.planner.cardinality import InputCardinality
from capdag.planner.error import InternalError


class SourceEntityType(Enum):
    """Origin type for a CapInputFile."""
    LISTING = "listing"
    CAP_OUTPUT = "cap_output"
    CHIP = "chip"
    BLOCK = "block"
    TEMPORARY = "temporary"


class CapFileMetadata:
    """Optional metadata attached to a CapInputFile."""

    __slots__ = ("filename", "size_bytes", "mime_type", "extra")

    def __init__(
        self,
        filename: Optional[str] = None,
        size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        extra: Optional[Any] = None,
    ) -> None:
        self.filename = filename
        self.size_bytes = size_bytes
        self.mime_type = mime_type
        self.extra = extra

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        if self.filename is not None:
            d["filename"] = self.filename
        if self.size_bytes is not None:
            d["size_bytes"] = self.size_bytes
        if self.mime_type is not None:
            d["mime_type"] = self.mime_type
        if self.extra is not None:
            d["extra"] = self.extra
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> CapFileMetadata:
        return CapFileMetadata(
            filename=d.get("filename"),
            size_bytes=d.get("size_bytes"),
            mime_type=d.get("mime_type"),
            extra=d.get("extra"),
        )

    def __repr__(self) -> str:
        parts = []
        if self.filename is not None:
            parts.append(f"filename={self.filename!r}")
        if self.size_bytes is not None:
            parts.append(f"size_bytes={self.size_bytes}")
        if self.mime_type is not None:
            parts.append(f"mime_type={self.mime_type!r}")
        if self.extra is not None:
            parts.append(f"extra={self.extra!r}")
        return f"CapFileMetadata({', '.join(parts)})"


class CapInputFile:
    """Uniform file representation passed to every cap.

    Caps never see listings, chips, or blocks directly — only CapInputFile.
    """

    __slots__ = (
        "file_path", "media_urn", "metadata", "source_id",
        "source_type", "tracked_file_id", "security_bookmark", "original_path",
    )

    def __init__(self, file_path: str, media_urn: str) -> None:
        self.file_path = file_path
        self.media_urn = media_urn
        self.metadata: Optional[CapFileMetadata] = None
        self.source_id: Optional[str] = None
        self.source_type: Optional[SourceEntityType] = None
        self.tracked_file_id: Optional[str] = None
        self.security_bookmark: Optional[bytes] = None  # runtime-only, never serialized
        self.original_path: Optional[str] = None

    @staticmethod
    def from_listing(listing_id: str, file_path: str, media_urn: str) -> CapInputFile:
        f = CapInputFile(file_path, media_urn)
        f.source_id = listing_id
        f.source_type = SourceEntityType.LISTING
        return f

    @staticmethod
    def from_chip(chip_id: str, cache_path: str, media_urn: str) -> CapInputFile:
        f = CapInputFile(cache_path, media_urn)
        f.source_id = chip_id
        f.source_type = SourceEntityType.CHIP
        return f

    @staticmethod
    def from_cap_output(output_path: str, media_urn: str) -> CapInputFile:
        f = CapInputFile(output_path, media_urn)
        f.source_type = SourceEntityType.CAP_OUTPUT
        return f

    def with_metadata(self, metadata: CapFileMetadata) -> CapInputFile:
        self.metadata = metadata
        return self

    def with_file_reference(
        self, tracked_file_id: str, security_bookmark: bytes, original_path: str
    ) -> CapInputFile:
        self.tracked_file_id = tracked_file_id
        self.security_bookmark = security_bookmark
        self.original_path = original_path
        return self

    def filename(self) -> Optional[str]:
        """Extract basename from file_path."""
        basename = os.path.basename(self.file_path)
        return basename if basename else None

    def has_file_reference(self) -> bool:
        return self.tracked_file_id is not None and self.security_bookmark is not None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "file_path": self.file_path,
            "media_urn": self.media_urn,
        }
        if self.metadata is not None:
            d["metadata"] = self.metadata.to_dict()
        if self.source_id is not None:
            d["source_id"] = self.source_id
        if self.source_type is not None:
            d["source_type"] = self.source_type.value
        if self.tracked_file_id is not None:
            d["tracked_file_id"] = self.tracked_file_id
        # security_bookmark is never serialized
        if self.original_path is not None:
            d["original_path"] = self.original_path
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> CapInputFile:
        f = CapInputFile(d["file_path"], d["media_urn"])
        if "metadata" in d:
            f.metadata = CapFileMetadata.from_dict(d["metadata"])
        if "source_id" in d:
            f.source_id = d["source_id"]
        if "source_type" in d:
            f.source_type = SourceEntityType(d["source_type"])
        if "tracked_file_id" in d:
            f.tracked_file_id = d["tracked_file_id"]
        if "original_path" in d:
            f.original_path = d["original_path"]
        return f

    def __repr__(self) -> str:
        return f"CapInputFile(file_path={self.file_path!r}, media_urn={self.media_urn!r})"


class ArgumentSource(Enum):
    """Tag describing where a resolved argument value came from."""
    INPUT_FILE = "input_file"
    PREVIOUS_OUTPUT = "previous_output"
    CAP_DEFAULT = "cap_default"
    CAP_SETTING = "cap_setting"
    LITERAL = "literal"
    SLOT = "slot"
    PLAN_METADATA = "plan_metadata"


class ArgumentBinding:
    """How to resolve one argument value.

    Each binding variant describes a different source for argument data.
    This is the Python equivalent of Rust's ArgumentBinding enum with
    10 variants, represented as a tagged class with a `kind` discriminant.
    """

    __slots__ = ("kind", "_data")

    # Kind constants matching Rust's variant names
    INPUT_FILE = "input_file"
    INPUT_FILE_PATH = "input_file_path"
    INPUT_MEDIA_URN = "input_media_urn"
    PREVIOUS_OUTPUT = "previous_output"
    CAP_DEFAULT = "cap_default"
    CAP_SETTING = "cap_setting"
    LITERAL = "literal"
    SLOT = "slot"
    PLAN_METADATA = "plan_metadata"

    def __init__(self, kind: str, data: Optional[Dict[str, Any]] = None) -> None:
        self.kind = kind
        self._data = data or {}

    # --- Factory methods for each variant ---

    @staticmethod
    def input_file(index: int) -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.INPUT_FILE, {"index": index})

    @staticmethod
    def input_file_path() -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.INPUT_FILE_PATH)

    @staticmethod
    def input_media_urn() -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.INPUT_MEDIA_URN)

    @staticmethod
    def previous_output(node_id: str, output_field: Optional[str] = None) -> ArgumentBinding:
        data: Dict[str, Any] = {"node_id": node_id}
        if output_field is not None:
            data["output_field"] = output_field
        return ArgumentBinding(ArgumentBinding.PREVIOUS_OUTPUT, data)

    @staticmethod
    def cap_default() -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.CAP_DEFAULT)

    @staticmethod
    def cap_setting(setting_urn: str) -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.CAP_SETTING, {"setting_urn": setting_urn})

    @staticmethod
    def literal(value: Any) -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.LITERAL, {"value": value})

    @staticmethod
    def literal_string(s: str) -> ArgumentBinding:
        return ArgumentBinding.literal(s)

    @staticmethod
    def literal_number(n: int) -> ArgumentBinding:
        return ArgumentBinding.literal(n)

    @staticmethod
    def literal_bool(b: bool) -> ArgumentBinding:
        return ArgumentBinding.literal(b)

    @staticmethod
    def slot(name: str, schema: Optional[Any] = None) -> ArgumentBinding:
        data: Dict[str, Any] = {"name": name}
        if schema is not None:
            data["schema"] = schema
        return ArgumentBinding(ArgumentBinding.SLOT, data)

    @staticmethod
    def plan_metadata(key: str) -> ArgumentBinding:
        return ArgumentBinding(ArgumentBinding.PLAN_METADATA, {"key": key})

    # --- Query methods ---

    def requires_input(self) -> bool:
        """True only for Slot bindings — these need user/external input."""
        return self.kind == ArgumentBinding.SLOT

    def references_previous(self) -> bool:
        """True only for PreviousOutput bindings."""
        return self.kind == ArgumentBinding.PREVIOUS_OUTPUT

    # --- Data accessors ---

    @property
    def index(self) -> int:
        return self._data["index"]

    @property
    def node_id(self) -> str:
        return self._data["node_id"]

    @property
    def output_field(self) -> Optional[str]:
        return self._data.get("output_field")

    @property
    def setting_urn(self) -> str:
        return self._data["setting_urn"]

    @property
    def value(self) -> Any:
        return self._data["value"]

    @property
    def slot_name(self) -> str:
        return self._data["name"]

    @property
    def schema(self) -> Optional[Any]:
        return self._data.get("schema")

    @property
    def key(self) -> str:
        return self._data["key"]

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"type": self.kind}
        d.update(self._data)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ArgumentBinding:
        kind = d["type"]
        data = {k: v for k, v in d.items() if k != "type"}
        return ArgumentBinding(kind, data)

    def __repr__(self) -> str:
        if self._data:
            return f"ArgumentBinding({self.kind!r}, {self._data!r})"
        return f"ArgumentBinding({self.kind!r})"


class ResolvedArgument:
    """A fully-resolved argument ready to pass to a cap."""

    __slots__ = ("name", "value", "source")

    def __init__(self, name: str, value: bytes, source: ArgumentSource) -> None:
        self.name = name
        self.value = value
        self.source = source

    def __repr__(self) -> str:
        return f"ResolvedArgument(name={self.name!r}, source={self.source.value}, len={len(self.value)})"


class ArgumentResolutionContext:
    """Context for resolving argument bindings at execution time.

    Holds references to input files, previous step outputs,
    plan metadata, cap settings, and slot values.
    """

    __slots__ = (
        "input_files", "current_file_index", "previous_outputs",
        "plan_metadata", "cap_settings", "slot_values",
    )

    def __init__(
        self,
        input_files: List[CapInputFile],
        current_file_index: int = 0,
        previous_outputs: Optional[Dict[str, Any]] = None,
        plan_metadata: Optional[Dict[str, Any]] = None,
        cap_settings: Optional[Dict[str, Dict[str, Any]]] = None,
        slot_values: Optional[Dict[str, bytes]] = None,
    ) -> None:
        self.input_files = input_files
        self.current_file_index = current_file_index
        self.previous_outputs = previous_outputs if previous_outputs is not None else {}
        self.plan_metadata = plan_metadata
        self.cap_settings = cap_settings
        self.slot_values = slot_values

    @staticmethod
    def with_inputs(input_files: List[CapInputFile]) -> ArgumentResolutionContext:
        """Minimal constructor with just input files."""
        return ArgumentResolutionContext(input_files=input_files)

    def current_file(self) -> Optional[CapInputFile]:
        """Get the current file being processed."""
        if 0 <= self.current_file_index < len(self.input_files):
            return self.input_files[self.current_file_index]
        return None


class ArgumentBindings:
    """Collection of named argument bindings for one cap node."""

    __slots__ = ("bindings",)

    def __init__(self) -> None:
        self.bindings: Dict[str, ArgumentBinding] = {}

    def add(self, name: str, binding: ArgumentBinding) -> None:
        self.bindings[name] = binding

    def add_file_path(self, arg_name: str) -> None:
        self.bindings[arg_name] = ArgumentBinding.input_file_path()

    def add_literal(self, arg_name: str, value: Any) -> None:
        self.bindings[arg_name] = ArgumentBinding.literal(value)

    def has_unresolved_slots(self) -> bool:
        return any(b.requires_input() for b in self.bindings.values())

    def get_unresolved_slots(self) -> List[str]:
        return [name for name, b in self.bindings.items() if b.requires_input()]

    def resolve_all(
        self,
        context: ArgumentResolutionContext,
        cap_urn: str,
        node_id: str,
        cap_defaults: Optional[Dict[str, Any]] = None,
        arg_required: Optional[Dict[str, bool]] = None,
    ) -> List[ResolvedArgument]:
        """Resolve all bindings, returning a list of ResolvedArguments.

        Optional slots with no value are silently skipped (not included
        in the result). Required slots with no value raise InternalError.
        """
        results: List[ResolvedArgument] = []
        for name, binding in self.bindings.items():
            default_value = cap_defaults.get(name) if cap_defaults else None
            is_required = True
            if arg_required is not None and name in arg_required:
                is_required = arg_required[name]

            resolved = resolve_binding(
                binding, context, cap_urn, node_id, default_value, is_required
            )
            if resolved is not None:
                resolved.name = name
                results.append(resolved)
        return results

    def to_dict(self) -> Dict[str, Any]:
        return {name: b.to_dict() for name, b in self.bindings.items()}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> ArgumentBindings:
        ab = ArgumentBindings()
        for name, binding_data in d.items():
            ab.bindings[name] = ArgumentBinding.from_dict(binding_data)
        return ab

    def __repr__(self) -> str:
        return f"ArgumentBindings({list(self.bindings.keys())})"


class StrandInput:
    """Input specification for a machine at execution start."""

    __slots__ = ("files", "expected_media_urn", "cardinality")

    def __init__(
        self,
        files: List[CapInputFile],
        expected_media_urn: str,
        cardinality: InputCardinality,
    ) -> None:
        self.files = files
        self.expected_media_urn = expected_media_urn
        self.cardinality = cardinality

    @staticmethod
    def single(file: CapInputFile) -> StrandInput:
        return StrandInput(
            files=[file],
            expected_media_urn=file.media_urn,
            cardinality=InputCardinality.SINGLE,
        )

    @staticmethod
    def sequence(files: List[CapInputFile], media_urn: str) -> StrandInput:
        return StrandInput(
            files=files,
            expected_media_urn=media_urn,
            cardinality=InputCardinality.SEQUENCE,
        )

    def is_valid(self) -> bool:
        if self.cardinality == InputCardinality.SINGLE:
            return len(self.files) == 1
        # SEQUENCE and AT_LEAST_ONE both require non-empty
        return len(self.files) > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "files": [f.to_dict() for f in self.files],
            "expected_media_urn": self.expected_media_urn,
            "cardinality": self.cardinality.value,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> StrandInput:
        return StrandInput(
            files=[CapInputFile.from_dict(f) for f in d["files"]],
            expected_media_urn=d["expected_media_urn"],
            cardinality=InputCardinality(d["cardinality"]),
        )

    def __repr__(self) -> str:
        return (
            f"StrandInput(files={len(self.files)}, "
            f"media_urn={self.expected_media_urn!r}, "
            f"cardinality={self.cardinality.value})"
        )


def _json_value_to_bytes(value: Any) -> bytes:
    """Convert a JSON value to bytes.

    Strings are encoded as raw UTF-8 bytes (no JSON quoting).
    Everything else is JSON-encoded.
    """
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def resolve_binding(
    binding: ArgumentBinding,
    context: ArgumentResolutionContext,
    cap_urn: str,
    node_id: str,
    default_value: Optional[Any] = None,
    is_required: bool = True,
) -> Optional[ResolvedArgument]:
    """Resolve a single argument binding to a concrete value.

    Returns None for optional Slot bindings with no available value.
    Raises InternalError for required bindings that cannot be resolved.
    """

    if binding.kind == ArgumentBinding.INPUT_FILE:
        index = binding.index
        if index >= len(context.input_files):
            raise InternalError(
                f"Input file index {index} out of bounds (have {len(context.input_files)} files)"
            )
        value = context.input_files[index].file_path.encode("utf-8")
        return ResolvedArgument("", value, ArgumentSource.INPUT_FILE)

    elif binding.kind == ArgumentBinding.INPUT_FILE_PATH:
        current = context.current_file()
        if current is None:
            raise InternalError("No current input file available")
        value = current.file_path.encode("utf-8")
        return ResolvedArgument("", value, ArgumentSource.INPUT_FILE)

    elif binding.kind == ArgumentBinding.INPUT_MEDIA_URN:
        current = context.current_file()
        if current is None:
            raise InternalError("No current input file available")
        value = current.media_urn.encode("utf-8")
        return ResolvedArgument("", value, ArgumentSource.INPUT_FILE)

    elif binding.kind == ArgumentBinding.PREVIOUS_OUTPUT:
        node_id = binding.node_id
        if node_id not in context.previous_outputs:
            raise InternalError(f"No previous output for node {node_id!r}")
        output_val = context.previous_outputs[node_id]
        output_field = binding.output_field
        if output_field is not None:
            if not isinstance(output_val, dict) or output_field not in output_val:
                raise InternalError(
                    f"Output field {output_field!r} not found in output of node {node_id!r}"
                )
            output_val = output_val[output_field]
        value = _json_value_to_bytes(output_val)
        return ResolvedArgument("", value, ArgumentSource.PREVIOUS_OUTPUT)

    elif binding.kind == ArgumentBinding.CAP_DEFAULT:
        if default_value is None:
            raise InternalError("No default value available for CapDefault binding")
        value = _json_value_to_bytes(default_value)
        return ResolvedArgument("", value, ArgumentSource.CAP_DEFAULT)

    elif binding.kind == ArgumentBinding.CAP_SETTING:
        setting_urn = binding.setting_urn
        if context.cap_settings is None or cap_urn not in context.cap_settings:
            raise InternalError(f"No settings available for cap {cap_urn!r}")
        cap_settings_map = context.cap_settings[cap_urn]
        if setting_urn not in cap_settings_map:
            raise InternalError(
                f"Setting {setting_urn!r} not found for cap {cap_urn!r}"
            )
        value = _json_value_to_bytes(cap_settings_map[setting_urn])
        return ResolvedArgument("", value, ArgumentSource.CAP_SETTING)

    elif binding.kind == ArgumentBinding.LITERAL:
        value = _json_value_to_bytes(binding.value)
        return ResolvedArgument("", value, ArgumentSource.LITERAL)

    elif binding.kind == ArgumentBinding.SLOT:
        slot_name = binding.slot_name
        slot_key = f"{node_id}:{slot_name}"

        # Priority 1: slot_values
        if context.slot_values is not None and slot_key in context.slot_values:
            return ResolvedArgument("", context.slot_values[slot_key], ArgumentSource.SLOT)

        # Priority 2: cap_settings[cap_urn][slot_name]
        if context.cap_settings is not None and cap_urn in context.cap_settings:
            cap_settings_map = context.cap_settings[cap_urn]
            if slot_name in cap_settings_map:
                value = _json_value_to_bytes(cap_settings_map[slot_name])
                return ResolvedArgument("", value, ArgumentSource.CAP_SETTING)

        # Priority 3: default_value
        if default_value is not None:
            value = _json_value_to_bytes(default_value)
            return ResolvedArgument("", value, ArgumentSource.CAP_DEFAULT)

        # No value found
        if is_required:
            raise InternalError(
                f"Required slot {slot_name!r} has no value for cap {cap_urn!r}"
            )
        return None

    elif binding.kind == ArgumentBinding.PLAN_METADATA:
        key = binding.key
        if context.plan_metadata is None:
            raise InternalError("No plan metadata available")
        if key not in context.plan_metadata:
            raise InternalError(f"Plan metadata key {key!r} not found")
        value = _json_value_to_bytes(context.plan_metadata[key])
        return ResolvedArgument("", value, ArgumentSource.PLAN_METADATA)

    else:
        raise InternalError(f"Unknown binding kind: {binding.kind!r}")
