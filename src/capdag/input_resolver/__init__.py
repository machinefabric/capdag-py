"""Input resolver mirror."""

from capdag.input_resolver.adapter import CartridgeAdapterInvoker, MAX_CONTENT_INSPECTION_BYTES
from capdag.input_resolver.adapters import AdapterRegistrationError, MediaAdapterRegistry
from capdag.input_resolver.detection import (
    AdapterSource,
    FileMedia,
    NoAdapters,
    NoInvoker,
    detect_file_media,
    extension_media,
    primary_media,
)
from capdag.input_resolver.os_filter import should_exclude, should_exclude_dir
from capdag.input_resolver.path_resolver import (
    resolve_directory,
    resolve_glob,
    resolve_item,
    resolve_items,
)
from capdag.input_resolver.resolver import (
    Detection,
    resolve_file,
    resolve_input,
    resolve_inputs,
    resolve_paths,
    structure_from_marker_tags,
)
from capdag.input_resolver.types import (
    ContentStructure,
    EmptyInputError,
    FabricUnavailableError,
    InspectionFailedError,
    InputItem,
    InputResolverError,
    InvalidGlobError,
    IoError,
    NoExtensionError,
    NoFilesResolvedError,
    NotFoundError,
    PermissionDeniedError,
    ResolvedFile,
    ResolvedInputSet,
    SymlinkCycleError,
    UnknownExtensionError,
)
from capdag.input_resolver.value_adapter import ValueAdapter
from capdag.input_resolver.value_adapter_registry import ValueAdapterRegistry

__all__ = [
    "AdapterRegistrationError",
    "AdapterSource",
    "CartridgeAdapterInvoker",
    "ContentStructure",
    "Detection",
    "EmptyInputError",
    "FabricUnavailableError",
    "FileMedia",
    "InspectionFailedError",
    "InputItem",
    "InputResolverError",
    "InvalidGlobError",
    "IoError",
    "MAX_CONTENT_INSPECTION_BYTES",
    "MediaAdapterRegistry",
    "NoAdapters",
    "NoExtensionError",
    "NoFilesResolvedError",
    "NoInvoker",
    "NotFoundError",
    "PermissionDeniedError",
    "ResolvedFile",
    "ResolvedInputSet",
    "SymlinkCycleError",
    "UnknownExtensionError",
    "ValueAdapter",
    "ValueAdapterRegistry",
    "detect_file_media",
    "extension_media",
    "primary_media",
    "resolve_directory",
    "resolve_file",
    "resolve_glob",
    "resolve_input",
    "resolve_inputs",
    "resolve_item",
    "resolve_items",
    "resolve_paths",
    "should_exclude",
    "should_exclude_dir",
    "structure_from_marker_tags",
]
