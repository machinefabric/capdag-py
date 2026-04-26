"""Tests for bifaci cartridge repository models."""

import pytest

from capdag.bifaci.cartridge_repo import (
    CartridgeBuild,
    CartridgeDistributionInfo,
    CartridgeInfo,
    CartridgeRegistry,
    CartridgeRegistryEntry,
    CartridgeRegistryResponse,
    CartridgeRepo,
    CartridgeRepoError,
    CartridgeRepoServer,
    CartridgeVersionData,
    RegistryArgSource,
    RegistryCap,
    RegistryCapArg,
    RegistryCapGroup,
    RegistryCapOutput,
)
from capdag.urn.cap_urn import CapUrn


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _make_version_data(pkg_name: str = "test-1.0.0.pkg") -> CartridgeVersionData:
    return CartridgeVersionData(
        release_date="2026-02-07",
        changelog=[],
        min_app_version="",
        builds=[
            CartridgeBuild(
                platform="darwin-arm64",
                package=CartridgeDistributionInfo(
                    name=pkg_name,
                    sha256="abc123",
                    size=1000,
                ),
            )
        ],
    )


def _make_cap(urn: str, title: str = "Test Cap", command: str = "test") -> RegistryCap:
    return RegistryCap(urn=urn, title=title, command=command)


def _make_cap_group(name: str, caps=None, adapter_urns=None) -> RegistryCapGroup:
    return RegistryCapGroup(
        name=name,
        caps=list(caps or []),
        adapter_urns=list(adapter_urns or []),
    )


def _make_cartridge_info(
    *,
    id: str = "testcartridge",
    name: str = "Test Cartridge",
    cap_groups=None,
    page_url: str = "",
    description: str = "",
) -> CartridgeInfo:
    return CartridgeInfo(
        id=id,
        name=name,
        version="1.0.0",
        description=description,
        team_id="TEAM123",
        signed_at="2026-02-07T00:00:00Z",
        page_url=page_url,
        cap_groups=list(cap_groups or []),
        versions={"1.0.0": _make_version_data(f"{id}-1.0.0.pkg")},
        available_versions=["1.0.0"],
    )


def _make_registry_entry(
    *,
    name: str = "Test Cartridge",
    description: str = "A test cartridge",
    author: str = "Test Author",
    page_url: str = "",
    team_id: str = "TEAM123",
    min_app_version: str = "",
    cap_groups=None,
    categories=None,
    tags=None,
    latest_version: str = "1.0.0",
    versions=None,
):
    if cap_groups is None:
        cap_groups = []
    if categories is None:
        categories = []
    if tags is None:
        tags = []
    if versions is None:
        versions = {"1.0.0": _make_version_data()}
    return CartridgeRegistryEntry(
        name=name,
        description=description,
        author=author,
        page_url=page_url,
        team_id=team_id,
        min_app_version=min_app_version,
        cap_groups=cap_groups,
        categories=categories,
        tags=tags,
        latest_version=latest_version,
        versions=versions,
    )


# ---------------------------------------------------------------------------
# CartridgeInfo behaviour
# ---------------------------------------------------------------------------


# TEST320: Construct CartridgeInfo and verify field round-trip.
def test_320_construct_cartridge_info_and_verify_fields():
    cartridge = _make_cartridge_info(
        cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])]
    )
    assert cartridge.id == "testcartridge"
    assert cartridge.name == "Test Cartridge"
    assert cartridge.version == "1.0.0"
    assert len(cartridge.cap_groups) == 1
    assert sum(1 for _ in cartridge.iter_caps()) == 1


# TEST321: is_signed() requires both team_id and signed_at to be non-empty.
def test_321_cartridge_info_is_signed():
    cartridge = _make_cartridge_info()
    assert cartridge.is_signed()

    cartridge.team_id = ""
    assert not cartridge.is_signed()

    cartridge.team_id = "TEAM123"
    cartridge.signed_at = ""
    assert not cartridge.is_signed()


# TEST322: build_for_platform returns the matching build for the latest
# version, None for an unknown platform.
def test_322_cartridge_info_build_for_platform():
    cartridge = _make_cartridge_info()
    build = cartridge.build_for_platform("darwin-arm64")
    assert build is not None
    assert build.package.name == "testcartridge-1.0.0.pkg"
    assert cartridge.build_for_platform("linux-amd64") is None


