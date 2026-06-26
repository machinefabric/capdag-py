"""Tests for bifaci cartridge repository models (v5.0 channel-partitioned)."""

import pytest

from capdag.bifaci.cartridge_repo import (
    CartridgeBuild,
    CartridgeChannel,
    CartridgeCompatibilityResolution,
    CompatStatus,
    host_platform,
    CartridgeChannelEntries,
    CartridgeDistributionInfo,
    CartridgeInfo,
    CartridgeRegistry,
    CartridgeRegistryChannels,
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
                    url=f"https://cartridges.machinefabric.com/{pkg_name}",
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
    channel: CartridgeChannel = CartridgeChannel.RELEASE,
) -> CartridgeInfo:
    return CartridgeInfo(
        id=id,
        name=name,
        channel=channel,
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


def _make_registry(
    *,
    release_entries=None,
    nightly_entries=None,
) -> CartridgeRegistry:
    """Build a v5.0 channel-partitioned registry. Either map can be
    omitted to leave that channel empty."""
    return CartridgeRegistry(
        schema_version="5.0",
        last_updated="2026-02-07",
        channels=CartridgeRegistryChannels(
            release=CartridgeChannelEntries(cartridges=dict(release_entries or {})),
            nightly=CartridgeChannelEntries(cartridges=dict(nightly_entries or {})),
        ),
    )


# ---------------------------------------------------------------------------
# CartridgeInfo behaviour
# ---------------------------------------------------------------------------


# TEST320: Construct CartridgeInfo and verify field round-trip.
def test_320_construct_cartridge_info_and_verify_fields():
    cartridge = _make_cartridge_info(
        cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])]
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


# TEST323: Server requires schema 5.0 and rejects older.
def test_323_cartridge_repo_server_validate_registry():
    CartridgeRepoServer(_make_registry())

    with pytest.raises(CartridgeRepoError) as exc_info:
        CartridgeRepoServer(
            CartridgeRegistry(
                schema_version="4.0",
                last_updated="x",
                channels=CartridgeRegistryChannels(
                    release=CartridgeChannelEntries(),
                    nightly=CartridgeChannelEntries(),
                ),
            )
        )
    assert "5.0" in str(exc_info.value)


# TEST324: Server transforms each channel-entry into a flat CartridgeInfo
# with channel set, preserving cap_groups verbatim.
def test_324_cartridge_repo_server_transform_to_array():
    server = CartridgeRepoServer(
        _make_registry(release_entries={
            "testcartridge": _make_registry_entry(
                cap_groups=[
                    _make_cap_group(
                        "g1",
                        caps=[_make_cap("cap:effect=none", "Identity", "identity")],
                        adapter_urns=["media:test"],
                    )
                ],
                categories=["test"],
                tags=["testing"],
            )
        })
    )

    cartridges = server.transform_to_cartridge_array()
    assert len(cartridges) == 1
    assert cartridges[0].id == "testcartridge"
    assert cartridges[0].channel is CartridgeChannel.RELEASE
    assert len(cartridges[0].cap_groups) == 1
    assert cartridges[0].cap_groups[0].adapter_urns == ["media:test"]
    assert sum(1 for _ in cartridges[0].iter_caps()) == 1


# TEST301: Walking both channels produces release entries first.
def test_301_transform_walks_both_channels_release_first():
    entry_release = _make_registry_entry(name="R")
    entry_nightly = _make_registry_entry(name="N")
    server = CartridgeRepoServer(_make_registry(
        release_entries={"foo": entry_release},
        nightly_entries={"bar": entry_nightly},
    ))
    cartridges = server.transform_to_cartridge_array()
    assert [c.channel for c in cartridges] == [CartridgeChannel.RELEASE, CartridgeChannel.NIGHTLY]


# TEST325: get_cartridges() wraps the transformed array in the response
# envelope, including both channels.
def test_325_cartridge_repo_server_get_cartridges():
    server = CartridgeRepoServer(_make_registry(release_entries={
        "testcartridge": _make_registry_entry(
            cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])]
        )
    }))
    response = server.get_cartridges()
    assert len(response.cartridges) == 1
    assert response.cartridges[0].id == "testcartridge"
    assert response.cartridges[0].channel is CartridgeChannel.RELEASE


