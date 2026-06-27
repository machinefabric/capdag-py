"""Fabric alias tests — mirror the Rust reference (capdag) test-for-test.

Shared test numbers (1880-1892) test the same behavior, with the same method,
across every capdag implementation. See capdag/src/fabric/alias.rs,
capdag/src/fabric/registry.rs, and capdag/src/machine/parser.rs.
"""

import json

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.urn.cap_urn import CapUrn
from capdag.fabric.registry import (
    ALIAS_TARGET_CAP,
    ALIAS_TARGET_MEDIA,
    FabricRegistry,
    Manifest,
    StoredAlias,
    StoredMediaDef,
    ValidationError,
    NotFoundError,
    classify_alias_target,
    is_alias_token,
    normalize_alias_name,
    token_is_urn,
)
from capdag.machine.parser import parse_machine
from capdag.machine.error import (
    MachineParseError,
    UndefinedAliasError,
    AliasNotACapError,
)


# --- helpers (mirror the Rust test fixtures) -------------------------------


def _build_cap(cap_urn_str: str, title: str, arg_urns, out_urn: str) -> Cap:
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, title, title.lower(), f"{title} cap")
    for u in arg_urns:
        cap.add_arg(CapArg(media_urn=u, required=True, sources=[StdinSource(u)]))
    cap.set_output(CapOutput(out_urn, f"{title} output"))
    return cap


# --- TEST1880-1882: pure helpers -------------------------------------------


# TEST1880: alias name normalization lowercases and accepts the allowed char
# class; rejects colon, whitespace, and out-of-class chars.
def test_1880_alias_name_normalization_rules():
    assert normalize_alias_name("JSONDoc") == "jsondoc"
    assert normalize_alias_name("pdf2text") == "pdf2text"
    assert normalize_alias_name("my.alias-1_x") == "my.alias-1_x"

    with pytest.raises(ValueError):
        normalize_alias_name("")
    with pytest.raises(ValueError):
        normalize_alias_name("pdf:text")
    with pytest.raises(ValueError):
        normalize_alias_name("my alias")
    with pytest.raises(ValueError):
        normalize_alias_name("a/b")


# TEST1881: URN-vs-alias detection keys purely on the presence of ':'.
def test_1881_token_urn_vs_alias_detection():
    assert token_is_urn('cap:in="media:ext=pdf";extract;out="media:enc=utf-8"')
    assert token_is_urn("media:fmt=json;record")
    assert not token_is_urn("pdf2text")
    assert is_alias_token("pdf2text")
    assert not is_alias_token("media:enc=utf-8")


# TEST1882: alias target classification distinguishes cap from media by prefix
# and rejects a non-URN target.
def test_1882_classify_alias_target_by_prefix():
    assert classify_alias_target("media:fmt=json;record") == ALIAS_TARGET_MEDIA
    assert (
        classify_alias_target(
            'cap:effect=patch;in="media:image";name;out="media:ext=png;image"'
        )
        == ALIAS_TARGET_CAP
    )
    assert classify_alias_target("not-a-urn") is None


# --- TEST1887: manifest serde round-trip -----------------------------------


# TEST1887: the Manifest type round-trips an `aliases` map.
def test_1887_manifest_serde_round_trips_aliases():
    data = json.loads(
        '{"version":1,"previous":0,"caps":{},"media":{},'
        '"aliases":{"pdf2text":3,"jsondoc":1}}'
    )
    m = Manifest.from_dict(data)
    assert m.aliases.get("pdf2text") == 3
    assert m.aliases.get("jsondoc") == 1
    back = m.to_dict()
    assert back["aliases"]["pdf2text"] == 3
    assert back["aliases"]["jsondoc"] == 1


# --- TEST1888-1892: registry alias resolution ------------------------------


# TEST1888: resolve_alias returns the alias target untyped; case-insensitive;
# malformed name rejected.
@pytest.mark.asyncio
async def test_1888_resolve_alias_returns_target():
    registry = FabricRegistry.new_for_test()
    registry.insert_cached_alias_for_test(
        StoredAlias("jsondoc", "media:fmt=json;record", 1)
    )
    assert await registry.resolve_alias("jsondoc") == "media:fmt=json;record"
    assert await registry.resolve_alias("JSONDoc") == "media:fmt=json;record"
    with pytest.raises(ValidationError):
        await registry.resolve_alias("bad:name")


# TEST1889: resolve_alias_typed enforces the expected kind.
@pytest.mark.asyncio
async def test_1889_resolve_alias_typed_enforces_kind():
    registry = FabricRegistry.new_for_test()
    registry.insert_cached_alias_for_test(
        StoredAlias("jsondoc", "media:fmt=json;record", 1)
    )
    assert (
        await registry.resolve_alias_typed("jsondoc", ALIAS_TARGET_MEDIA)
        == "media:fmt=json;record"
    )
    assert await registry.resolve_alias_typed("jsondoc", None) == "media:fmt=json;record"
    with pytest.raises(ValidationError):
        await registry.resolve_alias_typed("jsondoc", ALIAS_TARGET_CAP)