# ---------------------------------------------------------------------------
# CartridgeRepoServer
# ---------------------------------------------------------------------------


# TEST323: Server requires schema 4.0 and rejects 2.0.
def test_323_cartridge_repo_server_validate_registry():
    CartridgeRepoServer(CartridgeRegistry(schema_version="4.0", last_updated="x", cartridges={}))

    with pytest.raises(CartridgeRepoError) as exc_info:
        CartridgeRepoServer(CartridgeRegistry(schema_version="2.0", last_updated="x", cartridges={}))
    assert "4.0" in str(exc_info.value)


# TEST324: Server transforms a v4.0 entry into a flat CartridgeInfo,
# preserving cap_groups verbatim.
def test_324_cartridge_repo_server_transform_to_array():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    cap_groups=[
                        _make_cap_group(
                            "g1",
                            caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")],
                            adapter_urns=["media:test"],
                        )
                    ],
                    categories=["test"],
                    tags=["testing"],
                )
            },
        )
    )

    cartridges = server.transform_to_cartridge_array()
    assert len(cartridges) == 1
    assert cartridges[0].id == "testcartridge"
    assert len(cartridges[0].cap_groups) == 1
    assert cartridges[0].cap_groups[0].adapter_urns == ["media:test"]
    assert sum(1 for _ in cartridges[0].iter_caps()) == 1


# TEST325: get_cartridges() wraps the transformed array in the response
# envelope.
def test_325_cartridge_repo_server_get_cartridges():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])]
                )
            },
        )
    )
    response = server.get_cartridges()
    assert len(response.cartridges) == 1
    assert response.cartridges[0].id == "testcartridge"


# TEST326: get_cartridge_by_id returns the entry for a known id, None
# for an unknown one.
def test_326_cartridge_repo_server_get_cartridge_by_id():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])]
                )
            },
        )
    )
    assert server.get_cartridge_by_id("testcartridge") is not None
    assert server.get_cartridge_by_id("nonexistent") is None


# TEST327: search_cartridges matches name/description/tags and cap
# titles, but never substring on cap URNs.
def test_327_cartridge_repo_server_search_cartridges():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "pdfcartridge": _make_registry_entry(
                    name="PDF Cartridge",
                    description="Process PDF documents",
                    tags=["document"],
                    cap_groups=[
                        _make_cap_group(
                            "pdf",
                            caps=[
                                _make_cap(
                                    'cap:in=media:pdf;op=disbind;out="media:page;textable"',
                                    title="Disbind PDF",
                                    command="disbind",
                                )
                            ],
                        )
                    ],
                )
            },
        )
    )
    assert len(server.search_cartridges("pdf")) == 1
    assert len(server.search_cartridges("disbind")) == 1
    assert server.search_cartridges("nonexistent") == []


# TEST328: get_cartridges_by_category filters by string-equal categories.
def test_328_cartridge_repo_server_get_by_category():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "doccartridge": _make_registry_entry(
                    name="Doc Cartridge",
                    description="Process documents",
                    cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])],
                    categories=["document"],
                )
            },
        )
    )
    assert len(server.get_cartridges_by_category("document")) == 1
    assert server.get_cartridges_by_category("nonexistent") == []


# TEST329: get_cartridges_by_cap parses the request URN and matches
# each cartridge cap via tagged-URN equivalence — not string equality.
# A request URN whose tags appear in different declared order than the
# cap's still resolves.
def test_329_cartridge_repo_server_get_by_cap():
    declared_urn = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    request_urn = 'cap:in="media:pdf";op=disbind;out="media:list;disbound-page;textable"'

    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "pdfcartridge": _make_registry_entry(
                    name="PDF Cartridge",
                    description="Process PDFs",
                    cap_groups=[
                        _make_cap_group(
                            "pdf",
                            caps=[_make_cap(declared_urn, title="Disbind PDF", command="disbind")],
                        )
                    ],
                )
            },
        )
    )

    assert len(server.get_cartridges_by_cap(declared_urn)) == 1
    assert len(server.get_cartridges_by_cap(request_urn)) == 1, "tagged-URN equivalence must resolve"
    assert server.get_cartridges_by_cap('cap:in="media:bogus";op=nope;out="media:nonexistent"') == []


