"""Parity tests for input_resolver path and OS filtering."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from capdag.input_resolver import (
    ContentStructure,
    EmptyInputError,
    InspectionFailedError,
    InputItem,
    InvalidGlobError,
    NotFoundError,
    detect_file,
    detect_file_confirmed,
    resolve_directory,
    resolve_file,
    resolve_glob,
    resolve_inputs_confirmed,
    resolve_items,
    resolve_paths,
    should_exclude,
    should_exclude_dir,
)
from capdag.input_resolver.adapters.registry import MediaAdapterRegistry
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


# TEST977: OS files excluded in resolve_paths
def test_977_os_files_excluded_integration(tmp_path: Path):
    (tmp_path / ".DS_Store").write_text("")
    (tmp_path / "real.txt").write_text("content")
    result = resolve_paths([str(tmp_path)])
    assert len(result.files) == 1
    assert "real.txt" in str(result.files[0].path)


# TEST1090: 1 file -> is_sequence=false
def test_1090_single_file_scalar(tmp_path: Path):
    (tmp_path / "only.txt").write_text("hello")
    result = resolve_paths([str(tmp_path / "only.txt")])
    assert len(result.files) == 1
    assert not result.is_sequence


# TEST1092: 2 files -> is_sequence=true
def test_1092_two_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.txt").write_text("b")
    result = resolve_paths([str(tmp_path / "a.txt"), str(tmp_path / "b.txt")])
    assert len(result.files) == 2
    assert result.is_sequence


# TEST1093: 1 dir with 1 file -> is_sequence=false
def test_1093_dir_single_file(tmp_path: Path):
    (tmp_path / "only.pdf").write_text("%PDF-1.4")
    result = resolve_paths([str(tmp_path)])
    assert len(result.files) == 1
    assert not result.is_sequence


# TEST1094: 1 dir with 3 files -> is_sequence=true
def test_1094_dir_multiple_files(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    (tmp_path / "c.txt").write_text("test")
    result = resolve_paths([str(tmp_path)])
    assert len(result.files) == 3
    assert result.is_sequence


# TEST1098: Extension-based detection picks up pdf tag for .pdf files
def test_1098_extension_based_pdf(tmp_path: Path):
    path = tmp_path / "doc.pdf"
    path.write_text("%PDF-1.4")
    resolved = detect_file(path)
    urn = MediaUrn.from_string(resolved.media_urn)
    assert urn.has_marker_tag("pdf")


# TEST1288: structure_from_marker_tags correctly maps tag combinations to ContentStructure
def test_1288_structure_from_marker_tags():
    assert detect_file  # keep import used; actual structure mapping is exercised indirectly
    scalar_opaque = MediaUrn.from_string("media:text")
    scalar_record = MediaUrn.from_string("media:text;record")
    list_opaque = MediaUrn.from_string("media:text;list")
    list_record = MediaUrn.from_string("media:text;list;record")
    from capdag.input_resolver import structure_from_marker_tags

    assert structure_from_marker_tags(scalar_opaque) == ContentStructure.SCALAR_OPAQUE
    assert structure_from_marker_tags(scalar_record) == ContentStructure.SCALAR_RECORD
    assert structure_from_marker_tags(list_opaque) == ContentStructure.LIST_OPAQUE
    assert structure_from_marker_tags(list_record) == ContentStructure.LIST_RECORD


def _create_test_media_registry(tmp_path: Path) -> FabricRegistry:
    return FabricRegistry.new_for_test(tmp_path / "media-cache")


class _MockInvoker:
    def __init__(self, response):
        self.response = response

    async def invoke_adapter_selection(self, cartridge_id: str, file_path: Path):
        return self.response


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
    assert registry.refine_media_urn("media:test;textable", "something-special") == "media:refined;test;textable"


# TEST1222: Base URNs without a registered adapter are returned unchanged.
def test_1222_refine_no_matching_adapter():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    assert registry.refine_media_urn("media:other;textable", "something-special") == "media:other;textable"


# TEST1223: Adapters that decline to refine leave the original media URN intact.
def test_1223_refine_adapter_returns_none():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    assert registry.refine_media_urn("media:test;textable", "ordinary-value") == "media:test;textable"


# TEST1224: When multiple adapter prefixes match, the longest prefix wins.
def test_1224_refine_longest_prefix_match():
    registry = ValueAdapterRegistry()
    registry.register("media:test", _SpecialAdapter())
    registry.register("media:test;specific", _SpecificAdapter())
    assert registry.refine_media_urn("media:test;specific;textable", "something-specific") == "media:result;specific;test;textable"


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
    assert adapter.refine("media:test;textable", "something-special") == "media:refined;test;textable"


# TEST1229: Value adapters return no refinement when the base media URN is outside their domain.
def test_1229_value_adapter_refine_no_match_base():
    adapter = _SpecialAdapter()
    assert adapter.refine("media:other;textable", "something-special") is None


# TEST1230: Value adapters return no refinement when the inspected value does not match.
def test_1230_value_adapter_refine_no_match_value():
    adapter = _SpecialAdapter()
    assert adapter.refine("media:test;textable", "ordinary-value") is None


# TEST1235: Plain text without model-spec syntax eliminates model-spec TXT candidates.
def test_1235_disc_1_plain_text_eliminates_model_specs(tmp_path: Path):
    registry = _create_test_media_registry(tmp_path)
    all_txt_urns = registry.media_urns_for_extension("txt")
    from capdag.input_resolver.resolver import discriminate_candidates_by_validation

    survivors = discriminate_candidates_by_validation(
        b"Hello world\nThis is a plain text file\nNo colons here",
        all_txt_urns,
        registry,
        "media:list;textable;txt",
    )
    for survivor in survivors:
        assert "model-spec" not in survivor


# TEST1236: Discrimination matches a candidate's validation pattern
# against the file content. media:model-spec is a value type with no
# associated file extension, so it does NOT appear among txt
# candidates. When passed in explicitly as a candidate, content that
# matches its `^(scheme):\S+$` regex must survive; content that
# doesn't (plain prose) must be filtered out.
def test_1236_disc_2_model_spec_validation_pattern_filters_content(tmp_path: Path):
    registry = _create_test_media_registry(tmp_path)
    from capdag.input_resolver.resolver import discriminate_candidates_by_validation

    candidates = ["media:model-spec;textable"]

    # Spec-shaped content survives the regex filter.
    survivors = discriminate_candidates_by_validation(
        b"hf:MaziyarPanahi/Mistral-7B-Instruct-v0.3-GGUF",
        candidates,
        registry,
        "media:textable",
    )
    assert "media:model-spec;textable" in survivors

    # Plain prose with internal whitespace is rejected by the same regex.
    survivors_prose = discriminate_candidates_by_validation(
        b"this is not a model spec",
        candidates,
        registry,
        "media:textable",
    )
    assert "media:model-spec;textable" not in survivors_prose


# TEST1237: Empty candidates -> empty result
def test_1237_disc_5_empty_candidates(tmp_path: Path):
    registry = _create_test_media_registry(tmp_path)
    from capdag.input_resolver.resolver import discriminate_candidates_by_validation

    assert discriminate_candidates_by_validation(b"anything", [], registry, "media:") == []


# TEST1238: Unknown URN survives discrimination
def test_1238_disc_6_unknown_urn_survives(tmp_path: Path):
    registry = _create_test_media_registry(tmp_path)
    from capdag.input_resolver.resolver import discriminate_candidates_by_validation

    candidates = ["media:nonexistent;fake"]
    assert discriminate_candidates_by_validation(b"anything", candidates, registry, "media:") == candidates


# TEST1276: Registration of a cap group with non-conflicting adapters succeeds
def test_1276_register_non_conflicting(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("text-formats", ["media:json", "media:yaml"], "txtcartridge")
    assert registry.has_adapter_for_extension("json")


# TEST1277: Registration of a cap group with an adapter that conforms_to an existing adapter is rejected
def test_1277_reject_conforming_overlap(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:json"], "cartridge-a")
    with pytest.raises(Exception) as exc_info:
        registry.register_cap_group("group-b", ["media:json;record;textable"], "cartridge-b")
    message = str(exc_info.value)
    assert "group-b" in message
    assert "group-a" in message


# TEST1278: Registration rejects the entire group - no partial registration
def test_1278_reject_entire_group(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:json"], "cartridge-a")
    with pytest.raises(Exception):
        registry.register_cap_group("group-b", ["media:yaml", "media:json;textable", "media:csv"], "cartridge-b")
    assert registry.find_adapters_for_extension("json") == [("cartridge-a", MediaUrn.from_string("media:json"))]


# TEST1279: Intra-group conflict (two adapters within same group overlap) is rejected
def test_1279_intra_group_conflict(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    with pytest.raises(Exception):
        registry.register_cap_group("group-a", ["media:json", "media:json;record;textable"], "cartridge-a")


# TEST1280: find_adapters_for_extension returns correct cartridge IDs
def test_1280_find_adapters_for_extension(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("group-a", ["media:json"], "cartridge-a")
    registry.register_cap_group("group-b", ["media:yaml"], "cartridge-b")
    matches = registry.find_adapters_for_extension("json")
    assert matches == [("cartridge-a", MediaUrn.from_string("media:json"))]


# TEST1281: has_adapter_for_extension returns false for unregistered extension
def test_1281_no_adapter_for_unknown(tmp_path: Path):
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    assert not registry.has_adapter_for_extension("unknown")


# TEST1285: detect_file_confirmed fails when no adapters are registered for the extension
@pytest.mark.asyncio
async def test_1285_confirmed_no_adapters_fails(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text('{"key":"value"}')
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    with pytest.raises(InspectionFailedError, match="No content-inspection adapter"):
        await detect_file_confirmed(path, registry, _MockInvoker(None))


# TEST1286: detect_file_confirmed succeeds when adapter returns URNs
@pytest.mark.asyncio
async def test_1286_confirmed_adapter_returns_urns(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text('{"key":"value"}')
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("test-group", ["media:json"], "test-cartridge")

    resolved = await detect_file_confirmed(
        path,
        registry,
        _MockInvoker(["media:json;record;textable"]),
    )
    assert "json" in resolved.media_urn
    assert resolved.content_structure == ContentStructure.SCALAR_RECORD


# TEST1287: detect_file_confirmed fails when all adapters return empty END (no match)
@pytest.mark.asyncio
async def test_1287_confirmed_all_adapters_no_match(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text("not json")
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("test-group", ["media:json"], "test-cartridge")

    with pytest.raises(InspectionFailedError, match="All registered adapters returned no match"):
        await detect_file_confirmed(path, registry, _MockInvoker(None))


@pytest.mark.asyncio
async def test_1139_resolve_inputs_confirmed_wraps_detect_file_confirmed(tmp_path: Path):
    path = tmp_path / "data.json"
    path.write_text('{"key":"value"}')
    registry = MediaAdapterRegistry(_create_test_media_registry(tmp_path))
    registry.register_cap_group("test-group", ["media:json"], "test-cartridge")

    resolved = await resolve_inputs_confirmed([InputItem.file(path)], registry, _MockInvoker(["media:json;record;textable"]))
    assert len(resolved.files) == 1
    assert resolved.files[0].media_urn == "media:json;record;textable"


# =============================================================================
# Tests ported from Rust input_resolver/types.rs (1143-1146)
# =============================================================================

# TEST1143: InputItem.from_string distinguishes glob pattern, existing directory, and non-directory path.
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


# TEST1144: ContentStructure is_list/is_record helpers and string values are correct.
def test_1144_content_structure_helpers_and_display():
    assert not ContentStructure.is_list(ContentStructure.SCALAR_OPAQUE)
    assert not ContentStructure.is_record(ContentStructure.SCALAR_OPAQUE)
    assert ContentStructure.SCALAR_OPAQUE == "scalar/opaque"

    assert ContentStructure.is_list(ContentStructure.LIST_RECORD)
    assert ContentStructure.is_record(ContentStructure.LIST_RECORD)
    assert ContentStructure.LIST_RECORD == "list/record"


# TEST1145: ResolvedInputSet.new uses URN equivalence for common_media and file count for is_sequence.
def test_1145_resolved_input_set_uses_equivalent_media_and_file_count_cardinality():
    from capdag.input_resolver.types import ResolvedFile, ResolvedInputSet

    single_list_file = ResolvedInputSet.new([ResolvedFile(
        path=Path("/tmp/items.json"),
        media_urn="media:application;json;list;record",
        size_bytes=42,
        content_structure=ContentStructure.LIST_RECORD,
    )])
    assert not single_list_file.is_sequence
    assert single_list_file.is_homogeneous()
    assert single_list_file.common_media == "media:application;json;list;record"

    # Two files with tag-equivalent URNs (different tag order) → homogeneous, is_sequence
    equivalent_ordering = ResolvedInputSet.new([
        ResolvedFile(
            path=Path("/tmp/a.json"),
            media_urn="media:application;json;record;textable",
            size_bytes=10,
            content_structure=ContentStructure.SCALAR_RECORD,
        ),
        ResolvedFile(
            path=Path("/tmp/b.json"),
            media_urn="media:application;record;textable;json",
            size_bytes=11,
            content_structure=ContentStructure.SCALAR_RECORD,
        ),
    ])
    assert equivalent_ordering.is_sequence
    assert equivalent_ordering.is_homogeneous()
    assert equivalent_ordering.common_media == "media:application;json;record;textable"


# TEST1146: InputResolverError subclass display messages and exception hierarchy are correct.
def test_1146_input_resolver_error_display_and_source():
    from capdag.input_resolver.types import IoError, InvalidGlobError, InputResolverError

    io_error = IoError(Path("/tmp/data.bin"), Exception("no access"))
    assert "IO error at /tmp/data.bin" in str(io_error)
    assert "no access" in str(io_error)
    assert isinstance(io_error, InputResolverError)

    invalid_glob = InvalidGlobError("[", "unclosed character class")
    assert "Invalid glob pattern" in str(invalid_glob)
    assert "[" in str(invalid_glob)
    assert "unclosed character class" in str(invalid_glob)
    assert isinstance(invalid_glob, InputResolverError)
