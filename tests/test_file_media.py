"""The file media types a file's extension names, from the whole manifest,
and what a file is.

A stub registry on a local socket serves, at its ``definition`` location,
every media definition of fabric manifest 13 that carries the ``ext=``
file-type tag, and the JSON records that list an extension without one, as
published (``fixtures/fabric13_file_media.json``). The registry's manifest
names them all; what its cache holds is up to each test.

Tests use # TEST###: comments matching the Rust implementation for
cross-tracking.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pytest

from capdag.fabric.cache import key_hash
from capdag.fabric.registry import (
    FabricRegistry,
    FileTypesError,
    RegistryConfig,
    StoredMediaDef,
)
from capdag.input_resolver import (
    InputResolverError,
    MediaAdapterRegistry,
    NoAdapters,
    NoExtensionError,
    NoInvoker,
    UnknownExtensionError,
    ValueAdapterRegistry,
    detect_file_media,
    extension_media,
    primary_media,
)
from capdag.urn.media_urn import MediaUrn
from tests.stub_registry import Answer, StubRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "fabric13_file_media.json"
MANIFEST_VERSION = 13


def published() -> Dict[str, dict]:
    """The fixture's definitions as published, by URN."""
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["definitions"]


def definitions() -> Dict[str, StoredMediaDef]:
    return {urn: StoredMediaDef.from_dict(body) for urn, body in sorted(published().items())}


def is_file_type(urn: str) -> bool:
    return MediaUrn.from_string(urn).get_tag("ext") is not None


class FixtureRegistry:
    """The fixture registry: serves ``/media/<sha256 of URN>/<defver>.json``
    for every definition, 404 for anything else, and counts what it served."""

    def __init__(self) -> None:
        self._bodies = {
            f"/media/{key_hash(urn)}/{body['version']}.json": json.dumps(body).encode("utf-8")
            for urn, body in published().items()
        }
        self._stub = StubRegistry(self._answer)

    def _answer(self, path: str) -> Answer:
        body = self._bodies.get(path)
        return Answer(body=body) if body is not None else Answer(status=404)

    @property
    def anchor(self) -> str:
        return self._stub.anchor

    def served(self) -> int:
        """How many definitions were served."""
        return sum(self._stub.requests[path] for path in self._bodies)

    async def __aenter__(self) -> "FixtureRegistry":
        await self._stub.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        await self._stub.__aexit__(*exc)


def registry(anchor: str, cached: Sequence[str]) -> FabricRegistry:
    """A registry pinned at manifest 13 whose manifest names every fixture
    definition, fetching from ``anchor``; the definitions in ``cached`` are
    in its cache already."""
    reg = FabricRegistry.new_for_test_with_config_and_version(
        RegistryConfig().with_anchor(anchor), MANIFEST_VERSION
    )
    for urn, d in definitions().items():
        if urn in cached:
            reg.add_spec(d)
        else:
            reg.list_media_in_manifest_for_test(urn, d.version)
    return reg


async def urns(reg: FabricRegistry, extension: str) -> List[str]:
    return [d.urn for d in await reg.file_media_for_extension(extension)]


# TEST7177: on a cold cache, a file's extension names every file media type
# the manifest declares for it, fetched from the registry: .csv and .yaml are
# known although nothing has cached them, and the content-only JSON records a
# machine has cached (a model download result) are no file types
@pytest.mark.asyncio
async def test_7177_extensions_name_the_manifests_file_types_on_a_cold_cache():
    async with FixtureRegistry() as fixture:
        reg = registry(fixture.anchor, ["media:download-result;enc=utf8;fmt=json;record"])

        assert await urns(reg, "csv") == ["media:enc=utf8;ext=csv;fmt=csv;list;record"]
        yaml = [
            "media:enc=utf8;ext=yaml;fmt=yaml",
            "media:enc=utf8;ext=yaml;fmt=yaml;list",
            "media:enc=utf8;ext=yaml;fmt=yaml;list;record",
            "media:enc=utf8;ext=yaml;fmt=yaml;record",
        ]
        assert await urns(reg, "yaml") == yaml
        assert await urns(reg, "YML") == yaml
        assert await urns(reg, "json") == [
            "media:enc=utf8;ext=json;fmt=json",
            "media:enc=utf8;ext=json;fmt=json;list",
            "media:enc=utf8;ext=json;fmt=json;list;record",
            "media:enc=utf8;ext=json;fmt=json;record",
        ]
        assert await urns(reg, "txt") == [
            "media:digitized;enc=utf8;ext=txt;plain-text",
            "media:enc=utf8;ext=requirements",
            "media:enc=utf8;ext=txt;image-description;plain-text",
            "media:enc=utf8;ext=txt;page;plain-text",
            "media:enc=utf8;ext=txt;plain-text",
        ]

        file_types = sum(1 for urn in definitions() if is_file_type(urn))
        assert file_types == 156, "manifest 13 has 156 file media types"
        assert fixture.served() == file_types, "every file media type is fetched once, and nothing else"