# ---------------------------------------------------------------------------
# CartridgeRepo (cache)
# ---------------------------------------------------------------------------


# TEST330: update_cache populates the cartridge map and the cap-to-
# cartridges index keyed by normalized URNs.
def test_330_cartridge_repo_client_update_cache():
    repo = CartridgeRepo(3600)
    registry = CartridgeRegistryResponse(
        cartridges=[
            _make_cartridge_info(
                cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])]
            )
        ]
    )
    repo.update_cache("https://example.com/cartridges", registry)
    assert repo.get_cartridge("testcartridge") is not None


# TEST331: get_suggestions_for_cap returns a suggestion when the cache
# has a cartridge with a tagged-URN-equivalent cap, even if declared
# with different tag order.
def test_331_cartridge_repo_client_get_suggestions():
    repo = CartridgeRepo(3600)
    declared_urn = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    request_urn = 'cap:in="media:pdf";op=disbind;out="media:list;disbound-page;textable"'

    info = _make_cartridge_info(
        id="pdfcartridge",
        name="PDF Cartridge",
        description="Process PDFs",
        page_url="https://example.com/pdf",
        cap_groups=[_make_cap_group("pdf", caps=[_make_cap(declared_urn, title="Disbind PDF", command="disbind")])],
    )
    repo.update_cache("https://example.com/cartridges", CartridgeRegistryResponse(cartridges=[info]))

    suggestions = repo.get_suggestions_for_cap(request_urn)
    assert len(suggestions) == 1
    assert suggestions[0].cartridge_id == "pdfcartridge"
    assert suggestions[0].cap_title == "Disbind PDF"
    requested = CapUrn.from_string(request_urn)
    returned = CapUrn.from_string(suggestions[0].cap_urn)
    assert returned.is_equivalent(requested), "returned cap URN must be tagged-URN equivalent"


# TEST332: get_cartridge returns the cached entry by id and None for
# an unknown id.
def test_332_cartridge_repo_client_get_cartridge():
    repo = CartridgeRepo(3600)
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[
                _make_cartridge_info(
                    cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:in=media:;out=media:", "Identity", "identity")])]
                )
            ]
        ),
    )
    assert repo.get_cartridge("testcartridge") is not None
    assert repo.get_cartridge("nonexistent") is None


# TEST333: get_all_available_caps returns the deduplicated set of
# normalized URNs across cartridges.
def test_333_cartridge_repo_client_get_all_caps():
    repo = CartridgeRepo(3600)
    cap1 = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    cap2 = 'cap:in="media:txt;textable";op=disbind;out="media:disbound-page;textable;list"'
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[
                _make_cartridge_info(
                    id="cartridge1",
                    name="Cartridge 1",
                    cap_groups=[_make_cap_group("g", caps=[_make_cap(cap1, "Cap 1", "x")])],
                ),
                _make_cartridge_info(
                    id="cartridge2",
                    name="Cartridge 2",
                    cap_groups=[_make_cap_group("g", caps=[_make_cap(cap2, "Cap 2", "x")])],
                ),
            ]
        ),
    )
    caps = repo.get_all_available_caps()
    assert len(caps) == 2, f"expected two distinct caps, got {caps!r}"


# TEST334: needs_sync is true on an empty cache and false right after
# a successful update.
def test_334_cartridge_repo_client_needs_sync():
    repo = CartridgeRepo(3600)
    urls = ["https://example.com/cartridges"]
    assert repo.needs_sync(urls)

    repo.update_cache("https://example.com/cartridges", CartridgeRegistryResponse(cartridges=[]))
    assert not repo.needs_sync(urls)


