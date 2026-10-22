"""Fabric dims — the axes definitions are built along.

A dim (a language, a file type, a quantisation, …) is a fabric definition
like a cap, a media def or an alias: published on its own at
``dims/<sha256-of-name>/<defver>.json`` and pinned by a manifest's ``dims``
map. Its body says what the dim is and which values it may take, each with
its own documentation.

A cap or media definition names the dims it was built from, and the value
chosen from each, in its ``dims`` (:class:`DimRef`). Its own
``documentation`` is only what is specific to it; what a dim and a value mean
is read from the dim. A reader shows both.

This module imports nothing else from capdag, so the cap and media definition
modules can read it without an import cycle through the registry.
"""

import re
from typing import Any, Dict, List, Optional, Sequence

_DIM_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*\Z")


class DimError(ValueError):
    """Why a dim body is not one this library can hold."""


def is_dim_name(name: Any) -> bool:
    """Whether ``name`` is a dim name: ``^[a-z][a-z0-9-]*$``."""
    return isinstance(name, str) and _DIM_NAME_RE.match(name) is not None


def _object(data: Any, what: str) -> Dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(f"{what} is not an object: {data!r}")
    return data


def _refuse_unknown(data: Dict[str, Any], known: frozenset, what: str) -> None:
    """Unknown fields are refused: a key this library does not know would be
    dropped when the body is written back out, and the copy would no longer
    say what the registry said."""
    unknown = sorted(key for key in data if key not in known)
    if unknown:
        raise ValueError(
            f"{what} carries unknown field(s): {', '.join(unknown)}; "
            f"expected {', '.join(sorted(known))}"
        )


def _string(data: Dict[str, Any], key: str, what: str) -> str:
    if key not in data:
        raise ValueError(f"{what} is missing field `{key}`")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{what} field `{key}` is not a string: {value!r}")
    return value


def _optional_string(data: Dict[str, Any], key: str, what: str) -> Optional[str]:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"{what} field `{key}` is not a string: {value!r}")
    return value


def _list(data: Dict[str, Any], key: str, what: str) -> List[Any]:
    if key not in data:
        raise ValueError(f"{what} is missing field `{key}`")
    value = data[key]
    if not isinstance(value, list):
        raise ValueError(f"{what} field `{key}` is not an array: {value!r}")
    return value


class DimRef:
    """One dim a definition was built from, and the value chosen from it. The
    entries of a definition's ``dims``, in the order its source references
    them.

    Unknown fields are refused, as for arguments and outputs: a key this
    library does not know would be dropped when the definition is written
    back out, and the copy would no longer say what the registry said.
    """

    KNOWN_KEYS = frozenset({"dim", "value"})

    def __init__(self, dim: str, value: str):
        # The dim's name.
        self.dim = dim
        # The name of the value chosen from that dim.
        self.value = value

    def to_dict(self) -> Dict[str, Any]:
        return {"dim": self.dim, "value": self.value}

    @classmethod
    def from_dict(cls, data: Any) -> "DimRef":
        data = _object(data, "dims entry")
        _refuse_unknown(data, cls.KNOWN_KEYS, "dims entry")
        return cls(
            dim=_string(data, "dim", "dims entry"),
            value=_string(data, "value", "dims entry"),
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DimRef) and self.dim == other.dim and self.value == other.value

    def __hash__(self) -> int:
        return hash((self.dim, self.value))

    def __repr__(self) -> str:
        return f"DimRef({self.dim!r}, {self.value!r})"


def dim_refs_from_list(data: Any, what: str) -> List[DimRef]:
    """Read a definition's ``dims`` array. ``what`` names the definition in
    errors."""
    if not isinstance(data, list):
        raise ValueError(f"{what} dims is not an array: {data!r}")
    return [DimRef.from_dict(entry) for entry in data]


class DimTag:
    """A tag a dim value contributes to the URN of every definition built
    with it. ``value`` is ``*`` for a marker tag."""

    KNOWN_KEYS = frozenset({"key", "value"})

    def __init__(self, key: str, value: str):
        self.key = key
        self.value = value

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "value": self.value}

    @classmethod
    def from_dict(cls, data: Any) -> "DimTag":
        data = _object(data, "dim value tag")
        _refuse_unknown(data, cls.KNOWN_KEYS, "dim value tag")
        return cls(
            key=_string(data, "key", "dim value tag"),
            value=_string(data, "value", "dim value tag"),
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, DimTag) and self.key == other.key and self.value == other.value

    def __repr__(self) -> str:
        return f"DimTag({self.key!r}, {self.value!r})"