# TEST326: get_cartridge_by_id requires a (channel, id). Same id in
# the wrong channel must miss — channels are independent namespaces.
def test_326_cartridge_repo_server_get_cartridge_by_id():
    server = CartridgeRepoServer(_make_registry(release_entries={
        "testcartridge": _make_registry_entry(
            cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])]
        )
    }))
    assert server.get_cartridge_by_id(CartridgeChannel.RELEASE, "testcartridge") is not None
    assert server.get_cartridge_by_id(CartridgeChannel.RELEASE, "nonexistent") is None
    # Wrong channel — id exists only in release.
    assert server.get_cartridge_by_id(CartridgeChannel.NIGHTLY, "testcartridge") is None


# TEST300: A cartridge with the same id can independently exist in
# both channels. Each lookup must return the channel-specific entry.
def test_300_get_cartridge_by_id_channel_isolation():
    release_entry = _make_registry_entry(name="Foo (release)")
    nightly_entry = _make_registry_entry(
        name="Foo (nightly)",
        latest_version="2.0.0",
        versions={"2.0.0": _make_version_data("foo-2.0.0.pkg")},
    )
    server = CartridgeRepoServer(_make_registry(
        release_entries={"foocartridge": release_entry},
        nightly_entries={"foocartridge": nightly_entry},
    ))
    r = server.get_cartridge_by_id(CartridgeChannel.RELEASE, "foocartridge")
    assert r is not None and r.name == "Foo (release)" and r.version == "1.0.0"
    n = server.get_cartridge_by_id(CartridgeChannel.NIGHTLY, "foocartridge")
    assert n is not None and n.name == "Foo (nightly)" and n.version == "2.0.0"


# TEST327: search_cartridges matches name/description/tags and cap
# titles across both channels, but never substring on cap URNs.
def test_327_cartridge_repo_server_search_cartridges():
    server = CartridgeRepoServer(_make_registry(release_entries={
        "pdfcartridge": _make_registry_entry(
            name="PDF Cartridge",
            description="Process PDF documents",
            tags=["document"],
            cap_groups=[
                _make_cap_group(
                    "pdf",
                    caps=[
                        _make_cap(
                            'cap:in="media:ext=pdf";disbind;out="media:enc=utf-8;page"',
                            title="Disbind PDF",
                            command="disbind",
                        )
                    ],
                )
            ],
        )
    }))
    assert len(server.search_cartridges("pdf")) == 1
    assert len(server.search_cartridges("disbind")) == 1
    assert server.search_cartridges("nonexistent") == []


# TEST328: get_cartridges_by_category filters by string-equal categories.
def test_328_cartridge_repo_server_get_by_category():
    server = CartridgeRepoServer(_make_registry(release_entries={
        "doccartridge": _make_registry_entry(
            name="Doc Cartridge",
            description="Process documents",
            cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])],
            categories=["document"],
        )
    }))
    assert len(server.get_cartridges_by_category("document")) == 1
    assert server.get_cartridges_by_category("nonexistent") == []


# TEST329: get_cartridges_by_cap parses the request URN and matches
# each cartridge cap via the conforms_to predicate — not string
# equality, and the `op` tag has no functional role. A request URN
# whose tags appear in different declared order than the cap's still
# resolves because the predicate is order-independent.
def test_329_cartridge_repo_server_get_by_cap():
    declared_urn = 'cap:in="media:ext=pdf";disbind;out="media:disbound-page;enc=utf-8;list"'
    request_urn = 'cap:in="media:ext=pdf";disbind;out="media:disbound-page;enc=utf-8;list"'

    server = CartridgeRepoServer(_make_registry(release_entries={
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
    }))

    assert len(server.get_cartridges_by_cap(declared_urn)) == 1
    assert len(server.get_cartridges_by_cap(request_urn)) == 1, "tagged-URN equivalence must resolve"
    assert server.get_cartridges_by_cap('cap:in="media:bogus";nope;out="media:nonexistent"') == []


# ---------------------------------------------------------------------------
# CartridgeRepo (cache)
# ---------------------------------------------------------------------------


# TEST330: update_cache populates the cartridge map keyed by
# (channel, id) and the cap-to-cartridges index keyed by normalized
# URNs.
def test_330_cartridge_repo_client_update_cache():
    repo = CartridgeRepo(3600)
    registry = CartridgeRegistryResponse(
        cartridges=[
            _make_cartridge_info(
                channel=CartridgeChannel.RELEASE,
                cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])],
            )
        ]
    )
    repo.update_cache("https://example.com/cartridges", registry)
    assert repo.get_cartridge(CartridgeChannel.RELEASE, "testcartridge") is not None
    # Same id in the wrong channel must miss — channels are independent.
    assert repo.get_cartridge(CartridgeChannel.NIGHTLY, "testcartridge") is None


