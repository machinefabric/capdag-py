"""Formal cap definition

This module defines the structure for formal cap definitions including
the cap URN, arguments, output, and metadata.
"""

import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from capdag.urn.cap_urn import CapUrn


@dataclass
class ArgSource:
    """Source specification for argument input

    Each variant represents a different way to provide the argument:
    - stdin: via standard input with a media URN
    - position: positional argument (0-based)
    - cli_flag: named CLI flag
    """

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        raise NotImplementedError("Subclasses must implement to_dict")

    def get_type(self) -> str:
        """Get the source type name"""
        raise NotImplementedError("Subclasses must implement get_type")


class StdinSource(ArgSource):
    """Argument provided via stdin"""

    def __init__(self, stdin: str):
        self.stdin = stdin

    def to_dict(self) -> Dict[str, Any]:
        return {"stdin": self.stdin}

    def get_type(self) -> str:
        return "stdin"

    def stdin_media_urn(self) -> str:
        return self.stdin

    def __eq__(self, other):
        return isinstance(other, StdinSource) and self.stdin == other.stdin


class PositionSource(ArgSource):
    """Argument at a specific position"""

    def __init__(self, position: int):
        self.position = position

    def to_dict(self) -> Dict[str, Any]:
        return {"position": self.position}

    def get_type(self) -> str:
        return "position"

    def position_value(self) -> int:
        return self.position

    def __eq__(self, other):
        return isinstance(other, PositionSource) and self.position == other.position


class CliFlagSource(ArgSource):
    """Argument via CLI flag"""

    def __init__(self, cli_flag: str):
        self.cli_flag = cli_flag

    def to_dict(self) -> Dict[str, Any]:
        return {"cli_flag": self.cli_flag}

    def get_type(self) -> str:
        return "cli_flag"

    def flag_name(self) -> str:
        return self.cli_flag

    def __eq__(self, other):
        return isinstance(other, CliFlagSource) and self.cli_flag == other.cli_flag


def arg_source_from_dict(data: Dict[str, Any]) -> ArgSource:
    """Parse ArgSource from dict"""
    if "stdin" in data:
        return StdinSource(data["stdin"])
    elif "position" in data:
        return PositionSource(data["position"])
    elif "cli_flag" in data:
        return CliFlagSource(data["cli_flag"])
    else:
        raise ValueError(f"Unknown arg source format: {data}")


@dataclass
class CapArg:
    """Cap argument definition"""

    media_urn: str
    required: bool
    sources: List[ArgSource]
    arg_description: Optional[str] = None
    default_value: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    is_sequence: bool = False

    @classmethod
    def with_full_definition(
        cls,
        media_urn: str,
        required: bool,
        sources: List[ArgSource],
        arg_description: Optional[str] = None,
        default_value: Optional[Any] = None,
        metadata: Optional[Any] = None,
        is_sequence: bool = False,
    ) -> "CapArg":
        """Create a CapArg with all fields set"""
        return cls(
            media_urn=media_urn,
            required=required,
            sources=sources,
            arg_description=arg_description,
            default_value=default_value,
            metadata=metadata,
            is_sequence=is_sequence,
        )

    def get_media_urn(self) -> str:
        """Get the media URN"""
        return self.media_urn

    def get_metadata(self) -> Optional[Any]:
        """Get the metadata"""
        return self.metadata

    def set_metadata(self, metadata: Any):
        """Set the metadata"""
        self.metadata = metadata

    def clear_metadata(self):
        """Clear the metadata"""
        self.metadata = None

    def stream_urn(self) -> str:
        """The media URN the runtime demuxes this arg's input stream by: its
        ``Stdin`` source URN if it declares one, otherwise its declared slot
        media URN. A cap need not declare any ``Stdin`` source at all — a
        producer-fed arg may be delivered by its declared URN — so this never
        assumes a stdin source exists.
        """
        for source in self.sources:
            if isinstance(source, StdinSource):
                return source.stdin
        return self.media_urn

    def is_main_input(self, in_spec: "MediaUrn") -> bool:
        """Whether this arg is the cap's MAIN input relative to ``in_spec``
        (the cap URN's ``in=`` value): it declares a ``Stdin`` source whose
        URN is ``in=``. The main input is always the value piped in on
        stdin (like a Unix command's stdin), so the main arg always declares
        a ``Stdin`` source carrying ``in=``. Its DECLARED slot URN may differ
        from that stdin URN (e.g. a ``file-path`` slot whose piped content is
        a ``pdf-stream``) — the stdin URN, not the slot URN, is ``in=``. The
        main input may ALSO be delivered by position/cli-flag, but stdin is
        the defining route. Compared by tagged-URN equivalence, never as
        strings.
        """
        from capdag.urn.media_urn import MediaUrn

        for source in self.sources:
            if not isinstance(source, StdinSource):
                continue
            try:
                stdin_urn = MediaUrn.from_string(source.stdin)
                if stdin_urn.is_equivalent(in_spec):
                    return True
            except Exception:
                continue
        return False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "media_urn": self.media_urn,
            "required": self.required,
            "sources": [s.to_dict() for s in self.sources],
        }
        if self.arg_description is not None:
            result["arg_description"] = self.arg_description
        if self.default_value is not None:
            result["default_value"] = self.default_value
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.is_sequence:
            result["is_sequence"] = self.is_sequence
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapArg":
        """Parse from dict"""
        return cls(
            media_urn=data["media_urn"],
            required=data["required"],
            sources=[arg_source_from_dict(s) for s in data["sources"]],
            arg_description=data.get("arg_description"),
            default_value=data.get("default_value"),
            metadata=data.get("metadata"),
            is_sequence=data.get("is_sequence", False),
        )