# TEST1890: get_cap accepts a cap alias and returns the aliased cap; a media
# alias passed to get_cap fails hard (typed boundary).
@pytest.mark.asyncio
async def test_1890_get_cap_via_alias_and_type_mismatch():
    registry = FabricRegistry.new_for_test()
    cap = _build_cap(
        'cap:extract;in="media:ext=pdf";out="media:enc=utf-8"',
        "extract",
        ["media:ext=pdf"],
        "media:enc=utf-8",
    )
    canonical = cap.urn_string()
    registry.add_caps_to_cache([cap])
    registry.insert_cached_alias_for_test(StoredAlias("pdf2text", canonical, 1))

    got = await registry.get_cap("pdf2text")
    assert got.urn_string() == canonical

    registry.insert_cached_alias_for_test(
        StoredAlias("jsondoc", "media:fmt=json;record", 1)
    )
    with pytest.raises(ValidationError):
        await registry.get_cap("jsondoc")


# TEST1891: get_media_def accepts a media alias and returns the aliased spec;
# a cap alias passed to get_media_def fails hard.
@pytest.mark.asyncio
async def test_1891_get_media_def_via_alias_and_type_mismatch():
    registry = FabricRegistry.new_for_test()
    registry.add_spec(
        StoredMediaDef(urn="media:fmt=json;record", media_type="application/json", title="JSON")
    )
    registry.insert_cached_alias_for_test(
        StoredAlias("jsondoc", "media:fmt=json;record", 1)
    )
    spec = await registry.get_media_def("jsondoc")
    assert spec.urn == "media:fmt=json;record"

    cap = _build_cap(
        'cap:extract;in="media:ext=pdf";out="media:enc=utf-8"',
        "extract",
        ["media:ext=pdf"],
        "media:enc=utf-8",
    )
    canonical = cap.urn_string()
    registry.add_caps_to_cache([cap])
    registry.insert_cached_alias_for_test(StoredAlias("pdf2text", canonical, 1))
    with pytest.raises(ValidationError):
        await registry.get_media_def("pdf2text")


# TEST1892: an unknown alias name is a hard NotFound, never a silent empty.
@pytest.mark.asyncio
async def test_1892_unknown_alias_is_not_found():
    registry = FabricRegistry.new_for_test()
    with pytest.raises(NotFoundError):
        await registry.get_alias("nosuchalias")
    with pytest.raises(NotFoundError):
        registry.alias_defver_for("nosuchalias")
    assert registry.resolve_alias_cached("nosuchalias") is None
    assert registry.resolve_alias_cached("bad:name") is None


# --- TEST1883-1886: machine notation cap aliases ---------------------------


def _extract_with_alias_registry():
    extract_urn = 'cap:extract;in="media:ext=pdf";out="media:enc=utf-8;ext=txt"'
    cap = _build_cap(extract_urn, "extract", ["media:ext=pdf"], "media:enc=utf-8;ext=txt")
    canonical = cap.urn_string()
    registry = FabricRegistry.new_for_test()
    registry.add_caps_to_cache([cap])
    registry.insert_cached_alias_for_test(StoredAlias("pdf2text", canonical, 1))
    return registry, canonical


# TEST1883: a cap-position name with no local header resolves as a cap alias.
def test_1883_cap_position_alias_resolves_to_cap():
    registry, canonical = _extract_with_alias_registry()
    machine = parse_machine("[doc -> pdf2text -> txt]", registry)
    assert machine.strand_count() == 1
    strand = machine.strands()[0]
    assert len(strand.edges()) == 1
    assert str(strand.edges()[0].cap_urn) == canonical


# TEST1884: a local header alias shadows a fabric alias of the same name.
def test_1884_local_header_shadows_cap_alias():
    registry, _ = _extract_with_alias_registry()
    other_urn = 'cap:other;in="media:ext=pdf";out="media:enc=utf-8;ext=txt"'
    other = _build_cap(other_urn, "other", ["media:ext=pdf"], "media:enc=utf-8;ext=txt")
    other_canonical = other.urn_string()
    registry.add_caps_to_cache([other])
    notation = f"[pdf2text {other_urn}]\n[doc -> pdf2text -> txt]"
    machine = parse_machine(notation, registry)
    assert str(machine.strands()[0].edges()[0].cap_urn) == other_canonical


# TEST1885: a cap-position alias that resolves to a MEDIA URN is a hard error.
def test_1885_cap_position_alias_to_media_is_error():
    cap = _build_cap(
        'cap:extract;in="media:ext=pdf";out="media:enc=utf-8;ext=txt"',
        "extract",
        ["media:ext=pdf"],
        "media:enc=utf-8;ext=txt",
    )
    registry = FabricRegistry.new_for_test()
    registry.add_caps_to_cache([cap])
    registry.insert_cached_alias_for_test(
        StoredAlias("jsondoc", "media:fmt=json;record", 1)
    )
    # parse_machine wraps syntax errors in MachineParseError; the cause is the
    # specific AliasNotACapError.
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine("[doc -> jsondoc -> out]", registry)
    assert isinstance(exc_info.value.cause, AliasNotACapError)


# TEST1886: a cap-position name that is neither a local header nor a registered
# alias raises UndefinedAlias.
def test_1886_unregistered_cap_name_is_undefined_alias():
    registry, _ = _extract_with_alias_registry()
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine("[doc -> nosuchalias -> out]", registry)
    assert isinstance(exc_info.value.cause, UndefinedAliasError)