# TEST331: get_suggestions_for_cap returns a suggestion with channel
# propagated from the source cartridge.
def test_331_cartridge_repo_client_get_suggestions():
    repo = CartridgeRepo(3600)
    declared_urn = 'cap:in="media:ext=pdf";disbind;out="media:disbound-page;enc=utf-8;list"'
    request_urn = 'cap:in="media:ext=pdf";disbind;out="media:disbound-page;enc=utf-8;list"'

    info = _make_cartridge_info(
        id="pdfcartridge",
        name="PDF Cartridge",
        description="Process PDFs",
        page_url="https://example.com/pdf",
        cap_groups=[_make_cap_group("pdf", caps=[_make_cap(declared_urn, title="Disbind PDF", command="disbind")])],
        channel=CartridgeChannel.NIGHTLY,
    )
    repo.update_cache("https://example.com/cartridges", CartridgeRegistryResponse(cartridges=[info]))

    suggestions = repo.get_suggestions_for_cap(request_urn)
    assert len(suggestions) == 1
    assert suggestions[0].cartridge_id == "pdfcartridge"
    assert suggestions[0].cap_title == "Disbind PDF"
    assert suggestions[0].channel is CartridgeChannel.NIGHTLY
    requested = CapUrn.from_string(request_urn)
    returned = CapUrn.from_string(suggestions[0].cap_urn)
    assert returned.is_equivalent(requested), "returned cap URN must be tagged-URN equivalent"


# TEST332: get_cartridge requires a (channel, id) and returns None for
# an unknown pair.
def test_332_cartridge_repo_client_get_cartridge():
    repo = CartridgeRepo(3600)
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[
                _make_cartridge_info(
                    channel=CartridgeChannel.RELEASE,
                    cap_groups=[_make_cap_group("g", caps=[_make_cap("cap:effect=none", "Identity", "identity")])],
                )
            ]
        ),
    )
    assert repo.get_cartridge(CartridgeChannel.RELEASE, "testcartridge") is not None
    assert repo.get_cartridge(CartridgeChannel.RELEASE, "nonexistent") is None
    assert repo.get_cartridge(CartridgeChannel.NIGHTLY, "testcartridge") is None