# TEST335: A v4.0 nested registry round-trips through Server →
# CartridgeInfo, preserving the cap_groups structure and the signed
# flag.
def test_335_cartridge_repo_server_client_integration():
    cap_urn = 'cap:in="media:test";op=test;out="media:result"'
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    page_url="https://example.com",
                    cap_groups=[
                        _make_cap_group(
                            "test-group",
                            caps=[_make_cap(cap_urn, title="Test Cap", command="test")],
                            adapter_urns=["media:test"],
                        )
                    ],
                    categories=["test"],
                )
            },
        )
    )

    response = server.get_cartridges()
    assert len(response.cartridges) == 1
    cartridge = response.cartridges[0]
    assert cartridge.id == "testcartridge"
    assert cartridge.is_signed()
    assert cartridge.versions
    assert len(cartridge.cap_groups) == 1
    assert cartridge.cap_groups[0].adapter_urns == ["media:test"]
    assert sum(1 for _ in cartridge.iter_caps()) == 1


# TEST336: A registry response with a malformed cap URN inside
# cap_groups must propagate as ParseError when indexed into the cache,
# not silently disappear.
def test_336_update_cache_rejects_malformed_cap_urn():
    repo = CartridgeRepo(3600)
    registry = CartridgeRegistryResponse(
        cartridges=[
            _make_cartridge_info(
                id="broken",
                name="Broken",
                cap_groups=[_make_cap_group("g", caps=[_make_cap("not a valid urn at all", "Bad", "x")])],
            )
        ]
    )
    with pytest.raises(CartridgeRepoError):
        repo.update_cache("https://x", registry)


# ---------------------------------------------------------------------------
# Empty-state and wire-shape deserialization
# ---------------------------------------------------------------------------


# TEST630: CartridgeRepo creation starts with an empty cartridge list.
def test_630_cartridge_repo_creation():
    repo = CartridgeRepo(3600)
    assert repo.get_all_cartridges() == []


# TEST631: needs_sync returns true with an empty cache and non-empty
# URLs.
def test_631_needs_sync_empty_cache():
    repo = CartridgeRepo(3600)
    assert repo.needs_sync(["https://example.com/cartridges"])


# TEST632: A registry cap with only the three required fields parses.
def test_632_deserialize_minimal_registry_cap():
    cap = RegistryCap.from_dict(
        {
            "urn": "cap:in=media:;out=media:",
            "title": "Identity",
            "command": "identity",
        }
    )
    assert cap.urn == "cap:in=media:;out=media:"
    assert cap.title == "Identity"
    assert cap.command == "identity"
    assert cap.cap_description is None
    assert cap.args is None
    assert cap.output is None


# TEST633: A registry cap with cap_description / args / output parses.
def test_633_deserialize_rich_registry_cap():
    cap = RegistryCap.from_dict(
        {
            "urn": 'cap:in="media:pdf";op=disbind;out="media:page;textable"',
            "title": "Disbind PDF",
            "command": "disbind",
            "cap_description": "Extract each PDF page as plain page text.",
            "args": [
                {
                    "media_urn": "media:file-path;textable",
                    "required": True,
                    "is_sequence": False,
                    "sources": [
                        {"stdin": "media:pdf"},
                        {"position": 0},
                    ],
                    "arg_description": "Path to the PDF file to process",
                }
            ],
            "output": {
                "media_urn": "media:page;textable",
                "is_sequence": True,
                "output_description": "One page text per PDF page",
            },
        }
    )
    assert cap.command == "disbind"
    assert cap.cap_description == "Extract each PDF page as plain page text."
    assert cap.args is not None
    assert len(cap.args) == 1
    assert cap.args[0].media_urn == "media:file-path;textable"
    assert cap.args[0].sources[0].stdin == "media:pdf"
    assert cap.args[0].sources[1].position == 0
    assert cap.output is not None
    assert cap.output.media_urn == "media:page;textable"
    assert cap.output.is_sequence is True


# TEST634: A cap_group parses with caps + adapter_urns.
def test_634_deserialize_cap_group():
    group = RegistryCapGroup.from_dict(
        {
            "name": "pdf-formats",
            "caps": [
                {"urn": "cap:in=media:;out=media:", "title": "Identity", "command": "identity"}
            ],
            "adapter_urns": ["media:pdf"],
        }
    )
    assert group.name == "pdf-formats"
    assert len(group.caps) == 1
    assert group.adapter_urns == ["media:pdf"]


