"""Input resolver combining path expansion with extension-based media detection."""

from __future__ import annotations

from pathlib import Path

from capdag.input_resolver.path_resolver import resolve_items
from capdag.input_resolver.types import (
    ContentStructure,
    InputItem,
    NoFilesResolvedError,
    ResolvedFile,
    ResolvedInputSet,
)
from capdag.media.registry import ExtensionNotFoundError, MediaUrnRegistry
from capdag.urn.media_urn import MediaUrn


def resolve_input(item: InputItem) -> ResolvedInputSet:
    return resolve_inputs([item])


def resolve_inputs(items: list[InputItem]) -> ResolvedInputSet:
    paths = resolve_items(items)
    files = [detect_file(path) for path in paths]
    if not files:
        raise NoFilesResolvedError()
    return ResolvedInputSet.new(files)


def resolve_paths(paths: list[str]) -> ResolvedInputSet:
    return resolve_inputs([InputItem.from_string(path) for path in paths])


def detect_file(path: Path) -> ResolvedFile:
    registry = MediaUrnRegistry.new_for_test(Path("/tmp/capdag_media_registry"))
    return detect_file_with_media_registry(path, registry)


def detect_file_with_media_registry(path: Path, media_registry: MediaUrnRegistry) -> ResolvedFile:
    stat = path.stat()
    ext = path.suffix[1:].lower() if path.suffix.startswith(".") else None

    media_urn = "media:"
    content_structure = ContentStructure.SCALAR_OPAQUE
    if ext:
        try:
            urns = media_registry.media_urns_for_extension(ext)
        except ExtensionNotFoundError:
            urns = []
        best: MediaUrn | None = None
        best_str: str | None = None
        for urn_str in urns:
            urn = MediaUrn.from_string(urn_str)
            if best is None or urn.specificity() > best.specificity():
                best = urn
                best_str = urn_str
        if best is not None and best_str is not None:
            media_urn = best_str
            content_structure = structure_from_marker_tags(best)

    return ResolvedFile(
        path=path,
        media_urn=media_urn,
        size_bytes=stat.st_size,
        content_structure=content_structure,
    )


def structure_from_marker_tags(urn: MediaUrn) -> str:
    has_list = urn.has_marker_tag("list")
    has_record = urn.has_marker_tag("record")
    if has_list and has_record:
        return ContentStructure.LIST_RECORD
    if has_list:
        return ContentStructure.LIST_OPAQUE
    if has_record:
        return ContentStructure.SCALAR_RECORD
    return ContentStructure.SCALAR_OPAQUE
