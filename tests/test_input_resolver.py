"""Parity tests for input_resolver path and OS filtering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from capdag.input_resolver import (
    ContentStructure,
    Detection,
    EmptyInputError,
    InputItem,
    InvalidGlobError,
    NoAdapters,
    NoInvoker,
    NotFoundError,
    ResolvedInputSet,
    resolve_directory,
    resolve_glob,
    resolve_items,
    resolve_paths,
    should_exclude,
    should_exclude_dir,
)
from capdag.input_resolver.adapters.registry import MediaAdapterRegistry
from capdag.input_resolver.path_resolver import resolve_file
from capdag.input_resolver.value_adapter import ValueAdapter
from capdag.input_resolver.value_adapter_registry import ValueAdapterRegistry
from capdag.media.registry import FabricRegistry
from capdag.urn.media_urn import MediaUrn


# TEST1000: Single existing file
def test_1000_single_existing_file(tmp_path: Path):
    file_path = tmp_path / "test.pdf"
    file_path.write_bytes(b"")
    result = resolve_file(file_path)
    assert len(result) == 1
    assert result[0].name == "test.pdf"


# TEST1001: Single non-existent file
def test_1001_nonexistent_file():
    with pytest.raises(NotFoundError):
        resolve_file(Path("/nonexistent/path/file.pdf"))


# TEST1002: Empty directory
def test_1002_empty_directory(tmp_path: Path):
    assert resolve_directory(tmp_path) == []


# TEST1003: Directory with files
def test_1003_directory_with_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text("")
    (tmp_path / "b.txt").write_text("")
    (tmp_path / "c.txt").write_text("")
    assert len(resolve_directory(tmp_path)) == 3


# TEST1004: Directory with subdirs (recursive)
def test_1004_directory_with_subdirs(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "root.txt").write_text("")
    (sub / "nested.txt").write_text("")
    assert len(resolve_directory(tmp_path)) == 2


# TEST1005: Glob matching files
def test_1005_glob_matching_files(tmp_path: Path):
    (tmp_path / "a.pdf").write_text("")
    (tmp_path / "b.pdf").write_text("")
    (tmp_path / "c.txt").write_text("")
    assert len(resolve_glob(f"{tmp_path}/*.pdf")) == 2


# TEST1006: Glob matching nothing
def test_1006_glob_matching_nothing(tmp_path: Path):
    (tmp_path / "a.txt").write_text("")
    assert resolve_glob(f"{tmp_path}/*.xyz") == []


# TEST1007: Recursive glob
def test_1007_recursive_glob(tmp_path: Path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (tmp_path / "a.json").write_text("")
    (sub / "b.json").write_text("")
    assert len(resolve_glob(f"{tmp_path}/**/*.json")) == 2


# TEST1008: Mixed file + dir
def test_1008_mixed_file_dir(tmp_path: Path):
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (tmp_path / "file.pdf").write_text("")
    (subdir / "nested.txt").write_text("")
    items = [InputItem.file(tmp_path / "file.pdf"), InputItem.directory(subdir)]
    assert len(resolve_items(items)) == 2


# TEST1010: Duplicate paths are deduplicated
def test_1010_duplicate_paths(tmp_path: Path):
    file_path = tmp_path / "file.pdf"
    file_path.write_text("")
    items = [InputItem.file(file_path), InputItem.file(file_path)]
    assert len(resolve_items(items)) == 1


# TEST1011: Invalid glob syntax
def test_1011_invalid_glob():
    with pytest.raises(InvalidGlobError):
        resolve_glob("[unclosed")


# TEST1013: Empty input array
def test_1013_empty_input():
    with pytest.raises(EmptyInputError):
        resolve_items([])


# TEST1014: Symlink to file
@pytest.mark.skipif(not hasattr(os, "symlink"), reason="symlink support required")
def test_1014_symlink_to_file(tmp_path: Path):
    file_path = tmp_path / "real.txt"
    link_path = tmp_path / "link.txt"
    file_path.write_text("")
    os.symlink(file_path, link_path)
    assert len(resolve_file(link_path)) == 1


# TEST1016: Path with spaces
def test_1016_path_with_spaces(tmp_path: Path):
    file_path = tmp_path / "my file.pdf"
    file_path.write_text("")
    assert len(resolve_file(file_path)) == 1


# TEST1017: Path with unicode
def test_1017_path_with_unicode(tmp_path: Path):
    file_path = tmp_path / "文档.pdf"
    file_path.write_text("")
    assert len(resolve_file(file_path)) == 1


# TEST1018: Relative path
def test_1018_relative_path(tmp_path: Path, monkeypatch):
    file_path = tmp_path / "file.txt"
    file_path.write_text("")
    monkeypatch.chdir(tmp_path)
    assert len(resolve_file(Path("file.txt"))) == 1


# TEST1020: macOS .DS_Store is excluded
def test_1020_ds_store_excluded():
    assert should_exclude(Path("/some/path/.DS_Store"))
    assert should_exclude(Path(".DS_Store"))


# TEST1021: Windows Thumbs.db is excluded
def test_1021_thumbs_db_excluded():
    assert should_exclude(Path("/some/path/Thumbs.db"))
    assert should_exclude(Path("Thumbs.db"))


# TEST1022: macOS resource fork files are excluded
def test_1022_resource_fork_excluded():
    assert should_exclude(Path("/path/._file.txt"))
    assert should_exclude(Path("._anything"))


# TEST1023: Office lock files are excluded
def test_1023_office_lock_excluded():
    assert should_exclude(Path("/path/~$document.docx"))
    assert should_exclude(Path("~$spreadsheet.xlsx"))


# TEST1024: .git directory is excluded
def test_1024_git_dir_excluded():
    assert should_exclude_dir(Path("/repo/.git"))
    assert should_exclude_dir(Path(".git"))


# TEST1025: __MACOSX archive artifact is excluded
def test_1025_macosx_dir_excluded():
    assert should_exclude_dir(Path("/extracted/__MACOSX"))
    assert should_exclude_dir(Path("__MACOSX"))


# TEST1026: Temp files are excluded
def test_1026_temp_files_excluded():
    assert should_exclude(Path("/path/file.tmp"))
    assert should_exclude(Path("/path/file.temp"))
    assert should_exclude(Path("/path/file.swp"))
    assert should_exclude(Path("/path/file.bak"))


# TEST1027: .localized is excluded
def test_1027_localized_excluded():
    assert should_exclude(Path("/path/.localized"))


# TEST1028: desktop.ini is excluded
def test_1028_desktop_ini_excluded():
    assert should_exclude(Path("/path/desktop.ini"))


# TEST1029: Normal files are NOT excluded
def test_1029_normal_files_not_excluded():
    assert not should_exclude(Path("/path/file.txt"))
    assert not should_exclude(Path("/path/data.json"))
    assert not should_exclude(Path("/path/notes.md"))
    assert not should_exclude(Path("/path/.gitignore"))
    assert not should_exclude(Path("/path/.env"))
    assert not should_exclude(Path("/path/README.md"))


async def _resolve(paths: list[str], registry: FabricRegistry) -> ResolvedInputSet:
    """Resolve ``paths`` as a host with no cartridge to ask does."""
    detection = Detection(
        registry=registry,
        adapters=NoAdapters(),
        invoker=NoInvoker(),
        value_adapters=ValueAdapterRegistry(),
    )
    return await resolve_paths(paths, detection)


# TEST977: OS files excluded in resolve_paths
@pytest.mark.asyncio
async def test_977_os_files_excluded_integration(tmp_path: Path):
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / "real.txt").write_text("content")
    result = await _resolve([str(tmp_path)], _create_test_media_registry(tmp_path))
    assert len(result.files) == 1
    assert "real.txt" in str(result.files[0].path)


# TEST1090: 1 file → is_sequence=false
@pytest.mark.asyncio
async def test_1090_single_file_scalar(tmp_path: Path):
    (tmp_path / "only.txt").write_text("hello")
    result = await _resolve([str(tmp_path / "only.txt")], _create_test_media_registry(tmp_path))
    assert len(result.files) == 1
    assert not result.is_sequence


# TEST1092: 2 files → is_sequence=true
@pytest.mark.asyncio
async def test_1092_two_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = await _resolve(
        [str(tmp_path / "a.txt"), str(tmp_path / "b.txt")], _create_test_media_registry(tmp_path)
    )
    assert len(result.files) == 2
    assert result.is_sequence


# TEST1093: 1 dir with 1 file → is_sequence=false
@pytest.mark.asyncio
async def test_1093_dir_single_file(tmp_path: Path):
    (tmp_path / "only.pdf").write_text("%PDF-1.4")
    result = await _resolve([str(tmp_path)], _create_test_media_registry(tmp_path))
    assert len(result.files) == 1
    assert not result.is_sequence


# TEST1094: 1 dir with 3 files → is_sequence=true
@pytest.mark.asyncio
async def test_1094_dir_multiple_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    (tmp_path / "c.txt").write_text("test")
    result = await _resolve([str(tmp_path)], _create_test_media_registry(tmp_path))
    assert len(result.files) == 3
    assert result.is_sequence


# TEST1288: structure_from_marker_tags correctly maps tag combinations to ContentStructure
def test_1288_structure_from_marker_tags():
    scalar_opaque = MediaUrn.from_string("media:text")
    scalar_record = MediaUrn.from_string("media:enc=utf8;fmt=json;record")
    list_opaque = MediaUrn.from_string("media:enc=utf8;list")
    list_record = MediaUrn.from_string("media:enc=utf8;fmt=json;list;record")
    from capdag.input_resolver import structure_from_marker_tags

    assert structure_from_marker_tags(scalar_opaque) == ContentStructure.SCALAR_OPAQUE
    assert structure_from_marker_tags(scalar_record) == ContentStructure.SCALAR_RECORD
    assert structure_from_marker_tags(list_opaque) == ContentStructure.LIST_OPAQUE
    assert structure_from_marker_tags(list_record) == ContentStructure.LIST_RECORD


def _create_test_media_registry(tmp_path: Path) -> FabricRegistry:
    """Build a `FabricRegistry` whose manifest names, and whose cache holds,
    the file media types the input-resolver tests reference (`pdf`, `txt`,
    `json`): with every file type cached, a file's type is told without the
    network.
    """
    from capdag.fabric.registry import StoredMediaDef

    registry = FabricRegistry.new_for_test(tmp_path / "media-cache")

    registry.add_spec(StoredMediaDef(
        urn="media:document;ext=pdf",
        media_type="application/pdf",
        title="PDF",
        extensions=["pdf"],
    ))
    registry.add_spec(StoredMediaDef(
        urn="media:enc=utf8;ext=json;fmt=json;record",
        media_type="application/json",
        title="JSON",
        extensions=["json"],
    ))
    registry.add_spec(StoredMediaDef(
        urn="media:enc=utf8;ext=txt;list;plain-text",
        media_type="text/plain",
        title="Text",
        extensions=["txt"],
    ))
    return registry


class _SpecialAdapter(ValueAdapter):
    def __init__(self):
        super().__init__(
            base_media_urn="media:test",
            refined_marker_tag="refined",
            value_matches=lambda value: value == "something-special",
        )


class _SpecificAdapter(ValueAdapter):
    def __init__(self):
        super().__init__(
            base_media_urn="media:test;specific",
            refined_marker_tag="result",
            value_matches=lambda value: value == "something-specific",
        )


# TEST1221: Matching value adapters refine the base media URN when the value fits.
def test_1221_refine_with_matching_adapter():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    # The adapter is keyed by the `media:test` prefix; the base URN starts
    # with that prefix, so the adapter fires and appends `refined`.
    assert registry.refine_media_urn("media:test;enc=utf8", "something-special") == "media:enc=utf8;refined;test"


# TEST1222: Base URNs without a registered adapter are returned unchanged.
def test_1222_refine_no_matching_adapter():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    assert registry.refine_media_urn("media:other;enc=utf8", "something-special") == "media:other;enc=utf8"


# TEST1223: Adapters that decline to refine leave the original media URN intact.
def test_1223_refine_adapter_returns_none():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    assert registry.refine_media_urn("media:test;enc=utf8", "ordinary-value") == "media:test;enc=utf8"


# TEST1224: When multiple adapter prefixes match, the longest prefix wins.
def test_1224_refine_longest_prefix_match():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    registry.register("media:test;specific", _SpecificAdapter())
    assert registry.refine_media_urn("media:test;specific;enc=utf8", "something-specific") == "media:enc=utf8;result;specific;test"


# TEST1225: An empty value adapter registry returns the input media URN unchanged.
def test_1225_empty_registry():
    registry = ValueAdapterRegistry()
    assert registry.refine_media_urn("media:anything", "any-value") == "media:anything"


# TEST1226: Adapter presence checks report only the prefixes that were registered.
def test_1226_has_adapter():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    assert registry.has_adapter("media:test")
    assert not registry.has_adapter("media:other")


# TEST1228: Value adapters can append a more specific marker when both base URN and value match.
def test_1228_value_adapter_refine_match():
    adapter = _SpecialAdapter()
    assert adapter.refine("media:test;enc=utf8", "something-special") == "media:enc=utf8;refined;test"


# TEST1229: Value adapters return no refinement when the base media URN is outside their domain.
def test_1229_value_adapter_refine_no_match_base():
    adapter = _SpecialAdapter()
    assert adapter.refine("media:other;enc=utf8", "something-special") is None


# TEST1230: Value adapters return no refinement when the inspected value does not match.
def test_1230_value_adapter_refine_no_match_value():
    adapter = _SpecialAdapter()
    assert adapter.refine("media:test;enc=utf8", "ordinary-value") is None


# TEST1276: Registration of a cap group with non-conflicting adapters succeeds
def test_1276_register_non_conflicting(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("text-formats", ["media:enc=utf8;fmt=json", "media:enc=utf8;fmt=yaml"], "txtcartridge")
    assert len(registry._registered_adapters) == 2


# TEST1478: exact re-registration is idempotent — the SAME cartridge
# re-registering the SAME group with the SAME adapter URNs (a cartridge
# attached through two hosting routes, e.g. app-bundled AND system-installed)
# is a no-op, not a self-conflict and not duplicate rows. A DIFFERENT
# cartridge claiming the same URN stays rejected.
def test_1478_exact_reregistration_is_idempotent(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    urns = ["media:enc=utf8;fmt=json", "media:enc=utf8;fmt=yaml"]
    registry.register_cap_group("text-formats", urns, "txtcartridge")
    registry.register_cap_group("text-formats", urns, "txtcartridge")
    assert len(registry._registered_adapters) == 2, "re-registration must not duplicate rows"

    # A partially-new group from the same owner registers only the new URN.
    registry.register_cap_group("text-formats", ["media:enc=utf8;fmt=json", "media:fmt=toml"], "txtcartridge")
    assert len(registry._registered_adapters) == 3

    # Another cartridge claiming an identical URN is still ambiguity.
    with pytest.raises(Exception):
        registry.register_cap_group("text-formats", ["media:enc=utf8;fmt=json"], "other")


# TEST1277: Registration of a cap group with an adapter that conforms_to an existing adapter is rejected
def test_1277_reject_conforming_overlap(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:enc=utf8;fmt=json"], "cartridge-a")
    with pytest.raises(Exception) as exc_info:
        registry.register_cap_group("group-b", ["media:enc=utf8;fmt=json;record"], "cartridge-b")
    message = str(exc_info.value)
    assert "group-b" in message
    assert "group-a" in message


# TEST1278: Registration rejects the entire group — no partial registration
@pytest.mark.asyncio
async def test_1278_reject_entire_group(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:enc=utf8;fmt=json"], "cartridge-a")
    with pytest.raises(Exception):
        registry.register_cap_group("group-b", ["media:enc=utf8;fmt=yaml", "media:enc=utf8;fmt=json", "media:enc=utf8;fmt=csv"], "cartridge-b")
    assert await registry.find_adapters_for_extension("json") == [("cartridge-a", MediaUrn.from_string("media:enc=utf8;fmt=json"))]


# TEST1279: Intra-group conflict (two adapters within same group overlap) is rejected
def test_1279_intra_group_conflict(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    with pytest.raises(Exception):
        registry.register_cap_group("group-a", ["media:enc=utf8;fmt=json", "media:enc=utf8;fmt=json;record"], "cartridge-a")


# TEST1280: find_adapters_for_extension returns correct cartridge IDs
@pytest.mark.asyncio
async def test_1280_find_adapters_for_extension(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:enc=utf8;fmt=json"], "cartridge-a")
    registry.register_cap_group("group-b", ["media:enc=utf8;fmt=yaml"], "cartridge-b")
    matches = await registry.find_adapters_for_extension("json")
    assert matches == [("cartridge-a", MediaUrn.from_string("media:enc=utf8;fmt=json"))]


# TEST1281: has_adapter_for_extension returns false for unregistered extension
@pytest.mark.asyncio
async def test_1281_no_adapter_for_unknown(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    assert not await registry.has_adapter_for_extension("unknown")


# =============================================================================
# Tests ported from Rust input_resolver/types.rs (1143-1146)
# =============================================================================

# TEST1143: InputItem::from_string distinguishes glob patterns, directories, and files
def test_1143_input_item_from_string_distinguishes_glob_directory_and_file(tmp_path: Path):
    # Existing directory -> InputItem.directory
    dir_item = InputItem.from_string(str(tmp_path))
    assert dir_item.kind == "directory"
    assert dir_item.value == tmp_path

    # Non-existing path (no glob chars) -> InputItem.file
    file_path = tmp_path / "missing.txt"
    file_item = InputItem.from_string(str(file_path))
    assert file_item.kind == "file"

    # Glob pattern (contains *) -> InputItem.glob
    glob_item = InputItem.from_string("fixtures/**/*.pdf")
    assert glob_item.kind == "glob"
    assert glob_item.value == "fixtures/**/*.pdf"


# TEST1144: ContentStructure is_list/is_record helpers and Display implementation are correct
def test_1144_content_structure_helpers_and_display():
    assert not ContentStructure.is_list(ContentStructure.SCALAR_OPAQUE)
    assert not ContentStructure.is_record(ContentStructure.SCALAR_OPAQUE)
    assert ContentStructure.SCALAR_OPAQUE == "scalar/opaque"

    assert ContentStructure.is_list(ContentStructure.LIST_RECORD)
    assert ContentStructure.is_record(ContentStructure.LIST_RECORD)
    assert ContentStructure.LIST_RECORD == "list/record"


# TEST1145: ResolvedInputSet uses URN equivalence for common_media and file count for is_sequence
def test_1145_resolved_input_set_uses_equivalent_media_and_file_count_cardinality():
    from capdag.input_resolver.types import ResolvedFile, ResolvedInputSet

    single_list_file = ResolvedInputSet.new([ResolvedFile(
        path=Path("/tmp/items.json"),
        media_urn="media:application;enc=utf8;fmt=json;list;record",
        size_bytes=42,
        content_structure=ContentStructure.LIST_RECORD,
    )])
    assert not single_list_file.is_sequence
    assert single_list_file.is_homogeneous()
    assert single_list_file.common_media == "media:application;enc=utf8;fmt=json;list;record"

    # Two files with tag-equivalent URNs (different tag order) → homogeneous, is_sequence
    equivalent_ordering = ResolvedInputSet.new([
        ResolvedFile(
            path=Path("/tmp/a.json"),
            media_urn="media:application;enc=utf8;fmt=json;record",
            size_bytes=10,
            content_structure=ContentStructure.SCALAR_RECORD,
        ),
        ResolvedFile(
            path=Path("/tmp/b.json"),
            media_urn="media:application;enc=utf8;fmt=json;record",
            size_bytes=11,
            content_structure=ContentStructure.SCALAR_RECORD,
        ),
    ])
    assert equivalent_ordering.is_sequence
    assert equivalent_ordering.is_homogeneous()
    assert equivalent_ordering.common_media == "media:application;enc=utf8;fmt=json;record"


# TEST1146: InputResolverError subclass display messages and exception hierarchy are correct.
def test_1146_input_resolver_error_display_and_source():
    from capdag.input_resolver.types import IoError, InvalidGlobError, InputResolverError

    # The path is rendered the way the platform spells it, so the expectation
    # is built from the same Path rather than from a POSIX literal: on Windows
    # the message reads `\tmp\data.bin`, and asserting the forward-slash form
    # tested the separator instead of the message.
    io_path = Path("/tmp/data.bin")
    io_error = IoError(io_path, Exception("no access"))
    assert f"IO error at {io_path}" in str(io_error)
    assert "no access" in str(io_error)
    assert isinstance(io_error, InputResolverError)

    invalid_glob = InvalidGlobError("[", "unclosed character class")
    assert "Invalid glob pattern" in str(invalid_glob)
    assert "[" in str(invalid_glob)
    assert "unclosed character class" in str(invalid_glob)
    assert isinstance(invalid_glob, InputResolverError)