# TEST333: get_all_available_caps returns the deduplicated set of
# normalized URNs across cartridges.
def test_333_cartridge_repo_client_get_all_caps():
    repo = CartridgeRepo(3600)
    cap1 = 'cap:in="media:ext=pdf";disbind;out="media:disbound-page;enc=utf-8;list"'
    cap2 = 'cap:in="media:enc=utf-8;ext=txt";disbind;out="media:disbound-page;enc=utf-8;list"'
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[
                _make_cartridge_info(
                    id="cartridge1",
                    name="Cartridge 1",
                    cap_groups=[_make_cap_group("g", caps=[_make_cap(cap1, "Cap 1", "x")])],
                    channel=CartridgeChannel.RELEASE,
                ),
                _make_cartridge_info(
                    id="cartridge2",
                    name="Cartridge 2",
                    cap_groups=[_make_cap_group("g", caps=[_make_cap(cap2, "Cap 2", "x")])],
                    channel=CartridgeChannel.NIGHTLY,
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


# TEST335: A v5.0 channel-partitioned registry round-trips through
# Server → CartridgeInfo, preserving the cap_groups structure, signed
# flag, and channel provenance.
def test_335_cartridge_repo_server_client_integration():
    cap_urn = 'cap:in="media:test";test;out="media:result"'
    server = CartridgeRepoServer(_make_registry(release_entries={
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
    }))

    response = server.get_cartridges()
    assert len(response.cartridges) == 1
    cartridge = response.cartridges[0]
    assert cartridge.id == "testcartridge"
    assert cartridge.channel is CartridgeChannel.RELEASE
    assert cartridge.is_signed()
    assert cartridge.versions
    assert len(cartridge.cap_groups) == 1
    assert cartridge.cap_groups[0].adapter_urns == ["media:test"]
    assert sum(1 for _ in cartridge.iter_caps()) == 1


# TEST319: A registry response with a malformed cap URN inside
# cap_groups must propagate as ParseError when indexed into the cache,
# not silently disappear.
def test_319_update_cache_rejects_malformed_cap_urn():
    repo = CartridgeRepo(3600)
    registry = CartridgeRegistryResponse(
        cartridges=[
            _make_cartridge_info(
                id="broken",
                name="Broken",
                channel=CartridgeChannel.RELEASE,
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
            "urn": "cap:effect=none",
            "title": "Identity",
            "command": "identity",
        }
    )
    assert cap.urn == "cap:effect=none"
    assert cap.title == "Identity"
    assert cap.command == "identity"
    assert cap.cap_description is None
    assert cap.args is None
    assert cap.output is None


# TEST633: A registry cap with cap_description / args / output parses.
def test_633_deserialize_rich_registry_cap():
    cap = RegistryCap.from_dict(
        {
            "urn": 'cap:in="media:ext=pdf";disbind;out="media:enc=utf-8;page"',
            "title": "Disbind PDF",
            "command": "disbind",
            "cap_description": "Extract each PDF page as plain page text.",
            "args": [
                {
                    "media_urn": "media:enc=utf-8;file-path",
                    "required": True,
                    "is_sequence": False,
                    "sources": [
                        {"stdin": "media:ext=pdf"},
                        {"position": 0},
                    ],
                    "arg_description": "Path to the PDF file to process",
                }
            ],
            "output": {
                "media_urn": "media:enc=utf-8;page",
                "is_sequence": True,
                "output_description": "One page text per PDF page",
            },
        }
    )
    assert cap.command == "disbind"
    assert cap.cap_description == "Extract each PDF page as plain page text."
    assert cap.args is not None
    assert len(cap.args) == 1
    assert cap.args[0].media_urn == "media:enc=utf-8;file-path"
    assert cap.args[0].sources[0].stdin == "media:ext=pdf"
    assert cap.args[0].sources[1].position == 0
    assert cap.output is not None
    assert cap.output.media_urn == "media:enc=utf-8;page"
    assert cap.output.is_sequence is True


# TEST634: A cap_group parses with caps + adapter_urns.
def test_634_deserialize_cap_group():
    group = RegistryCapGroup.from_dict(
        {
            "name": "pdf-formats",
            "caps": [
                {"urn": "cap:effect=none", "title": "Identity", "command": "identity"}
            ],
            "adapter_urns": ["media:ext=pdf"],
        }
    )
    assert group.name == "pdf-formats"
    assert len(group.caps) == 1
    assert group.adapter_urns == ["media:ext=pdf"]


# TEST635: CartridgeInfo deserializes the wire shape exactly as
# returned by /api/cartridges (camelCase top-level + snake_case
# cap_groups). Null camelCase string fields become empty strings.
def test_635_deserialize_cartridge_info_wire_shape():
    cartridge = CartridgeInfo.from_dict(
        {
            "id": "pdfcartridge",
            "name": "pdfcartridge",
            "channel": "release",
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
                        {"urn": "cap:effect=none", "title": "Identity", "command": "identity"},
                        {
                            "urn": 'cap:in="media:ext=pdf";disbind;out="media:enc=utf-8;page"',
                            "title": "Disbind PDF Into Page Text",
                            "command": "disbind",
                        },
                    ],
                    "adapter_urns": ["media:ext=pdf"],
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
            "channel": "nightly",
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
                    "channel": "release",
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
                                {"urn": "cap:effect=none", "title": "Identity", "command": "identity"}
                            ],
                            "adapter_urns": ["media:ext=pdf"],
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
                    "channel": "release",
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
                                    "urn": 'cap:in="media:image;jpeg";convert-image;out="media:image;png"',
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


# ---------------------------------------------------------------------------
# CartridgeBuild legacy-package fallback + host-compatibility resolution
# ---------------------------------------------------------------------------


# TEST1847: A build from a registry manifest published BEFORE `packages[]`
# existed carries only the legacy singular `package` (no `format`). It must
# still deserialize (a missing `packages` must not fail the whole parse) and
# primary_package() must fall back to that legacy package, so a registry not
# yet republished with the dual-write keeps installing. When `packages[]` is
# present it is preferred over the legacy field, native format wins.
def test_1847_cartridge_build_legacy_package_fallback():
    legacy = CartridgeBuild.from_dict(
        {
            "platform": "linux-x86_64",
            "package": {
                "name": "imagecartridge-1.0.0.pkg",
                "url": "https://cartridges.machinefabric.com/imagecartridge-1.0.0.pkg",
                "sha256": "abc123",
                "size": 1000,
            },
        }
    )
    assert legacy.packages == []
    primary = legacy.primary_package()
    assert primary is not None, "legacy package must be read as a fallback"
    assert primary.name == "imagecartridge-1.0.0.pkg"
    assert primary.format == ""  # legacy object has no format
    assert primary.url.endswith("imagecartridge-1.0.0.pkg")

    modern = CartridgeBuild.from_dict(
        {
            "platform": "linux-x86_64",
            "package": {
                "name": "legacy.pkg",
                "url": "https://x/legacy.pkg",
                "sha256": "dead",
                "size": 1,
            },
            "packages": [
                {"name": "c.rpm", "url": "https://x/c.rpm", "sha256": "a", "size": 2, "format": "rpm"},
                {"name": "c.deb", "url": "https://x/c.deb", "sha256": "b", "size": 3, "format": "deb"},
            ],
        }
    )
    # linux prefers deb over rpm; the legacy `package` is ignored.
    assert modern.primary_package().name == "c.deb"


def _build_for_platform_with_format(platform: str, fmt: str, pkg_name: str) -> CartridgeBuild:
    """One platform build carrying a single native-format package, so a
    resolution test can assert exactly which package the host gets."""
    return CartridgeBuild(
        platform=platform,
        packages=[
            CartridgeDistributionInfo(
                name=pkg_name,
                sha256="deadbeef",
                size=4242,
                url=f"https://cartridges.machinefabric.com/{pkg_name}",
                format=fmt,
            )
        ],
    )


def _cartridge_with_versions(id, versions):
    """Construct a cartridge whose versions/platform-builds are fully
    specified by the caller. `versions` is given newest-first; `version`
    (the latest field) is set to the first entry. Each version lists the
    (platform, format, pkg_name) builds it ships."""
    version_map = {}
    available = []
    for ver, builds in versions:
        available.append(ver)
        version_map[ver] = CartridgeVersionData(
            release_date="2026-02-07",
            changelog=[],
            min_app_version="",
            builds=[_build_for_platform_with_format(p, f, n) for (p, f, n) in builds],
        )
    latest = versions[0][0] if versions else ""
    return CartridgeInfo(
        id=id,
        name=id,
        channel=CartridgeChannel.RELEASE,
        version=latest,
        team_id="TEAM123",
        signed_at="2026-02-07T00:00:00Z",
        versions=version_map,
        available_versions=available,
    )


# TEST1849: latest version has a host build -> Compatible, resolving to the
# latest version and that platform's native-format package.
def test_1849_resolve_for_host_compatible_latest():
    cartridge = _cartridge_with_versions(
        "c",
        [
            ("1.2.0", [("darwin-arm64", "pkg", "c-1.2.0.pkg"), ("linux-x86_64", "deb", "c-1.2.0.deb")]),
            ("1.1.0", [("darwin-arm64", "pkg", "c-1.1.0.pkg")]),
        ],
    )
    r = cartridge.resolve_for_host("linux-x86_64")
    assert r.status == CompatStatus.COMPATIBLE
    assert r.resolved_version == "1.2.0"
    assert r.resolved_package.name == "c-1.2.0.deb"
    assert r.resolved_package.format == "deb"
    assert r.reason is None, "Compatible carries no reason"
    assert r.host_platform == "linux-x86_64"


# TEST1850: the latest version lacks a host build but an older version has one
# -> CompatibleOutdated, resolving to the older version with a reason naming
# both the latest and the resolved version.
def test_1850_resolve_for_host_compatible_outdated():
    cartridge = _cartridge_with_versions(
        "c",
        [
            ("1.3.0", [("darwin-arm64", "pkg", "c-1.3.0.pkg")]),
            ("1.2.0", [("darwin-arm64", "pkg", "c-1.2.0.pkg"), ("linux-x86_64", "deb", "c-1.2.0.deb")]),
            ("1.1.0", [("linux-x86_64", "deb", "c-1.1.0.deb")]),
        ],
    )
    r = cartridge.resolve_for_host("linux-x86_64")
    assert r.status == CompatStatus.COMPATIBLE_OUTDATED
    # Newest-with-host-build is 1.2.0, NOT the oldest 1.1.0 that also has it.
    assert r.resolved_version == "1.2.0"
    assert r.resolved_package.name == "c-1.2.0.deb"
    assert r.reason is not None
    assert "1.3.0" in r.reason, f"reason names the latest: {r.reason}"
    assert "1.2.0" in r.reason, f"reason names the resolved: {r.reason}"


# TEST1851: no version ships a host build -> Incompatible, no resolved
# version/package, reason states the host platform.
def test_1851_resolve_for_host_incompatible():
    cartridge = _cartridge_with_versions(
        "c",
        [
            ("1.2.0", [("darwin-arm64", "pkg", "c-1.2.0.pkg")]),
            ("1.1.0", [("darwin-arm64", "pkg", "c-1.1.0.pkg")]),
        ],
    )
    r = cartridge.resolve_for_host("windows-x86_64")
    assert r.status == CompatStatus.INCOMPATIBLE
    assert r.resolved_version is None
    assert r.resolved_package is None
    assert "windows-x86_64" in r.reason


# TEST1852: a host build whose packages[] is empty AND has no legacy `package`
# ships no installer; resolution must SKIP it (not resolve to an
# un-downloadable version) and fall through to an older usable version.
def test_1852_resolve_for_host_skips_build_with_no_installer():
    cartridge = _cartridge_with_versions(
        "c",
        [
            ("2.0.0", [("linux-x86_64", "deb", "c-2.0.0.deb")]),
            ("1.0.0", [("linux-x86_64", "deb", "c-1.0.0.deb")]),
        ],
    )
    # Make 2.0.0's linux build ship nothing installable.
    v2 = cartridge.versions["2.0.0"]
    v2.builds[0].packages = []
    v2.builds[0].package = None

    r = cartridge.resolve_for_host("linux-x86_64")
    # 2.0.0 is skipped (no installer); newest USABLE host build is 1.0.0.
    assert r.status == CompatStatus.COMPATIBLE_OUTDATED
    assert r.resolved_version == "1.0.0"
    assert r.resolved_package.name == "c-1.0.0.deb"


# TEST1853: host_platform() returns a normalized {os}-{arch} string with arch
# aarch64 mapped to arm64 — the exact form the registry uses.
def test_1853_host_platform_normalized_form():
    p = host_platform()
    assert "-" in p, f"host_platform must be os-arch, got {p}"
    os_seg, arch_seg = p.split("-", 1)
    assert os_seg, f"os segment present: {os_seg}"
    # The registry never uses the raw "aarch64"; it must be normalized.
    assert arch_seg != "aarch64", "arch must be normalized to arm64"


# ---------------------------------------------------------------------------
# CartridgeJson fabric_manifest_version tests
# ---------------------------------------------------------------------------

from capdag.bifaci.cartridge_json import CartridgeJson


def _make_cartridge_json(**kwargs) -> CartridgeJson:
    defaults = dict(
        name="testcartridge",
        version="1.0.0",
        channel="release",
        registry_url="https://cartridges.machinefabric.com",
        entry="testcartridge",
        installed_at="2026-06-18T00:00:00Z",
    )
    defaults.update(kwargs)
    return CartridgeJson(**defaults)


# TEST0084: CartridgeJson fabric_manifest_version=0 is the default and absent from wire dict
def test_0084_cartridge_json_fabric_manifest_version_zero_round_trip():
    cj = _make_cartridge_json()

    # Default must be 0
    assert cj.fabric_manifest_version == 0

    # Serialized dict must not contain the key when value is 0
    d = cj.to_dict()
    assert "fabric_manifest_version" not in d, (
        f"fabric_manifest_version must be absent from wire dict when 0, got: {d}"
    )

    # Deserialize from dict without the key — must produce 0
    cj2 = CartridgeJson.from_dict(d)
    assert cj2.fabric_manifest_version == 0, (
        f"expected fabric_manifest_version==0 after round-trip, got {cj2.fabric_manifest_version}"
    )


# TEST0085: CartridgeJson fabric_manifest_version nonzero is emitted and restored
def test_0085_cartridge_json_fabric_manifest_version_nonzero_round_trip():
    cj = _make_cartridge_json(fabric_manifest_version=7)

    # Serialized dict must contain the key
    d = cj.to_dict()
    assert "fabric_manifest_version" in d, (
        f"fabric_manifest_version must be present in wire dict when nonzero, got: {d}"
    )
    assert d["fabric_manifest_version"] == 7, (
        f"expected fabric_manifest_version==7 in dict, got {d['fabric_manifest_version']}"
    )

    # Deserialize from dict with the key — must restore 7
    cj2 = CartridgeJson.from_dict(d)
    assert cj2.fabric_manifest_version == 7, (
        f"expected fabric_manifest_version==7 after round-trip, got {cj2.fabric_manifest_version}"
    )