# TEST635: CartridgeInfo deserializes the wire shape exactly as
# returned by /api/cartridges (camelCase top-level + snake_case
# cap_groups). Null camelCase string fields become empty strings.
def test_635_deserialize_cartridge_info_wire_shape():
    cartridge = CartridgeInfo.from_dict(
        {
            "id": "pdfcartridge",
            "name": "pdfcartridge",
            "version": "0.179.441",
            "description": "PDF page renderer",
            "author": "https://github.com/machinefabric",
            "pageUrl": "https://github.com/machinefabric/pdfcartridge",
            "teamId": "P336JK947M",
            "signedAt": "2026-04-25T14:53:55Z",
            "minAppVersion": "1.0.0",
            "cap_groups": [
                {
                    "name": "pdf-formats",
                    "caps": [
                        {"urn": "cap:in=media:;out=media:", "title": "Identity", "command": "identity"},
                        {
                            "urn": 'cap:in=media:pdf;op=disbind;out="media:page;textable"',
                            "title": "Disbind PDF Into Page Text",
                            "command": "disbind",
                        },
                    ],
                    "adapter_urns": ["media:pdf"],
                }
            ],
            "categories": [],
            "tags": [],
            "versions": {},
            "availableVersions": [],
        }
    )
    assert cartridge.id == "pdfcartridge"
    assert cartridge.team_id == "P336JK947M"
    assert len(cartridge.cap_groups) == 1
    assert sum(1 for _ in cartridge.iter_caps()) == 2


# TEST636: CartridgeInfo with null version/description/author still
# deserializes cleanly (the null_as_empty_string deserializer is the
# only tolerated coercion).
def test_636_deserialize_cartridge_info_with_null_strings():
    cartridge = CartridgeInfo.from_dict(
        {
            "id": "mlxcartridge",
            "name": "MLX Cartridge",
            "version": None,
            "description": None,
            "author": None,
            "cap_groups": [],
            "versions": {},
        }
    )
    assert cartridge.version == ""
    assert cartridge.description == ""
    assert cartridge.author == ""
    assert cartridge.cap_groups == []


# TEST637: A full /api/cartridges-shaped response with two cartridges
# and nested cap_groups round-trips through the response wrapper.
def test_637_deserialize_full_registry_response():
    response = CartridgeRegistryResponse.from_dict(
        {
            "cartridges": [
                {
                    "id": "pdfcartridge",
                    "name": "pdfcartridge",
                    "version": "0.179.441",
                    "description": "PDF",
                    "author": "https://github.com/machinefabric",
                    "pageUrl": "",
                    "teamId": "P336JK947M",
                    "signedAt": "2026-04-25T14:53:55Z",
                    "minAppVersion": "1.0.0",
                    "cap_groups": [
                        {
                            "name": "pdf-formats",
                            "caps": [
                                {"urn": "cap:in=media:;out=media:", "title": "Identity", "command": "identity"}
                            ],
                            "adapter_urns": ["media:pdf"],
                        }
                    ],
                    "categories": [],
                    "tags": [],
                    "versions": {},
                    "availableVersions": [],
                },
                {
                    "id": "imagecartridge",
                    "name": "imagecartridge",
                    "version": "0.1.6",
                    "description": "image",
                    "author": "",
                    "teamId": "P336JK947M",
                    "signedAt": "2026-04-25T21:53:45Z",
                    "minAppVersion": "1.0.0",
                    "cap_groups": [
                        {
                            "name": "image-formats",
                            "caps": [
                                {
                                    "urn": 'cap:in="media:image;jpeg";op=convert_image;out="media:image;png"',
                                    "title": "Convert JPEG to PNG",
                                    "command": "convert-image",
                                }
                            ],
                            "adapter_urns": [
                                "media:bmp;image",
                                "media:image;jpeg",
                                "media:image;png",
                                "media:image;tiff",
                                "media:image;webp",
                                "media:gif;image",
                            ],
                        }
                    ],
                    "categories": [],
                    "tags": [],
                    "versions": {},
                    "availableVersions": [],
                },
            ],
            "total": 2,
            "page": 1,
            "limit": 20,
            "totalPages": 1,
        }
    )
    assert len(response.cartridges) == 2
    img = next(c for c in response.cartridges if c.id == "imagecartridge")
    assert len(img.cap_groups) == 1
    assert len(img.cap_groups[0].adapter_urns) == 6
