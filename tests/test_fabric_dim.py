"""Fabric dim tests — mirror the Rust reference (capdag) test-for-test.

Shared test numbers (1966-1968, 1971-1972) test the same behavior, with the
same method, across every capdag implementation. See capdag/src/fabric/dim.rs
and the `dim_tests` module of capdag/src/fabric/registry.rs. TEST1969 lives
with the cap definition tests (test_cap.py), TEST1970 with the media def
tests (test_media_def.py).
"""

import hashlib
import json
from pathlib import Path

import httpx
import pytest

from capdag.cap.definition import Cap, CapOutput
from capdag.fabric.dim import DimRef, DimTag, StoredDim, StoredDimValue
from capdag.fabric.registry import (
    CacheEntry,
    DimCacheEntry,
    FabricRegistry,
    Manifest,
    MediaCacheEntry,
    NotFoundError,
    ParseError,
    RegistryConfig,
    StoredMediaDef,
    ValidationError,
    _dim_url_and_cache_path,
    _media_url_and_cache_path,
    _retain_pinned,
    checked_dim,
    normalize_cap_urn,
    normalize_media_urn,
)
from capdag.urn.cap_urn import CapUrn


# --- helpers (mirror the Rust test fixtures) -------------------------------


def _dim(name: str, version: int, values) -> StoredDim:
    return StoredDim(
        name=name,
        version=version,
        title=f"Title of {name}",
        documentation=f"## {name}\nWhat {name} is.",
        values=[
            StoredDimValue(
                name=v,
                title=v.upper(),
                tags=[DimTag(name, v)],
                documentation=f"The {v} value.",
            )
            for v in values
        ],
    )


def _cap_with_dims(urn: str, dims) -> Cap:
    cap = Cap(CapUrn.from_string(urn), "t", ["t"])
    cap.version = 1
    cap.dims = [DimRef(d, v) for d, v in dims]
    return cap


def _spec_with_dims(urn: str, dims) -> StoredMediaDef:
    return StoredMediaDef(
        urn=urn,
        media_type="text/plain",
        title="t",
        version=1,
        dims=[DimRef(d, v) for d, v in dims],
    )


# --- TEST1966: manifest dims map --------------------------------------------


# TEST1966: the Manifest type round-trips a `dims` map (name -> defver), and a manifest without one is refused: every manifest this library reads names the dims of its snapshot.
def test_1966_manifest_carries_a_dims_map_and_requires_it():
    data = json.loads(
        '{"version":11,"previous":10,"caps":{},"media":{},"aliases":{},'
        '"dims":{"language":1,"file-type":2}}'
    )
    m = Manifest.from_dict(data)
    assert m.dims.get("language") == 1
    assert m.dims.get("file-type") == 2
    back = json.loads(json.dumps(m.to_dict()))
    assert back["dims"]["file-type"] == 2

    without = json.loads('{"version":11,"previous":10,"caps":{},"media":{},"aliases":{}}')
    with pytest.raises(ValueError, match="dims"):
        Manifest.from_dict(without)


# --- TEST1967: get_dim -------------------------------------------------------


# TEST1967: get_dim returns a dim the registry holds; a name the pinned manifest does not list is NotFound naming the manifest version, decided before any fetch (the registry is offline, and the error is not the offline one); a string that is no dim name is refused as such.
@pytest.mark.asyncio
async def test_1967_get_dim_resolves_through_the_manifest(tmp_path):
    registry = FabricRegistry.new_for_test(tmp_path)
    registry.insert_cached_dim_for_test(_dim("language", 1, ["en", "es"]))
    got = await registry.get_dim("language")
    assert got.value("es") is not None
    assert got.value("es").title == "ES"
    assert registry.dim_defver_for("language") == 1

    registry.set_offline(True)
    with pytest.raises(NotFoundError) as exc_info:
        await registry.get_dim("tone")
    assert "dim 'tone' is not part of manifest v1" in str(exc_info.value)
    with pytest.raises(ValidationError):
        await registry.get_dim("Tone")


