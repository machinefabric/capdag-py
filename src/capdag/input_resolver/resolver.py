"""Input resolver combining path expansion with extension-based media detection."""

from __future__ import annotations

from pathlib import Path
import tempfile
import re

from capdag.input_resolver.adapter import CartridgeAdapterInvoker
from capdag.input_resolver.adapters.registry import MediaAdapterRegistry

from capdag.input_resolver.path_resolver import resolve_items
from capdag.input_resolver.types import (
    ContentStructure,
    InspectionFailedError,
    InputItem,
    NoFilesResolvedError,
    ResolvedFile,
    ResolvedInputSet,
)
from capdag.media.registry import ExtensionNotFoundError, FabricRegistry
from capdag.urn.media_urn import MediaUrn


def discriminate_candidates_by_validation(
    content: bytes,
    candidate_urns: list[str],
    media_registry: FabricRegistry,
    baseline_urn: str,
) -> list[str]:
    """Filter candidate URNs using validation rules and baseline specificity."""
    if not candidate_urns:
        return []

    baseline = MediaUrn.from_string(baseline_urn)
    content_str = content.decode("utf-8", errors="ignore")
    survivors: list[str] = []

    for urn_str in candidate_urns:
        spec = media_registry.get_cached_media_spec(urn_str)
        if spec is None:
            survivors.append(urn_str)
            continue

        validation = spec.validation or {}
        pattern = validation.get("pattern")
        if pattern:
            if re.fullmatch(pattern, content_str, flags=re.DOTALL) is not None:
                survivors.append(urn_str)
            continue

        candidate = MediaUrn.from_string(urn_str)
        if not candidate.conforms_to(baseline):
            survivors.append(urn_str)

    return survivors


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
    registry = FabricRegistry.new_for_test(Path(tempfile.gettempdir()) / "capdag_media_registry")
    return detect_file_with_media_registry(path, registry)


def detect_file_with_media_registry(path: Path, media_registry: FabricRegistry) -> ResolvedFile:
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


async def detect_file_confirmed(
    path: Path,
    adapter_registry: MediaAdapterRegistry,
    invoker: CartridgeAdapterInvoker,
) -> ResolvedFile:
    stat = path.stat()
    ext = path.suffix[1:].lower() if path.suffix.startswith(".") else ""
    adapters = adapter_registry.find_adapters_for_extension(ext)
    if not adapters:
        raise InspectionFailedError(
            path,
            "No content-inspection adapter registered for extension "
            f"'.{ext}'. A cartridge must register an adapter for this file type.",
        )

    returned: list[tuple[MediaUrn, str, str]] = []
    for cartridge_id, _adapter_urn in adapters:
        response = await invoker.invoke_adapter_selection(cartridge_id, path)
        if response:
            for urn_str in response:
                urn = MediaUrn.from_string(urn_str)
                returned.append((urn, urn_str, cartridge_id))

    if not returned:
        consulted = [cartridge_id for cartridge_id, _ in adapters]
        raise InspectionFailedError(
            path,
            "All registered adapters returned no match "
            f"(extension '.{ext}'). Adapters consulted: {consulted}. "
            "The file content does not match any registered media type.",
        )

    best_specificity = max(urn.specificity() for urn, _, _ in returned)
    ties = [entry for entry in returned if entry[0].specificity() == best_specificity]
    undominated: list[tuple[MediaUrn, str, str]] = []
    for candidate in ties:
        dominated = any(
            candidate is not other and candidate[0].conforms_to(other[0])
            for other in ties
        )
        if not dominated:
            undominated.append(candidate)

    if len(undominated) > 1:
        tie_descs = [f"'{urn_str}' (from cartridge '{cid}')" for _, urn_str, cid in undominated]
        raise InspectionFailedError(
            path,
            "Ambiguous adapter selection: multiple adapters returned URNs at the same "
            "specificity level with no conformance relationship: "
            + ", ".join(tie_descs)
            + ". This indicates a registration conflict that should have been caught at "
            "cap group registration time.",
        )

    selected_urn, selected_urn_str, _ = max(returned, key=lambda entry: entry[0].specificity())
    return ResolvedFile(
        path=path,
        media_urn=selected_urn_str,
        size_bytes=stat.st_size,
        content_structure=structure_from_marker_tags(selected_urn),
    )


async def resolve_inputs_confirmed(
    items: list[InputItem],
    adapter_registry: MediaAdapterRegistry,
    invoker: CartridgeAdapterInvoker,
) -> ResolvedInputSet:
    paths = resolve_items(items)
    files = [await detect_file_confirmed(path, adapter_registry, invoker) for path in paths]
    if not files:
        raise NoFilesResolvedError()
    return ResolvedInputSet.new(files)