class StoredDimValue:
    """One value a dim may take."""

    KNOWN_KEYS = frozenset({"name", "title", "tags", "documentation", "media_type", "extensions"})

    def __init__(
        self,
        name: str,
        title: str,
        tags: List[DimTag],
        documentation: Optional[str] = None,
        media_type: Optional[str] = None,
        extensions: Optional[List[str]] = None,
    ):
        # The value's name, unique within the dim.
        self.name = name
        # Display-friendly title of the value.
        self.title = title
        # The tags the value contributes. At least one.
        self.tags = list(tags)
        # Markdown documentation of what choosing this value means.
        self.documentation = documentation
        # The MIME media type the value gives the media defs built with it.
        self.media_type = media_type
        # The file extensions the value gives the media defs built with it.
        self.extensions = list(extensions or [])

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": self.name,
            "title": self.title,
            "tags": [tag.to_dict() for tag in self.tags],
        }
        if self.documentation is not None:
            result["documentation"] = self.documentation
        if self.media_type is not None:
            result["media_type"] = self.media_type
        if self.extensions:
            result["extensions"] = list(self.extensions)
        return result

    @classmethod
    def from_dict(cls, data: Any) -> "StoredDimValue":
        data = _object(data, "dim value")
        _refuse_unknown(data, cls.KNOWN_KEYS, "dim value")
        extensions = data.get("extensions", [])
        if not isinstance(extensions, list) or not all(isinstance(e, str) for e in extensions):
            raise ValueError(f"dim value field `extensions` is not an array of strings: {extensions!r}")
        return cls(
            name=_string(data, "name", "dim value"),
            title=_string(data, "title", "dim value"),
            tags=[DimTag.from_dict(tag) for tag in _list(data, "tags", "dim value")],
            documentation=_optional_string(data, "documentation", "dim value"),
            media_type=_optional_string(data, "media_type", "dim value"),
            extensions=extensions,
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StoredDimValue) and self.to_dict() == other.to_dict()


class StoredDim:
    """Stored dim definition. Mirrors ``fabric/dim.schema.json`` on the wire
    and is the body cached at ``dims/<sha256-of-name>/<defver>.json``."""

    KNOWN_KEYS = frozenset({"name", "version", "title", "documentation", "values"})

    def __init__(
        self,
        name: str,
        version: int,
        title: str,
        documentation: str,
        values: List[StoredDimValue],
    ):
        # The dim's name, unique across the snapshot.
        self.name = name
        # Per-definition version. Always >= 1 — dims exist only in the
        # versioned regime.
        self.version = version
        # Display-friendly title of the dim.
        self.title = title
        # Markdown documentation of what the dim is.
        self.documentation = documentation
        # The values the dim may take, in the order the dim declares them.
        self.values = list(values)

    def value(self, name: str) -> Optional[StoredDimValue]:
        """The value named ``name``, if the dim declares it."""
        return next((v for v in self.values if v.name == name), None)

    def validate(self) -> None:
        """Hold the body to what ``dim.schema.json`` says beyond its field
        types: a dim name, at least one value, value names unique, every value
        with a tag. Raises :class:`DimError`."""
        if not is_dim_name(self.name):
            raise DimError(
                f"dim name '{self.name}' is not a dim name (lowercase letters, digits "
                f"and '-', starting with a letter)"
            )
        if not self.values:
            raise DimError(f"dim '{self.name}' declares no values")
        seen = set()
        for v in self.values:
            if v.name in seen:
                raise DimError(f"dim '{self.name}' declares value '{v.name}' more than once")
            seen.add(v.name)
            if not v.tags:
                raise DimError(f"dim '{self.name}' value '{v.name}' contributes no tag")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "title": self.title,
            "documentation": self.documentation,
            "values": [v.to_dict() for v in self.values],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "StoredDim":
        data = _object(data, "dim")
        _refuse_unknown(data, cls.KNOWN_KEYS, "dim")
        if "version" not in data:
            raise ValueError("dim is missing field `version`")
        version = data["version"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 0:
            raise ValueError(f"dim field `version` is not a non-negative integer: {version!r}")
        return cls(
            name=_string(data, "name", "dim"),
            version=version,
            title=_string(data, "title", "dim"),
            documentation=_string(data, "documentation", "dim"),
            values=[StoredDimValue.from_dict(v) for v in _list(data, "values", "dim")],
        )

    def __eq__(self, other: object) -> bool:
        return isinstance(other, StoredDim) and self.to_dict() == other.to_dict()

    def __repr__(self) -> str:
        return f"StoredDim({self.name!r}, version={self.version})"


def check_dim_refs(dims: Sequence[DimRef]) -> None:
    """A definition's ``dims`` names each dim at most once, and only by dim
    and value names. Raises ``ValueError`` saying why not, naming the
    offending entry."""
    seen = set()
    for r in dims:
        if not is_dim_name(r.dim):
            raise ValueError(f"'{r.dim}' is not a dim name")
        if not r.value:
            raise ValueError(f"dim '{r.dim}' is named without a value")
        if r.dim in seen:
            raise ValueError(f"dim '{r.dim}' is named more than once")
        seen.add(r.dim)