# TEST7178: the file media types load only when a file's type is first asked,
# once: making the registry and reading other definitions fetches none of
# them, and a second question fetches nothing more
@pytest.mark.asyncio
async def test_7178_file_media_types_load_lazily_and_once():
    async with FixtureRegistry() as fixture:
        reg = registry(fixture.anchor, [])

        await reg.get_media_def("media:enc=utf8;fmt=json;model-list;record")
        assert fixture.served() == 1, "only the definition asked for is fetched"

        await urns(reg, "pdf")
        after_first = fixture.served()
        assert after_first == 1 + 156
        await urns(reg, "csv")
        await urns(reg, "md")
        assert fixture.served() == after_first, "the index is loaded once"


# TEST7179: file media types already cached are not fetched again
@pytest.mark.asyncio
async def test_7179_cached_file_media_types_are_not_fetched():
    async with FixtureRegistry() as fixture:
        reg = registry(fixture.anchor, list(definitions()))
        assert await urns(reg, "csv") == ["media:enc=utf8;ext=csv;fmt=csv;list;record"]
        assert fixture.served() == 0


# TEST7180: offline with a cold cache, a file's type cannot be told: the
# question fails, naming every file media type it could not load and why, and
# never answers from the part of the fabric that is cached
@pytest.mark.asyncio
async def test_7180_offline_on_a_cold_cache_fails_naming_what_it_could_not_load():
    async with FixtureRegistry() as fixture:
        reg = registry(fixture.anchor, ["media:enc=utf8;ext=txt;plain-text", "media:document;ext=pdf"])
        reg.set_offline(True)

        with pytest.raises(FileTypesError) as exc_info:
            await reg.file_media_for_extension("txt")
        message = str(exc_info.value)
        assert message.startswith(
            "154 of the 156 file media types of manifest v13 could not be loaded"
        ), message
        assert "media:enc=utf8;ext=csv;fmt=csv;list;record: Network access blocked" in message, message
        assert "media:enc=utf8;ext=txt;plain-text:" not in message, (
            f"a cached type is not reported: {message}"
        )
        assert fixture.served() == 0

        reg.set_offline(False)
        assert await urns(reg, "csv") == ["media:enc=utf8;ext=csv;fmt=csv;list;record"]


# ---------------------------------------------------------------------------
# What a file is
# ---------------------------------------------------------------------------


def write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_bytes(content.encode("utf-8"))
    return path


def warm_machine_registry(anchor: str) -> FabricRegistry:
    """A registry over the fixture whose cache holds what a machine that has
    run a model download and an OCR cap holds."""
    return registry(
        anchor,
        [
            "media:download-result;enc=utf8;fmt=json;record",
            "media:digitized;enc=utf8;ext=txt;plain-text",
        ],
    )


