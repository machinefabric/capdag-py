"""Core types for input resolution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from capdag.urn.media_urn import MediaUrn


class InputResolverError(Exception):
    """Base exception for input resolution failures."""


class NotFoundError(InputResolverError):
    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"Path not found: {self.path}")


class PermissionDeniedError(InputResolverError):
    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"Permission denied: {self.path}")


class InvalidGlobError(InputResolverError):
    def __init__(self, pattern: str, reason: str):
        self.pattern = pattern
        self.reason = reason
        super().__init__(f"Invalid glob pattern '{pattern}': {reason}")


class IoError(InputResolverError):
    def __init__(self, path: Path, error: Exception):
        self.path = Path(path)
        self.error = error
        super().__init__(f"IO error at {self.path}: {error}")


class EmptyInputError(InputResolverError):
    def __init__(self):
        super().__init__("No input paths provided")


class NoFilesResolvedError(InputResolverError):
    def __init__(self):
        super().__init__("No files found after resolving all inputs")


class InspectionFailedError(InputResolverError):
    def __init__(self, path: Path, reason: str):
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"Inspection failed for {self.path}: {reason}")


class SymlinkCycleError(InputResolverError):
    def __init__(self, path: Path):
        self.path = Path(path)
        super().__init__(f"Symlink cycle detected at: {self.path}")


@dataclass(frozen=True)
class InputItem:
    kind: str
    value: Path | str

    @staticmethod
    def file(path: Path | str) -> "InputItem":
        return InputItem("file", Path(path))

    @staticmethod
    def directory(path: Path | str) -> "InputItem":
        return InputItem("directory", Path(path))

    @staticmethod
    def glob(pattern: str) -> "InputItem":
        return InputItem("glob", pattern)

    @staticmethod
    def from_string(value: str) -> "InputItem":
        if any(ch in value for ch in "*?["):
            return InputItem.glob(value)
        path = Path(value)
        if path.is_dir():
            return InputItem.directory(path)
        return InputItem.file(path)


class ContentStructure:
    SCALAR_OPAQUE = "scalar/opaque"
    SCALAR_RECORD = "scalar/record"
    LIST_OPAQUE = "list/opaque"
    LIST_RECORD = "list/record"

    @staticmethod
    def is_list(value: str) -> bool:
        return value in (ContentStructure.LIST_OPAQUE, ContentStructure.LIST_RECORD)

    @staticmethod
    def is_record(value: str) -> bool:
        return value in (ContentStructure.SCALAR_RECORD, ContentStructure.LIST_RECORD)


@dataclass
class ResolvedFile:
    path: Path
    media_urn: str
    size_bytes: int
    content_structure: str


@dataclass
class ResolvedInputSet:
    files: list[ResolvedFile]
    is_sequence: bool
    common_media: Optional[str]

    @classmethod
    def new(cls, files: list[ResolvedFile]) -> "ResolvedInputSet":
        is_sequence = len(files) > 1
        common_media: Optional[str] = None
        if files:
            first = MediaUrn.from_string(files[0].media_urn)
            if all(first.is_equivalent(MediaUrn.from_string(f.media_urn)) for f in files[1:]):
                common_media = files[0].media_urn
        return cls(files=files, is_sequence=is_sequence, common_media=common_media)

    def is_homogeneous(self) -> bool:
        """Returns True if all files share the same (equivalent) media URN."""
        return self.common_media is not None
