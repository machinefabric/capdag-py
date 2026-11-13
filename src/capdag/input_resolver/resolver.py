"""Resolving a run's inputs — files, directories and globs — to the files
they name and what each of them is.

What a file is comes from the one detection every host runs
(:func:`~capdag.input_resolver.detection.detect_file_media`); this module adds
only the path resolution around it and the shape of the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from capdag.fabric.registry import FabricRegistry
from capdag.input_resolver.adapter import CartridgeAdapterInvoker
from capdag.input_resolver.detection import AdapterSource, detect_file_media
from capdag.input_resolver.path_resolver import resolve_items
from capdag.input_resolver.types import (
    ContentStructure,
    InputItem,
    NoFilesResolvedError,
    ResolvedFile,
    ResolvedInputSet,
)
from capdag.input_resolver.value_adapter_registry import ValueAdapterRegistry
from capdag.urn.media_urn import MediaUrn


@dataclass(frozen=True)
class Detection:
    """How a host detects its inputs: its fabric, the cartridges it can ask,
    and its value adapters."""

    registry: FabricRegistry
    adapters: AdapterSource
    invoker: CartridgeAdapterInvoker
    value_adapters: ValueAdapterRegistry


async def resolve_file(path: Path, detection: Detection) -> ResolvedFile:
    """What one file is, as a run's input: the media a host that cannot ask
    takes (:func:`~capdag.input_resolver.detection.primary_media`)."""
    found = await detect_file_media(
        Path(path),
        detection.registry,
        detection.adapters,
        detection.invoker,
        detection.value_adapters,
    )
    media_urn = found.primary()
    return ResolvedFile(
        path=found.path,
        media_urn=media_urn,
        size_bytes=found.size_bytes,
        content_structure=structure_from_marker_tags(MediaUrn.from_string(media_urn)),
    )


async def resolve_input(item: InputItem, detection: Detection) -> ResolvedInputSet:
    """Resolve one input item."""
    return await resolve_inputs([item], detection)


async def resolve_inputs(items: list[InputItem], detection: Detection) -> ResolvedInputSet:
    """Resolve input items to the files they name and what each is."""
    paths = resolve_items(items)
    files = [await resolve_file(path, detection) for path in paths]
    if not files:
        raise NoFilesResolvedError()
    return ResolvedInputSet.new(files)


async def resolve_paths(paths: list[str], detection: Detection) -> ResolvedInputSet:
    """Resolve string paths (a file, a directory or a glob each)."""
    return await resolve_inputs([InputItem.from_string(path) for path in paths], detection)


def structure_from_marker_tags(urn: MediaUrn) -> str:
    """The content structure a media URN's marker tags say."""
    has_list = urn.has_marker_tag("list")
    has_record = urn.has_marker_tag("record")
    if has_list and has_record:
        return ContentStructure.LIST_RECORD
    if has_list:
        return ContentStructure.LIST_OPAQUE
    if has_record:
        return ContentStructure.SCALAR_RECORD
    return ContentStructure.SCALAR_OPAQUE
