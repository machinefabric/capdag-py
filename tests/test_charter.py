"""Charters, read as a client of this mirror reads them. Mirrors the
structural half of Rust ``bifaci/charter_tests.rs``: the shape, the
locations, the folder a stored charter proves and the anchor a fetched one
must be for. The signature half (TEST12910, 12911, 12914–12918) has no
counterpart here, because this mirror verifies no chain (see
``capdag/bifaci/charter.py``). Every refusal below starts from a charter that
reads, changes one thing, and checks that the one thing is what is refused.
"""

import json

import httpx
import pytest

from capdag.bifaci.charter import (
    DEV_SLUG,
    CharterError,
    CharterFetchError,
    RegistryFolder,
    RegistryKind,
    fetch_charter,
    parse_charter,
    read_stored_charter,
    store_charter,
    stored_charter_for,
)
from tests.charter_fixtures import (
    CARTRIDGES_ANCHOR,
    CARTRIDGES_SLUG,
    cartridges_charter,
    fabric_charter,
    fetched,
    lab_charter,
    store_test_charter,
)


def _serving(charter_for_anchor):
    """A client whose transport serves, under ``https://served.example/fabric``,
    the charter ``charter_for_anchor(anchor)`` returns; anything else is 404."""
    anchor = "https://served.example/fabric"
    f = fetched(charter_for_anchor(anchor))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fabric/charter.json":
            return httpx.Response(200, content=f.body)
        if request.url.path == "/fabric/charter.json.sig":
            return httpx.Response(200, content=f.signature)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), anchor


# TEST12912: a valid charter served under another anchor is refused — a
# registry cannot borrow another's charter. Nothing at an anchor's
# charter.json makes it no registry at all.
@pytest.mark.asyncio
async def test_12912_a_charter_for_another_anchor_is_refused():
    client, anchor = _serving(lambda anchor: fabric_charter(anchor, "test-fabric"))
    got = await fetch_charter(client, anchor, RegistryKind.FABRIC)
    assert got.charter.anchor == anchor, "the charter served for its own anchor reads"

    borrowed, borrowed_anchor = _serving(
        lambda _anchor: fabric_charter("https://registry.example/fabric", "test-fabric")
    )
    with pytest.raises(CharterFetchError) as exc_info:
        await fetch_charter(borrowed, borrowed_anchor, RegistryKind.FABRIC)
    assert exc_info.value.kind == CharterFetchError.REFUSED

    with pytest.raises(CharterFetchError) as exc_info:
        await fetch_charter(client, "https://served.example/nowhere", RegistryKind.FABRIC)
    assert exc_info.value.kind == CharterFetchError.UNCHARTERED


# TEST12913: a charter of one kind does not stand for another kind — fetched,
# or stored in a registry's folder.
@pytest.mark.asyncio
async def test_12913_a_charter_of_another_kind_is_refused(tmp_path):
    client, anchor = _serving(lambda anchor: fabric_charter(anchor, "test-fabric"))
    with pytest.raises(CharterFetchError) as exc_info:
        await fetch_charter(client, anchor, RegistryKind.CARTRIDGES)
    assert exc_info.value.kind == CharterFetchError.REFUSED

    store_test_charter(tmp_path, "test-fabric", fabric_charter("https://registry.example/fabric", "test-fabric"))
    with pytest.raises(CharterError):
        read_stored_charter(tmp_path / "test-fabric", RegistryKind.CARTRIDGES)
    read_stored_charter(tmp_path / "test-fabric", RegistryKind.FABRIC)


# TEST12919: a location is filled with exactly the placeholders it takes —
# one missing, or one it does not take, is refused rather than guessed.
def test_12919_a_location_takes_exactly_its_placeholders():
    fabric = fabric_charter("https://registry.example/fabric", "test-fabric")
    assert (
        fabric.location("definition", {"kind": "caps", "urn_hash": "ab12", "version": "3"})
        == "https://registry.example/fabric/caps/ab12/3.json"
    )
    with pytest.raises(CharterError):
        fabric.location("definition", {"kind": "caps", "urn_hash": "ab12"})
    with pytest.raises(CharterError):
        fabric.location("latest", {"version": "3"})
    with pytest.raises(CharterError):
        fabric.location("schema", {})