# --- TEST1968: dim object addressing and checking ---------------------------


# TEST1968: a dim is addressed at dims/<sha256-of-name>/<defver>.json, on the registry and in the cache; a body served for it must be that dim at that version, with no field this library does not know, and must hold (values present, names unique).
def test_1968_a_dim_object_is_the_dim_and_version_asked_for():
    config = RegistryConfig().with_registry_url("https://fabric.example.test")
    cache = Path("/tmp/capdag-test-cache-1968")
    digest = hashlib.sha256("language".encode("utf-8")).hexdigest()
    url, path = _dim_url_and_cache_path(cache, config, "language", 3)
    assert url == f"https://fabric.example.test/dims/{digest}/3.json"
    assert path == cache / "dims" / digest / "3.json"

    good = json.dumps(_dim("language", 3, ["en"]).to_dict()).encode("utf-8")
    assert checked_dim(good, "language", 3).name == "language"
    with pytest.raises(ParseError, match="does not match requested name"):
        checked_dim(good, "file-type", 3)
    with pytest.raises(ParseError, match="manifest pins defver 2"):
        checked_dim(good, "language", 2)

    extra = json.loads(good)
    extra["predicates"] = []
    with pytest.raises(ParseError, match="predicates"):
        checked_dim(json.dumps(extra).encode("utf-8"), "language", 3)
    twice = json.dumps(_dim("language", 3, ["en", "en"]).to_dict()).encode("utf-8")
    with pytest.raises(ValidationError, match="declares value 'en' more than once"):
        checked_dim(twice, "language", 3)
    none = json.dumps(_dim("language", 3, []).to_dict()).encode("utf-8")
    with pytest.raises(ValidationError):
        checked_dim(none, "language", 3)


# --- TEST1971: disk-cache hydration ------------------------------------------