@dataclass
class CapOutput:
    """Output definition"""

    media_urn: str
    output_description: str
    metadata: Optional[Dict[str, Any]] = None
    is_sequence: bool = False

    @classmethod
    def with_full_definition(
        cls,
        media_urn: str,
        output_description: str,
        metadata: Optional[Any] = None,
        is_sequence: bool = False,
    ) -> "CapOutput":
        """Create a CapOutput with all fields set"""
        return cls(
            media_urn=media_urn,
            output_description=output_description,
            metadata=metadata,
            is_sequence=is_sequence,
        )

    def get_media_urn(self) -> str:
        """Get the media URN"""
        return self.media_urn

    def get_metadata(self) -> Optional[Any]:
        """Get the metadata"""
        return self.metadata

    def set_metadata(self, metadata: Any):
        """Set the metadata"""
        self.metadata = metadata

    def clear_metadata(self):
        """Clear the metadata"""
        self.metadata = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result = {
            "media_urn": self.media_urn,
            "output_description": self.output_description,
        }
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.is_sequence:
            result["is_sequence"] = self.is_sequence
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapOutput":
        """Parse from dict"""
        return cls(
            media_urn=data["media_urn"],
            output_description=data["output_description"],
            metadata=data.get("metadata"),
            is_sequence=data.get("is_sequence", False),
        )


@dataclass
class RegisteredBy:
    """Registration attribution — who registered a capability and when"""
    username: str
    registered_at: str