#: One file of each common kind, its content, and the media a host with no
#: cartridge to ask takes it as.
NO_ADAPTER_TABLE = [
    ("notes.txt", "A line of text.\n", "media:enc=utf8;ext=txt;plain-text"),
    ("people.csv", "name,age\nann,30\n", "media:enc=utf8;ext=csv;fmt=csv;list;record"),
    ("rows.tsv", "name\tage\nann\t30\n", "media:enc=utf8;ext=tsv;fmt=tsv;list;record"),
    ("config.yaml", "name: ann\nage: 30\n", "media:enc=utf8;ext=yaml;fmt=yaml"),
    ("config.yml", "name: ann\n", "media:enc=utf8;ext=yaml;fmt=yaml"),
    ("a.json", '{"name": "ann"}', "media:enc=utf8;ext=json;fmt=json"),
    ("events.ndjson", '{"a":1}\n{"a":2}\n', "media:enc=utf8;ext=ndjson;fmt=ndjson"),
    ("events.jsonl", '{"a":1}\n', "media:enc=utf8;ext=ndjson;fmt=ndjson"),
    ("data.xml", "<a><b/></a>", "media:enc=utf8;ext=xml;fmt=xml"),
    ("config.toml", "a = 1\n", "media:enc=utf8;ext=toml"),
    ("README.md", "# Title\n", "media:enc=utf8;ext=md;plain-text"),
    ("run.log", "started\n", "media:enc=utf8;ext=log;plain-text"),
    ("page.html", "<html></html>", "media:enc=utf8;ext=html"),
    ("notebook.ipynb", '{"cells": []}', "media:enc=utf8;ext=jupyter;record"),
    ("report.pdf", "%PDF-1.4\n", "media:document;ext=pdf"),
    ("letter.docx", "PK", "media:document;ext=docx"),
    ("sheet.xlsx", "PK", "media:document;ext=xlsx"),
    ("photo.png", "\u0089PNG", "media:ext=png;image"),
    ("photo.jpg", "ÿØ", "media:ext=jpeg;image"),
    ("song.mp3", "ID3", "media:audio;ext=mp3"),
    ("clip.mp4", "ftyp", "media:ext=mp4;video"),
    ("bundle.zip", "PK", "media:archive;ext=zip"),
]


async def primary_without_adapters(reg: FabricRegistry, path: Path) -> str:
    try:
        found = await detect_file_media(path, reg, NoAdapters(), NoInvoker(), ValueAdapterRegistry())
    except InputResolverError as e:
        return f"error: {e}"
    return found.primary()


# TEST7181: with no cartridge to ask (the capdag CLI, a host before its
# cartridges attach), each common extension is the file type the fabric
# declares for it: a .txt is plain text, not digitized text; a .json is JSON,
# not a model download result; .csv, .tsv, .yaml and .yml are known; a
# refinement nothing proves (a JSON record, digitized text, a filing
# document) is never claimed
@pytest.mark.asyncio
async def test_7181_common_extensions_are_their_file_types_without_adapters(tmp_path):
    async with FixtureRegistry() as fixture:
        reg = warm_machine_registry(fixture.anchor)
        wrong = []
        for name, content, expected in NO_ADAPTER_TABLE:
            got = await primary_without_adapters(reg, write(tmp_path, name, content))
            if got != expected:
                wrong.append(f"{name}: {got}, expected {expected}")
        assert not wrong, "wrongly identified:\n  " + "\n  ".join(wrong)

        unknown = write(tmp_path, "thing.zzzz", "x")
        with pytest.raises(UnknownExtensionError) as exc_info:
            await detect_file_media(unknown, reg, NoAdapters(), NoInvoker(), ValueAdapterRegistry())
        assert exc_info.value.extension == "zzzz", str(exc_info.value)

        bare = write(tmp_path, "Makefile", "all:\n")
        with pytest.raises(NoExtensionError):
            await detect_file_media(bare, reg, NoAdapters(), NoInvoker(), ValueAdapterRegistry())


class BundledAdapters:
    """The adapter URNs datacartridge and txtcartridge declare, and what each
    claims the table's files are (their adapters' answers for that
    content)."""

    async def invoke_adapter_selection(self, cartridge_id: str, file_path: Path) -> Optional[List[str]]:
        name = file_path.name
        claims = {
            ("datacartridge", "record.json"): [
                "media:enc=utf8;ext=json;fmt=json;record",
                "media:enc=utf8;ext=json;fmt=json",
            ],
            ("datacartridge", "rows.json"): [
                "media:enc=utf8;ext=json;fmt=json;list;record",
                "media:enc=utf8;ext=json;fmt=json;list",
                "media:enc=utf8;ext=json;fmt=json",
            ],
            ("datacartridge", "people.csv"): ["media:enc=utf8;ext=csv;fmt=csv;list;record"],
            ("txtcartridge", "notes.txt"): ["media:enc=utf8;ext=txt;plain-text"],
        }.get((cartridge_id, name))
        if claims is None:
            raise AssertionError(f"{cartridge_id} was not expected to be asked about {name}")
        return list(claims)


def bundled_adapter_registry(fabric: FabricRegistry) -> MediaAdapterRegistry:
    adapters = MediaAdapterRegistry(fabric)
    adapters.register_cap_group(
        "data-formats",
        [
            "media:enc=utf8;fmt=json",
            "media:enc=utf8;fmt=ndjson",
            "media:enc=utf8;fmt=csv",
            "media:ext=tsv",
            "media:ext=psv",
            "media:enc=utf8;fmt=yaml",
            "media:ext=xml",
            "media:ext=toml",
        ],
        "datacartridge",
    )
    adapters.register_cap_group("text-formats", ["media:plain-text", "media:ext=html"], "txtcartridge")
    return adapters