# TEST1971: what is loaded from the disk cache is kept only as the pinned manifest names it — a dim at another version is dropped — and a definition is kept only when every dim it names survives with the value it names. At v0 there are no dims. The second half drives the same through the registry's own construction from a disk cache.
@pytest.mark.asyncio
async def test_1971_the_disk_cache_keeps_definitions_only_with_their_pinned_dims(
    tmp_path, monkeypatch
):
    manifest = Manifest.empty(11)
    manifest.dims["language"] = 2
    manifest.dims["medium"] = 1
    caps_urns = [
        "cap:a;in=media:;out=media:",
        "cap:b;in=media:;out=media:",
        "cap:c;in=media:;out=media:",
    ]
    for u in caps_urns:
        manifest.caps[normalize_cap_urn(u)] = 1
    manifest.media["media:x"] = 1
    manifest.media["media:y"] = 1

    caps = {
        normalize_cap_urn(caps_urns[0]): _cap_with_dims(caps_urns[0], [("medium", "text")]),
        normalize_cap_urn(caps_urns[1]): _cap_with_dims(caps_urns[1], [("language", "en")]),
        normalize_cap_urn(caps_urns[2]): _cap_with_dims(caps_urns[2], []),
    }
    specs = {
        "media:x": _spec_with_dims("media:x", [("medium", "text")]),
        "media:y": _spec_with_dims("media:y", [("medium", "audio")]),
    }
    aliases = {}
    dims = {
        "language": _dim("language", 1, ["en"]),  # the manifest pins 2
        "medium": _dim("medium", 1, ["text"]),
    }

    _retain_pinned(manifest, 11, caps, specs, aliases, dims)
    assert list(dims.keys()) == ["medium"], "a dim at another version is dropped"
    assert sorted(c.urn_string() for c in caps.values()) == sorted(
        [normalize_cap_urn(caps_urns[0]), normalize_cap_urn(caps_urns[2])]
    ), "the cap naming the dropped dim is dropped with it"
    assert list(specs.keys()) == ["media:x"], "a value the dim lacks drops the definition"

    v0_dims = {"medium": _dim("medium", 1, ["text"])}
    _retain_pinned(Manifest.empty(0), 0, {}, {}, {}, v0_dims)
    assert v0_dims == {}, "v0 has no dims"

    # The registry's construction from a disk cache applies the same rule.
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    config = RegistryConfig().with_registry_url("https://fabric.example.test")
    cache_dir = FabricRegistry._get_cache_dir(config.registry_base_url)

    def record_cap(op: str, cap_dims) -> Cap:
        cap = Cap(CapUrn.from_string(f'cap:in="media:void";{op};out="media:record"'), op, [op])
        cap.version = 1
        cap.add_output(CapOutput("media:record", "record", "The record"))
        cap.dims = [DimRef(d, v) for d, v in cap_dims]
        return cap

    kept_cap = record_cap("kept", [("medium", "text")])
    stale_cap = record_cap("stale", [("language", "en")])
    disk_manifest = Manifest.empty(11)
    disk_manifest.dims["language"] = 2
    disk_manifest.dims["medium"] = 1
    for cap in (kept_cap, stale_cap):
        urn = normalize_cap_urn(cap.urn_string())
        disk_manifest.caps[urn] = 1
        cap_file = cache_dir / "caps" / hashlib.sha256(urn.encode()).hexdigest() / "1.json"
        cap_file.parent.mkdir(parents=True, exist_ok=True)
        cap_file.write_text(json.dumps(CacheEntry(cap, 0, 0).to_dict()))
    for spec in (
        _spec_with_dims("media:x", [("medium", "text")]),
        _spec_with_dims("media:y", [("medium", "audio")]),
    ):
        disk_manifest.media[spec.urn] = 1
        _, spec_file = _media_url_and_cache_path(cache_dir, config, spec.urn, 1)
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text(json.dumps(MediaCacheEntry(spec, 0, 0).to_dict()))
    for d in (_dim("language", 1, ["en"]), _dim("medium", 1, ["text"])):
        _, dim_file = _dim_url_and_cache_path(cache_dir, config, d.name, d.version)
        dim_file.parent.mkdir(parents=True, exist_ok=True)
        dim_file.write_text(json.dumps(DimCacheEntry(d, 0, 0).to_dict()))
    (cache_dir / "manifests").mkdir(parents=True, exist_ok=True)
    (cache_dir / "manifests" / "11.json").write_text(json.dumps(disk_manifest.to_dict()))

    registry = await FabricRegistry.with_config_and_manifest_version(config, 11)
    assert registry.get_cached_dim("medium") is not None
    assert registry.get_cached_dim("language") is None, "a dim at another version is dropped"
    assert registry.get_cached_cap(kept_cap.urn_string()) is not None
    assert registry.get_cached_cap(stale_cap.urn_string()) is None, (
        "the cap naming the dropped dim is dropped with it"
    )
    assert registry.get_cached_media_def("media:x") is not None
    assert registry.get_cached_media_def("media:y") is None, (
        "a value the dim lacks drops the definition"
    )


# --- TEST1972: a definition needs every dim it names ------------------------


