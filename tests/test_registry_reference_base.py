"""A cap may name a published media type refined by an absence (``!k``) or
leaving a key open (``?k``): the registry holds the published definition the
reference resolves to, and the cap keeps its own URN.

Tests use # TEST###: comments matching the Rust implementation for
cross-tracking.
"""

import json
import tempfile
from pathlib import Path

import httpx
import pytest

from capdag import CapUrn
from capdag.fabric import cache
from capdag.fabric.registry import (
    FabricLocations,
    FabricRegistry,
    Manifest,
    RegistryConfig,
    normalize_cap_urn,
    normalize_media_urn,
    publisher_layout_charter,
)
from capdag.urn.media_urn import MediaUrn
from tests.stub_registry import Answer, StubRegistry

JSON = "media:enc=utf8;fmt=json"
CONTENT = "media:enc=utf8;fmt=json;!ext"
ANY_SHAPE = "media:enc=utf8;fmt=json;?list;?record"
CAP = f'cap:in="{CONTENT}";out="{ANY_SHAPE}";reference-probe'


# TEST7211: a cap whose sides name the published media:enc=utf8;fmt=json
# refined by an absence (!ext) and by open keys (?list;?record) is held: its
# media footprint is that one definition, fetched at the version the manifest
# pins for it, and the cap keeps its URN as written.
@pytest.mark.asyncio
async def test_7211_a_cap_naming_a_published_type_refined_by_absence_is_held():
    cap_key = normalize_cap_urn(CAP)
    json_key = normalize_media_urn(JSON)
    cap_body = json.dumps({
        "urn": CAP, "version": 1, "title": "Reference probe", "aliases": ["reference-probe"],
        "args": [{"media_urn": CONTENT, "name": "input", "required": True,
                  "sources": [{"stdin": CONTENT}]}],
        "outputs": [{"media_urn": ANY_SHAPE, "name": "output", "output_description": "out"}],
    }).encode()
    media_body = json.dumps({
        "urn": JSON, "version": 1, "title": "JSON", "media_type": "application/json",
    }).encode()

    paths = {}

    def answer(path: str) -> Answer:
        if path == paths["cap"]:
            return Answer(body=cap_body)
        if path == paths["media"]:
            return Answer(body=media_body)
        return Answer(status=404)

    async with StubRegistry(answer) as stub:
        locations = FabricLocations.from_charter(publisher_layout_charter(stub.anchor))
        cap_url = locations.definition("caps", cache.key_hash(cap_key), 1)
        media_url = locations.definition("media", cache.key_hash(json_key), 1)
        paths["cap"] = cap_url[len(stub.anchor):]
        paths["media"] = media_url[len(stub.anchor):]

        manifest = Manifest.empty(12)
        manifest.caps[cap_key] = 1
        manifest.media[json_key] = 1
        registry = FabricRegistry(
            Path(tempfile.mkdtemp(prefix="capdag-reference-base-")),
            RegistryConfig().with_anchor(stub.anchor),
            publisher_layout_charter(stub.anchor),
            httpx.AsyncClient(timeout=10.0),
            12,
            manifest,
        )

        held = await registry.get_cap(cap_key)
        assert held.urn.in_spec() == MediaUrn.from_string(CONTENT).to_string()
        assert held.urn.out_spec() == MediaUrn.from_string(ANY_SHAPE).to_string()
        assert registry._collect_referenced_media_urns(held) == [json_key]

        # Each side's type is drawn with the title of the definition it resolves to.
        for side in (CONTENT, ANY_SHAPE):
            assert registry.get_cached_media_def(side).title == "JSON", side
        assert stub.requests_for(media_url) == 1, "the base definition is fetched once"
        assert sum(stub.requests.values()) == 2, "the cap and its one media definition"
