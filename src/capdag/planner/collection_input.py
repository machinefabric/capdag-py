"""Collection input — folder hierarchy for cap inputs.

This module defines CapInputCollection, a recursive folder tree of files
that can be flattened into a list of CapInputFile for cap execution.
Mirrors Rust's planner/collection_input.rs exactly.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from capdag.planner.argument_binding import CapInputFile, SourceEntityType

_COLLECTION_MEDIA_URN = "media:collection;record;textable"


class CollectionFile:
    """A single file within a collection folder."""

    __slots__ = ("listing_id", "file_path", "media_urn", "title", "security_bookmark")

    def __init__(self, listing_id: str, file_path: str, media_urn: str) -> None:
        self.listing_id = listing_id
        self.file_path = file_path
        self.media_urn = media_urn
        self.title: Optional[str] = None
        self.security_bookmark: Optional[bytes] = None  # runtime-only, never serialized

    def with_title(self, title: str) -> CollectionFile:
        self.title = title
        return self

    def with_security_bookmark(self, bookmark: bytes) -> CollectionFile:
        self.security_bookmark = bookmark
        return self

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "listing_id": self.listing_id,
            "file_path": self.file_path,
            "media_urn": self.media_urn,
        }
        if self.title is not None:
            d["title"] = self.title
        # security_bookmark is never serialized
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> CollectionFile:
        cf = CollectionFile(d["listing_id"], d["file_path"], d["media_urn"])
        if "title" in d:
            cf.title = d["title"]
        return cf

    def __repr__(self) -> str:
        return f"CollectionFile(listing_id={self.listing_id!r}, file_path={self.file_path!r})"


class CapInputCollection:
    """Recursive folder hierarchy for collection-type cap inputs.

    Represents a folder with direct files and named subfolders.
    Can be flattened into a list of CapInputFile for cap execution.
    """

    __slots__ = ("folder_id", "folder_name", "files", "folders", "media_urn")

    def __init__(self, folder_id: str, folder_name: str) -> None:
        self.folder_id = folder_id
        self.folder_name = folder_name
        self.files: List[CollectionFile] = []
        self.folders: Dict[str, CapInputCollection] = {}
        self.media_urn = _COLLECTION_MEDIA_URN

    def to_json(self) -> Any:
        """Serialize the entire tree to a JSON-compatible value."""
        return json.loads(json.dumps(self.to_dict()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "folder_id": self.folder_id,
            "folder_name": self.folder_name,
            "files": [f.to_dict() for f in self.files],
            "folders": {name: folder.to_dict() for name, folder in self.folders.items()},
            "media_urn": self.media_urn,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> CapInputCollection:
        c = CapInputCollection(d["folder_id"], d["folder_name"])
        c.files = [CollectionFile.from_dict(f) for f in d.get("files", [])]
        c.folders = {
            name: CapInputCollection.from_dict(folder_data)
            for name, folder_data in d.get("folders", {}).items()
        }
        return c

    def flatten_to_files(self) -> List[CapInputFile]:
        """Recursively collect all files into a flat list of CapInputFile."""
        result: List[CapInputFile] = []
        self._collect_files_recursive(result)
        return result

    def total_file_count(self) -> int:
        """Recursively count all files in this node and all descendants."""
        count = len(self.files)
        for subfolder in self.folders.values():
            count += subfolder.total_file_count()
        return count

    def total_folder_count(self) -> int:
        """Recursively count all subfolder entries (not including self)."""
        count = len(self.folders)
        for subfolder in self.folders.values():
            count += subfolder.total_folder_count()
        return count

    def is_empty(self) -> bool:
        """Shallow check — True only if this node has no direct files and no subfolders."""
        return len(self.files) == 0 and len(self.folders) == 0

    def _collect_files_recursive(self, result: List[CapInputFile]) -> None:
        for cf in self.files:
            input_file = CapInputFile(cf.file_path, cf.media_urn)
            input_file.source_id = cf.listing_id
            input_file.source_type = SourceEntityType.LISTING
            if cf.security_bookmark is not None:
                input_file.security_bookmark = cf.security_bookmark
            result.append(input_file)

        for subfolder in self.folders.values():
            subfolder._collect_files_recursive(result)

    def __repr__(self) -> str:
        return (
            f"CapInputCollection(folder={self.folder_name!r}, "
            f"files={len(self.files)}, subfolders={len(self.folders)})"
        )