class Cap:
    """Formal cap definition

    A cap definition includes:
    - URN with tags (including `op`, `in`, `out`)
    - Arguments with media URN references
    - Output with media URN reference
    - Optional metadata
    """

    def __init__(self, urn: CapUrn, title: str, aliases: List[str]):
        self.urn = urn
        self.version: int = 0
        self.title = title
        # Globally-unique names selecting this cap in both CLIs (replaces the
        # former non-unique `command`). At least one; uniqueness enforced at publish.
        self.aliases: List[str] = aliases
        # Generic-input dispatch umbrella flag (never backed by a cartridge,
        # never a runnable graph edge). Absent in the wire form => False.
        self.is_abstract: bool = False
        self.cap_description: Optional[str] = None
        self.documentation: Optional[str] = None
        self.args: List[CapArg] = []
        self.output: Optional[CapOutput] = None
        self.metadata: Dict[str, str] = {}
        self._metadata_json: Optional[Any] = None
        self._registered_by: Optional["RegisteredBy"] = None
        self.supported_model_types: List[str] = []
        self.default_model_spec: Optional[str] = None

    @classmethod
    def with_description(cls, urn: CapUrn, title: str, aliases: List[str], description: str) -> "Cap":
        """Create a Cap with a description"""
        cap = cls(urn, title, aliases)
        cap.cap_description = description
        return cap

    @classmethod
    def with_metadata(cls, urn: CapUrn, title: str, aliases: List[str], metadata: Dict[str, str]) -> "Cap":
        """Create a Cap with metadata"""
        cap = cls(urn, title, aliases)
        cap.metadata = metadata
        return cap

    @classmethod
    def with_args(
        cls, urn: CapUrn, title: str, aliases: List[str], args: List[CapArg]
    ) -> "Cap":
        """Create a Cap with arguments"""
        cap = cls(urn, title, aliases)
        cap.args = args
        return cap

    @classmethod
    def with_full_definition(
        cls,
        urn: CapUrn,
        title: str,
        cap_description: Optional[str],
        metadata: Dict[str, str],
        aliases: List[str],
        args: List[CapArg],
        output: Optional[CapOutput] = None,
        metadata_json: Optional[Any] = None,
        documentation: Optional[str] = None,
    ) -> "Cap":
        """Create a Cap with all fields set"""
        cap = cls(urn, title, aliases)
        cap.cap_description = cap_description
        cap.documentation = documentation
        cap.metadata = metadata
        cap.args = args
        cap.output = output
        cap._metadata_json = metadata_json
        return cap

    def urn_string(self) -> str:
        """Get the URN as a string"""
        return self.urn.to_string()

    def get_args(self) -> List[CapArg]:
        """Get all arguments"""
        return self.args

    def add_arg(self, arg: CapArg):
        """Add an argument"""
        self.args.append(arg)

    def get_output(self) -> Optional[CapOutput]:
        """Get the output definition"""
        return self.output

    def set_output(self, output: CapOutput):
        """Set the output definition"""
        self.output = output

    def get_aliases(self) -> List[str]:
        """Get the cap's aliases (globally-unique selection names)."""
        return self.aliases

    def primary_alias(self) -> str:
        """The first alias, for single-name display. A cap always has one."""
        return self.aliases[0] if self.aliases else ""

    def has_alias(self, name: str) -> bool:
        """Whether name is one of this cap's aliases (exact match)."""
        return name in self.aliases

    def set_description(self, description: str):
        """Set the capability description"""
        self.cap_description = description

    def get_documentation(self) -> Optional[str]:
        """Get the documentation string"""
        return self.documentation

    def set_documentation(self, documentation: str) -> None:
        """Set the documentation string"""
        self.documentation = documentation

    def clear_documentation(self) -> None:
        """Clear the documentation string"""
        self.documentation = None

    def has_metadata(self, key: str) -> bool:
        """Check if metadata key exists"""
        return key in self.metadata

    def get_metadata(self, key: str) -> Optional[str]:
        """Get metadata value"""
        return self.metadata.get(key)

    def set_metadata(self, key: str, value: str):
        """Set metadata value"""
        self.metadata[key] = value

    def remove_metadata(self, key: str) -> Optional[str]:
        """Remove a metadata value. Returns the removed value or None."""
        return self.metadata.pop(key, None)

    def get_metadata_json(self) -> Optional[Any]:
        """Get the metadata JSON"""
        return self._metadata_json

    def set_metadata_json(self, metadata_json: Any):
        """Set the metadata JSON"""
        self._metadata_json = metadata_json

    def clear_metadata_json(self):
        """Clear the metadata JSON"""
        self._metadata_json = None

    def get_registered_by(self) -> Optional["RegisteredBy"]:
        """Get the registration attribution"""
        return self._registered_by

    def set_registered_by(self, registered_by: "RegisteredBy"):
        """Set the registration attribution"""
        self._registered_by = registered_by

    def clear_registered_by(self):
        """Clear the registration attribution"""
        self._registered_by = None

    def accepts_request(self, request_str: str) -> bool:
        """Check if this cap accepts a request string.
        Uses routing direction: request is the pattern, cap is the instance.
        """
        request = CapUrn.from_string(request_str)
        return request.accepts(self.urn)

    def is_more_specific_than(self, other: "Cap", request: str) -> bool:
        """Check if this cap is more specific than another for a given request.
        Both caps must accept the request; then compares specificity.
        """
        if not self.accepts_request(request) or not other.accepts_request(request):
            return False
        return self.urn.is_more_specific_than(other.urn)

    def accepts_stdin(self) -> bool:
        """Check if this cap accepts stdin input"""
        return self.get_stdin_media_urn() is not None

    def get_stdin_media_urn(self) -> Optional[str]:
        """Get stdin media URN if any arg uses stdin source"""
        for arg in self.args:
            for source in arg.sources:
                if isinstance(source, StdinSource):
                    return source.stdin_media_urn()
        return None

    def sequence_shape(self) -> Tuple[bool, bool]:
        """Cardinality shape of this cap's primary data path:
        ``(input_is_sequence, output_is_sequence)``.

        ``input_is_sequence`` is the ``is_sequence`` flag of the first arg
        that carries a ``Stdin`` source — the primary data input the wire
        delivers. ``output_is_sequence`` is the output's ``is_sequence`` flag.

        This is THE single definition of cap cardinality. Path search
        (``planner.live_cap_fab``), editor realization, and notation
        resolution (``machine.resolve``) all read it here so they can never
        diverge — the distinction that decides whether a ForEach is
        synthesized.
        """
        input_is_sequence = False
        for arg in self.args:
            if any(isinstance(source, StdinSource) for source in arg.sources):
                input_is_sequence = arg.is_sequence
                break
        output_is_sequence = self.output.is_sequence if self.output is not None else False
        return input_is_sequence, output_is_sequence

    def needs_foreach(self, source_is_sequence: bool) -> bool:
        """Whether a data position of cardinality ``source_is_sequence`` feeding
        this cap's primary input requires a ForEach (per-item map) to be
        inserted before it.

        The one rule, shared by every planner/resolver path: a sequence
        feeding a scalar-input cap must be mapped. The media URN does not
        change — ForEach is a shape transition, not a type transition.
        """
        input_is_sequence, _output_is_sequence = self.sequence_shape()
        return source_is_sequence and not input_is_sequence

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict"""
        result: Dict[str, Any] = {
            "urn": self.urn.to_string(),
            "title": self.title,
            "aliases": self.aliases,
        }

        if self.is_abstract:
            result["abstract"] = True

        if self.version != 0:
            result["version"] = self.version

        if self.cap_description is not None:
            result["cap_description"] = self.cap_description

        if self.documentation is not None:
            result["documentation"] = self.documentation

        if self.args:
            result["args"] = [arg.to_dict() for arg in self.args]

        if self.output is not None:
            result["output"] = self.output.to_dict()

        if self.metadata:
            result["metadata"] = self.metadata

        if self._metadata_json is not None:
            result["metadata_json"] = self._metadata_json

        if self._registered_by is not None:
            result["registered_by"] = {
                "username": self._registered_by.username,
                "registered_at": self._registered_by.registered_at,
            }

        if self.supported_model_types:
            result["supported_model_types"] = self.supported_model_types

        if self.default_model_spec is not None:
            result["default_model_spec"] = self.default_model_spec

        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Cap":
        """Parse from dict"""
        urn = CapUrn.from_string(data["urn"])
        aliases = data.get("aliases") or []
        if not aliases:
            raise ValueError(
                f"cap {urn.to_string()!r} must declare at least one alias "
                "(the 'aliases' field is required and non-empty)"
            )
        cap = cls(urn, data["title"], aliases)
        cap.is_abstract = bool(data.get("abstract", False))

        if "cap_description" in data:
            cap.cap_description = data["cap_description"]

        if "documentation" in data:
            cap.documentation = data["documentation"]

        if "args" in data:
            cap.args = [CapArg.from_dict(a) for a in data["args"]]

        if "output" in data and data["output"] is not None:
            cap.output = CapOutput.from_dict(data["output"])

        if "metadata" in data:
            cap.metadata = data["metadata"]

        if "metadata_json" in data:
            cap._metadata_json = data["metadata_json"]

        if "registered_by" in data:
            rb = data["registered_by"]
            cap._registered_by = RegisteredBy(
                username=rb["username"],
                registered_at=rb["registered_at"],
            )

        cap.version = int(data.get("version", 0))
        cap.supported_model_types = data.get("supported_model_types", [])
        cap.default_model_spec = data.get("default_model_spec")

        return cap

    def __eq__(self, other):
        if not isinstance(other, Cap):
            return False
        return (
            self.urn == other.urn
            and self.title == other.title
            and sorted(self.aliases) == sorted(other.aliases)
            and self.is_abstract == other.is_abstract
        )