# TEST1972: a definition is cached only once every dim it names is held, with the value it names. A dim the manifest does not list is refused naming the definition, the dim and the manifest version, before any fetch; a value the dim does not declare is refused naming all three; one dim named twice is refused. The second half fetches caps and media defs from a served registry and checks what lands in the cache.
@pytest.mark.asyncio
async def test_1972_a_definition_needs_every_dim_it_names(tmp_path):
    registry = FabricRegistry.new_for_test(tmp_path / "probe")
    registry.insert_cached_dim_for_test(_dim("language", 1, ["en"]))
    registry.set_offline(True)
    await registry._ensure_dims_cached("cap 'cap:probe'", [DimRef("language", "en")])

    with pytest.raises(ValidationError) as exc_info:
        await registry._ensure_dims_cached("cap 'cap:probe'", [DimRef("language", "fr")])
    assert str(exc_info.value) == (
        "cap 'cap:probe' names value 'fr' of dim 'language', which the dim does not declare"
    )
    with pytest.raises(NotFoundError) as exc_info:
        await registry._ensure_dims_cached("cap 'cap:probe'", [DimRef("tone", "formal")])
    assert str(exc_info.value) == "cap 'cap:probe' names dim 'tone', which is not in manifest v1"
    with pytest.raises(ValidationError, match="named more than once"):
        await registry._ensure_dims_cached(
            "cap 'cap:probe'", [DimRef("language", "en"), DimRef("language", "en")]
        )

    # Through the fetch paths: a served registry holding the dim `language`
    # with the one value `en`.
    base = "https://fabric.example.test"
    config = RegistryConfig().with_registry_url(base)
    served = {}

    def serve(url: str, body: dict) -> None:
        served[url] = json.dumps(body).encode("utf-8")

    def cap_body(op: str, value: str) -> dict:
        return {
            "urn": f'cap:in="media:void";{op};out="media:record"',
            "version": 1,
            "title": op,
            "aliases": [op],
            "dims": [{"dim": "language", "value": value}],
            "outputs": [
                {"media_urn": "media:record", "name": "record", "output_description": "The record"}
            ],
        }

    cache_dir = tmp_path / "served"
    registry = FabricRegistry(cache_dir, config, None, 1, Manifest.empty(1))
    for op, value in (("speaks", "en"), ("mumbles", "fr")):
        urn = normalize_cap_urn(cap_body(op, value)["urn"])
        registry.manifest.caps[urn] = 1
        serve(f"{base}/caps/{hashlib.sha256(urn.encode()).hexdigest()}/1.json", cap_body(op, value))
    for urn, spec_dims in (
        ("media:void", []),
        ("media:record", []),
        ("media:enc=utf-8;spoken", [{"dim": "tone", "value": "formal"}]),
    ):
        normalized = normalize_media_urn(urn)
        registry.manifest.media[normalized] = 1
        body = {"urn": normalized, "version": 1, "media_type": "text/plain", "title": urn}
        if spec_dims:
            body["dims"] = spec_dims
        serve(_media_url_and_cache_path(cache_dir, config, normalized, 1)[0], body)
    registry.manifest.dims["language"] = 1
    serve(_dim_url_and_cache_path(cache_dir, config, "language", 1)[0], _dim("language", 1, ["en"]).to_dict())

    def handler(request: httpx.Request) -> httpx.Response:
        body = served.get(str(request.url))
        if body is None:
            return httpx.Response(404)
        return httpx.Response(200, content=body)

    registry.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    speaks = cap_body("speaks", "en")["urn"]
    assert registry.get_cached_dim("language") is None
    cap = await registry.get_cap(speaks)
    assert cap.dims == [DimRef("language", "en")]
    assert registry.get_cached_dim("language") is not None, "the dim is cached with the cap"
    assert registry.get_cached_cap(speaks) is not None
    assert _dim_url_and_cache_path(cache_dir, config, "language", 1)[1].is_file()

    mumbles = cap_body("mumbles", "fr")["urn"]
    with pytest.raises(ValidationError) as exc_info:
        await registry.get_cap(mumbles)
    assert str(exc_info.value) == (
        f"cap '{normalize_cap_urn(mumbles)}' names value 'fr' of dim 'language', "
        f"which the dim does not declare"
    )
    assert registry.get_cached_cap(mumbles) is None, "a cap whose dim lacks its value is not cached"

    spoken = "media:enc=utf-8;spoken"
    with pytest.raises(NotFoundError) as exc_info:
        await registry.get_media_def(spoken)
    assert str(exc_info.value) == (
        f"media def '{normalize_media_urn(spoken)}' names dim 'tone', which is not in manifest v1"
    )
    assert registry.get_cached_media_def(spoken) is None, (
        "a media def naming a dim the manifest lacks is not cached"
    )
    assert not _media_url_and_cache_path(cache_dir, config, normalize_media_urn(spoken), 1)[1].exists()