# TEST12920: the shape every charter must have. Each case is a charter that
# reads with one thing wrong; the unchanged charter passes, so each refusal is
# about the one change.
def test_12920_a_charter_out_of_shape_is_malformed():
    cartridges_charter().validate()
    lab_charter().validate()
    body = json.dumps(cartridges_charter().to_dict())
    parse_charter(body.encode())

    def refused(why, change):
        c = cartridges_charter()
        change(c)
        with pytest.raises(CharterError):
            c.validate()
            pytest.fail(f"{why} was accepted")

    refused("an http anchor", lambda c: setattr(c, "anchor", "http://registry.example/cartridges"))
    refused("an anchor ending in /", lambda c: setattr(c, "anchor", c.anchor + "/"))
    refused("the reserved dev slug", lambda c: setattr(c, "slug", DEV_SLUG))
    refused("a slug outside [a-z0-9.-]", lambda c: setattr(c, "slug", "Has_Upper"))
    refused("no manifest location", lambda c: c.locations.clear())
    refused(
        "a manifest location without {registry_version}",
        lambda c: c.locations.update(manifest="https://r.example/manifest"),
    )
    refused(
        "a placeholder the location does not take",
        lambda c: c.locations.update(manifest="https://r.example/v{registry_version}/{app_id}"),
    )
    refused("a location of another kind", lambda c: c.locations.update(latest="https://r.example/latest"))
    refused("a cartridges registry with no fabric", lambda c: setattr(c, "fabric", None))
    refused("an experiment that is not an id", lambda c: setattr(c, "experiment", "Not An Id"))
    refused("a not_after that is not after issue", lambda c: setattr(c, "not_after", c.issued_at))

    with pytest.raises(CharterError):
        parse_charter(body.replace('"anchor"', '"surprise": 1, "anchor"', 1).encode())
    with pytest.raises(CharterError, match="format"):
        parse_charter(body.replace("machinefabric-registry-charter/1", "machinefabric-manifest-sig/1").encode())


# TEST12921: a stored charter proves its folder only under its own slug: a
# folder renamed after install is refused, though the charter reads.
def test_12921_a_stored_charter_holds_its_folder_to_its_slug(tmp_path):
    store_test_charter(tmp_path, CARTRIDGES_SLUG)
    opened = read_stored_charter(tmp_path / CARTRIDGES_SLUG, RegistryKind.CARTRIDGES)
    assert opened.anchor == CARTRIDGES_ANCHOR

    renamed = tmp_path / "cartridges.machinefabric.com"
    (tmp_path / CARTRIDGES_SLUG).rename(renamed)
    with pytest.raises(CharterError, match="stored in a folder named 'cartridges.machinefabric.com'"):
        read_stored_charter(renamed, RegistryKind.CARTRIDGES)
    with pytest.raises(CharterError):
        store_charter(fetched(cartridges_charter()), renamed)


# TEST12922: a registry folder is opened through its charter, and found by
# its anchor — never by its name. `dev` is the one folder with no charter.
def test_12922_registry_folders_are_found_by_their_charters(tmp_path):
    store_test_charter(tmp_path, CARTRIDGES_SLUG)
    lab = lab_charter()
    store_test_charter(tmp_path, lab.slug, lab)
    (tmp_path / DEV_SLUG).mkdir()
    # A folder named like the anchor's host holds no charter, and is not it.
    (tmp_path / "registry.example").mkdir()

    found = stored_charter_for(tmp_path, CARTRIDGES_ANCHOR, RegistryKind.CARTRIDGES)
    assert found is not None, "the registry's folder is found by its anchor"
    folder, charter = found
    assert folder == tmp_path / CARTRIDGES_SLUG
    assert charter.slug == CARTRIDGES_SLUG
    assert stored_charter_for(tmp_path, "https://registry.example/elsewhere", RegistryKind.CARTRIDGES) is None

    dev = RegistryFolder.open(tmp_path / DEV_SLUG)
    assert dev.slug == DEV_SLUG
    assert dev.anchor is None
    assert RegistryFolder.open(tmp_path / CARTRIDGES_SLUG).anchor == CARTRIDGES_ANCHOR
    with pytest.raises(CharterError):
        RegistryFolder.open(tmp_path / "registry.example")