# TEST7182: with the bundled cartridges' adapters (a desktop client), what a
# cartridge claims proves a refinement: a JSON object is a JSON record, an
# array of objects a list of records, and a .txt the cartridge reads as plain
# text is plain text, never digitized text
@pytest.mark.asyncio
async def test_7182_cartridge_claims_prove_refinements(tmp_path):
    async with FixtureRegistry() as fixture:
        fabric = warm_machine_registry(fixture.anchor)
        adapters = bundled_adapter_registry(fabric)

        async def detect(path: Path):
            return await detect_file_media(path, fabric, adapters, BundledAdapters(), ValueAdapterRegistry())

        found = await detect(write(tmp_path, "record.json", '{"name": "ann"}'))
        assert found.media == ["media:enc=utf8;ext=json;fmt=json;record"]

        found = await detect(write(tmp_path, "rows.json", '[{"name": "ann"}]'))
        assert found.media == ["media:enc=utf8;ext=json;fmt=json;list;record"]

        found = await detect(write(tmp_path, "people.csv", "name\nann\n"))
        assert found.media == ["media:enc=utf8;ext=csv;fmt=csv;list;record"]

        # pip's requirements files claim .txt too, and no cartridge speaks for
        # them, so a .txt is offered as either; a host that cannot ask takes
        # the plain text, the more specific.
        found = await detect(write(tmp_path, "notes.txt", "A line of text.\n"))
        assert found.media == ["media:enc=utf8;ext=requirements", "media:enc=utf8;ext=txt;plain-text"]
        assert found.primary() == "media:enc=utf8;ext=txt;plain-text"


# TEST7183: what a file is from its name alone is its extension's base types,
# never a refinement
@pytest.mark.asyncio
async def test_7183_a_files_media_by_name_alone_is_its_extensions_base_types():
    async with FixtureRegistry() as fixture:
        reg = warm_machine_registry(fixture.anchor)
        assert await extension_media("json", reg) == ["media:enc=utf8;ext=json;fmt=json"]
        txt = await extension_media("TXT", reg)
        assert txt == ["media:enc=utf8;ext=requirements", "media:enc=utf8;ext=txt;plain-text"]
        assert primary_media(txt) == "media:enc=utf8;ext=txt;plain-text"
        with pytest.raises(UnknownExtensionError):
            await extension_media("zzzz", reg)


# TEST7184: a refinement whose declared validation rules the content meets
# stands without a cartridge; one whose rules it fails falls; a definition
# with an invalid pattern is an error naming it
@pytest.mark.asyncio
async def test_7184_validation_rules_prove_or_disprove_a_refinement(tmp_path):
    def script(urn: str, pattern: str) -> StoredMediaDef:
        return StoredMediaDef.from_dict({
            "urn": urn, "version": 1, "media_type": "text/plain", "title": "t",
            "extensions": ["txt"], "validation": {"pattern": pattern},
        })

    base = StoredMediaDef.from_dict({
        "urn": "media:enc=utf8;ext=txt;plain-text", "version": 1, "media_type": "text/plain",
        "title": "Plain Text", "extensions": ["txt"],
    })
    reg = FabricRegistry.new_for_test()
    reg.add_spec(base)
    reg.add_spec(script("media:enc=utf8;ext=txt;plain-text;shebang", "^#!"))

    async def media(name: str, content: str) -> List[str]:
        path = write(tmp_path, name, content)
        found = await detect_file_media(path, reg, NoAdapters(), NoInvoker(), ValueAdapterRegistry())
        return found.media

    assert await media("run.txt", "#!/bin/sh\n") == ["media:enc=utf8;ext=txt;plain-text;shebang"]
    assert await media("prose.txt", "hello\n") == ["media:enc=utf8;ext=txt;plain-text"]

    broken = FabricRegistry.new_for_test()
    broken.add_spec(script("media:broken;enc=utf8;ext=txt;plain-text", "(("))
    path = write(tmp_path, "x.txt", "x")
    with pytest.raises(InputResolverError) as exc_info:
        await detect_file_media(path, broken, NoAdapters(), NoInvoker(), ValueAdapterRegistry())
    assert "media:broken;enc=utf8;ext=txt;plain-text" in str(exc_info.value), str(exc_info.value)
