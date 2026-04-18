"""Tests for bifaci cartridge repository models."""

from capdag.bifaci.cartridge_repo import (
    CartridgeBuild,
    CartridgeCapSummary,
    CartridgeDistributionInfo,
    CartridgeInfo,
    CartridgeRegistry,
    CartridgeRegistryEntry,
    CartridgeRegistryResponse,
    CartridgeRepo,
    CartridgeRepoError,
    CartridgeRepoServer,
    CartridgeVersionData,
)


# TEST320: Construct CartridgeInfo and verify fields
def test_320_construct_cartridge_info_and_verify_fields():
    cartridge = CartridgeInfo(
        id="testcartridge",
        name="Test Cartridge",
        version="1.0.0",
        description="A test cartridge",
        author="Test Author",
        homepage="https://example.com",
        team_id="TEAM123",
        signed_at="2026-02-07T00:00:00Z",
        min_app_version="1.0.0",
        page_url="https://example.com/cartridge",
        categories=["test"],
        tags=["testing"],
        caps=[],
        versions={
            "1.0.0": CartridgeVersionData(
                release_date="2026-02-07",
                changelog=[],
                min_app_version="1.0.0",
                builds=[
                    CartridgeBuild(
                        platform="darwin-arm64",
                        package=CartridgeDistributionInfo(
                            name="test-1.0.0.pkg",
                            sha256="abc123",
                            size=1000,
                        ),
                    )
                ],
            )
        },
        available_versions=["1.0.0"],
    )

    assert cartridge.id == "testcartridge"
    assert cartridge.name == "Test Cartridge"
    assert cartridge.version == "1.0.0"


# TEST321: Verify is_signed() method
def test_321_cartridge_info_is_signed():
    cartridge = CartridgeInfo(
        id="testcartridge",
        name="Test",
        version="1.0.0",
        team_id="TEAM123",
        signed_at="2026-02-07T00:00:00Z",
    )

    assert cartridge.is_signed()

    cartridge.team_id = ""
    assert not cartridge.is_signed()

    cartridge.team_id = "TEAM123"
    cartridge.signed_at = ""
    assert not cartridge.is_signed()


# TEST322: Verify build_for_platform() method
def test_322_cartridge_info_build_for_platform():
    cartridge = CartridgeInfo(
        id="testcartridge",
        name="Test",
        version="1.0.0",
        versions={
            "1.0.0": CartridgeVersionData(
                release_date="2026-02-07",
                changelog=[],
                min_app_version="",
                builds=[
                    CartridgeBuild(
                        platform="darwin-arm64",
                        package=CartridgeDistributionInfo(
                            name="test-1.0.0.pkg",
                            sha256="abc123",
                            size=1000,
                        ),
                    )
                ],
            )
        },
        available_versions=["1.0.0"],
    )

    build = cartridge.build_for_platform("darwin-arm64")
    assert build is not None
    assert build.package.name == "test-1.0.0.pkg"

    assert cartridge.build_for_platform("linux-x86_64") is None

    empty_cartridge = CartridgeInfo(id="empty", name="Empty", version="1.0.0")
    assert empty_cartridge.build_for_platform("darwin-arm64") is None


def _make_registry_entry(
    *,
    name: str = "Test Cartridge",
    description: str = "A test cartridge",
    author: str = "Test Author",
    page_url: str = "",
    team_id: str = "TEAM123",
    min_app_version: str = "",
    caps=None,
    categories=None,
    tags=None,
    latest_version: str = "1.0.0",
    versions=None,
):
    if caps is None:
        caps = []
    if categories is None:
        categories = []
    if tags is None:
        tags = []
    if versions is None:
        versions = {
            "1.0.0": CartridgeVersionData(
                release_date="2026-02-07",
                changelog=[],
                min_app_version="",
                builds=[
                    CartridgeBuild(
                        platform="darwin-arm64",
                        package=CartridgeDistributionInfo(
                            name="test-1.0.0.pkg",
                            sha256="abc123",
                            size=1000,
                        ),
                    )
                ],
            )
        }
    return CartridgeRegistryEntry(
        name=name,
        description=description,
        author=author,
        page_url=page_url,
        team_id=team_id,
        min_app_version=min_app_version,
        caps=caps,
        categories=categories,
        tags=tags,
        latest_version=latest_version,
        versions=versions,
    )


# TEST323: Validate registry schema version
def test_323_cartridge_repo_server_validate_registry():
    registry = CartridgeRegistry(
        schema_version="4.0",
        last_updated="2026-02-07",
        cartridges={},
    )
    CartridgeRepoServer(registry)

    old_registry = CartridgeRegistry(
        schema_version="2.0",
        last_updated="2026-02-07",
        cartridges={},
    )
    try:
        CartridgeRepoServer(old_registry)
        assert False, "expected schema validation failure"
    except CartridgeRepoError as exc:
        assert "4.0" in str(exc)


# TEST324: Transform v3 registry to flat cartridge array
def test_324_cartridge_repo_server_transform_to_array():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    categories=["test"],
                    tags=["testing"],
                    min_app_version="1.0.0",
                    versions={
                        "1.0.0": CartridgeVersionData(
                            release_date="2026-02-07",
                            changelog=["Initial release"],
                            min_app_version="1.0.0",
                            builds=[
                                CartridgeBuild(
                                    platform="darwin-arm64",
                                    package=CartridgeDistributionInfo(
                                        name="test-1.0.0.pkg",
                                        sha256="abc123",
                                        size=1000,
                                    ),
                                )
                            ],
                        )
                    },
                )
            },
        )
    )

    cartridges = server.transform_to_cartridge_array()
    assert len(cartridges) == 1
    assert cartridges[0].id == "testcartridge"
    assert cartridges[0].name == "Test Cartridge"
    assert cartridges[0].version == "1.0.0"


# TEST325: Get all cartridges via get_cartridges()
def test_325_cartridge_repo_server_get_cartridges():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={"testcartridge": _make_registry_entry()},
        )
    )
    response = server.get_cartridges()
    assert len(response.cartridges) == 1
    assert response.cartridges[0].id == "testcartridge"


# TEST326: Get cartridge by ID
def test_326_cartridge_repo_server_get_cartridge_by_id():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={"testcartridge": _make_registry_entry()},
        )
    )

    result = server.get_cartridge_by_id("testcartridge")
    assert result is not None
    assert result.id == "testcartridge"
    assert server.get_cartridge_by_id("nonexistent") is None


# TEST327: Search cartridges by text query
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
                )
            },
        )
    )

    results = server.search_cartridges("pdf")
    assert len(results) == 1
    assert results[0].id == "pdfcartridge"
    assert server.search_cartridges("nonexistent") == []


# TEST328: Filter cartridges by category
def test_328_cartridge_repo_server_get_by_category():
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "doccartridge": _make_registry_entry(
                    name="Doc Cartridge",
                    description="Process documents",
                    categories=["document"],
                )
            },
        )
    )

    results = server.get_cartridges_by_category("document")
    assert len(results) == 1
    assert results[0].id == "doccartridge"
    assert server.get_cartridges_by_category("nonexistent") == []


# TEST329: Find cartridges by cap URN
def test_329_cartridge_repo_server_get_by_cap():
    cap_urn = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "pdfcartridge": _make_registry_entry(
                    name="PDF Cartridge",
                    description="Process PDFs",
                    caps=[
                        CartridgeCapSummary(
                            urn=cap_urn,
                            title="Disbind PDF",
                            description="Extract pages",
                        )
                    ],
                )
            },
        )
    )

    results = server.get_cartridges_by_cap(cap_urn)
    assert len(results) == 1
    assert results[0].id == "pdfcartridge"
    assert server.get_cartridges_by_cap("cap:nonexistent") == []


# TEST330: CartridgeRepoClient cache update
def test_330_cartridge_repo_client_update_cache():
    repo = CartridgeRepo(3600)
    registry = CartridgeRegistryResponse(
        cartridges=[
            CartridgeInfo(
                id="testcartridge",
                name="Test Cartridge",
                version="1.0.0",
                team_id="TEAM123",
                signed_at="2026-02-07",
            )
        ]
    )

    repo.update_cache("https://example.com/cartridges", registry)

    cartridge = repo.get_cartridge("testcartridge")
    assert cartridge is not None
    assert cartridge.id == "testcartridge"


# TEST331: Get suggestions for missing cap
def test_331_cartridge_repo_client_get_suggestions():
    repo = CartridgeRepo(3600)
    cap_urn = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    registry = CartridgeRegistryResponse(
        cartridges=[
            CartridgeInfo(
                id="pdfcartridge",
                name="PDF Cartridge",
                version="1.0.0",
                description="Process PDFs",
                team_id="TEAM123",
                signed_at="2026-02-07",
                page_url="https://example.com/pdf",
                caps=[
                    CartridgeCapSummary(
                        urn=cap_urn,
                        title="Disbind PDF",
                        description="Extract pages",
                    )
                ],
            )
        ]
    )

    repo.update_cache("https://example.com/cartridges", registry)

    suggestions = repo.get_suggestions_for_cap(cap_urn)
    assert len(suggestions) == 1
    assert suggestions[0].cartridge_id == "pdfcartridge"
    assert suggestions[0].cap_urn == cap_urn


# TEST332: Get cartridge by ID from client
def test_332_cartridge_repo_client_get_cartridge():
    repo = CartridgeRepo(3600)
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[CartridgeInfo(id="testcartridge", name="Test Cartridge", version="1.0.0")]
        ),
    )

    cartridge = repo.get_cartridge("testcartridge")
    assert cartridge is not None
    assert cartridge.id == "testcartridge"
    assert repo.get_cartridge("nonexistent") is None


# TEST333: Get all available caps
def test_333_cartridge_repo_client_get_all_caps():
    repo = CartridgeRepo(3600)
    cap1 = 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"'
    cap2 = 'cap:in="media:txt;textable";op=disbind;out="media:disbound-page;textable;list"'
    repo.update_cache(
        "https://example.com/cartridges",
        CartridgeRegistryResponse(
            cartridges=[
                CartridgeInfo(
                    id="cartridge1",
                    name="Cartridge 1",
                    version="1.0.0",
                    caps=[CartridgeCapSummary(urn=cap1, title="Cap 1")],
                ),
                CartridgeInfo(
                    id="cartridge2",
                    name="Cartridge 2",
                    version="1.0.0",
                    caps=[CartridgeCapSummary(urn=cap2, title="Cap 2")],
                ),
            ]
        ),
    )

    caps = repo.get_all_available_caps()
    assert len(caps) == 2
    assert cap1 in caps
    assert cap2 in caps


# TEST334: Check if client needs sync
def test_334_cartridge_repo_client_needs_sync():
    repo = CartridgeRepo(3600)
    urls = ["https://example.com/cartridges"]

    assert repo.needs_sync(urls)

    repo.update_cache("https://example.com/cartridges", CartridgeRegistryResponse(cartridges=[]))
    assert not repo.needs_sync(urls)


# TEST335: Server creates response, client consumes it
def test_335_cartridge_repo_server_client_integration():
    cap_urn = 'cap:in="media:test";op=test;out="media:result"'
    server = CartridgeRepoServer(
        CartridgeRegistry(
            schema_version="4.0",
            last_updated="2026-02-07",
            cartridges={
                "testcartridge": _make_registry_entry(
                    page_url="https://example.com",
                    caps=[
                        CartridgeCapSummary(
                            urn=cap_urn,
                            title="Test Cap",
                            description="Test capability",
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
    assert cartridge.name == "Test Cartridge"
    assert cartridge.is_signed()
    assert cartridge.versions
    assert len(cartridge.caps) == 1
    assert cartridge.caps[0].urn == cap_urn


# TEST630: Verify CartridgeRepo creation starts with empty cartridge list
def test_630_cartridge_repo_creation():
    repo = CartridgeRepo(3600)
    assert repo.get_all_cartridges() == []


# TEST631: Verify needs_sync returns true with empty cache and non-empty URLs
def test_631_needs_sync_empty_cache():
    repo = CartridgeRepo(3600)
    assert repo.needs_sync(["https://example.com/cartridges"])


# TEST632: Verify CartridgeCapSummary deserializes null description as empty string
def test_632_deserialize_cap_summary_with_null_description():
    cap = CartridgeCapSummary.from_dict(
        {
            "urn": "media:text;llm;gen",
            "title": "Generate Text",
            "description": None,
        }
    )
    assert cap.urn == "media:text;llm;gen"
    assert cap.title == "Generate Text"
    assert cap.description == ""


# TEST633: Verify CartridgeCapSummary deserializes missing description as empty string
def test_633_deserialize_cap_summary_with_missing_description():
    cap = CartridgeCapSummary.from_dict(
        {
            "urn": "media:text;llm;gen",
            "title": "Generate Text",
        }
    )
    assert cap.description == ""


# TEST634: Verify CartridgeCapSummary deserializes present description correctly
def test_634_deserialize_cap_summary_with_present_description():
    cap = CartridgeCapSummary.from_dict(
        {
            "urn": "media:text;llm;gen",
            "title": "Generate Text",
            "description": "A real description",
        }
    )
    assert cap.description == "A real description"


# TEST635: Verify CartridgeInfo deserializes null version/description/author as empty strings
def test_635_deserialize_cartridge_info_with_null_fields():
    cartridge = CartridgeInfo.from_dict(
        {
            "id": "mlxcartridge",
            "name": "MLX Cartridge",
            "version": None,
            "description": None,
            "author": None,
            "caps": [
                {"urn": "media:text;llm;gen", "title": "Generate Text", "description": None}
            ],
            "versions": {},
        }
    )
    assert cartridge.id == "mlxcartridge"
    assert cartridge.name == "MLX Cartridge"
    assert cartridge.version == ""
    assert cartridge.description == ""
    assert cartridge.author == ""
    assert len(cartridge.caps) == 1
    assert cartridge.caps[0].description == ""


# TEST636: Verify CartridgeRegistryResponse deserializes with mixed null/present descriptions
def test_636_deserialize_registry_with_null_descriptions():
    registry = CartridgeRegistryResponse.from_dict(
        {
            "cartridges": [
                {
                    "id": "test-cartridge",
                    "name": "Test Cartridge",
                    "description": "A test cartridge",
                    "caps": [
                        {"urn": "media:text;llm;gen", "title": "Gen Text", "description": None},
                        {
                            "urn": "media:image;vision",
                            "title": "Vision",
                            "description": "Analyze images",
                        },
                    ],
                    "versions": {},
                }
            ],
            "total": 1,
            "registryVersion": "4.0",
        }
    )
    assert len(registry.cartridges) == 1
    assert registry.cartridges[0].caps[0].description == ""
    assert registry.cartridges[0].caps[1].description == "Analyze images"


# TEST637: Verify full CartridgeInfo deserialization with signature and package fields
def test_637_deserialize_full_cartridge_with_signature():
    cartridge = CartridgeInfo.from_dict(
        {
            "id": "pdfcartridge",
            "name": "pdfcartridge",
            "version": "0.81.5325",
            "description": "PDF document processor",
            "author": "https://github.com/machinefabric",
            "pageUrl": "https://github.com/machinefabric/pdfcartridge",
            "teamId": "P336JK947M",
            "signedAt": "2026-02-07T16:40:28Z",
            "minAppVersion": "1.0.0",
            "caps": [
                {
                    "urn": 'cap:in="media:pdf";op=disbind;out="media:disbound-page;textable;list"',
                    "title": "Disbind PDF",
                    "description": "Extract pages from PDF",
                }
            ],
            "categories": [],
            "tags": [],
            "versions": {
                "0.81.5325": {
                    "releaseDate": "2026-02-07T16:40:28Z",
                    "changelog": [],
                    "builds": [
                        {
                            "platform": "darwin-arm64",
                            "package": {
                                "name": "pdfcartridge-0.81.5325.pkg",
                                "sha256": "9b68724eb9220ecf01e8ed4f5f80c594fbac2239bc5bf675005ec882ecc5eba0",
                                "size": 5187485,
                            },
                        }
                    ],
                }
            },
            "availableVersions": ["0.81.5325"],
        }
    )

    assert cartridge.id == "pdfcartridge"
    assert cartridge.team_id == "P336JK947M"
    assert cartridge.signed_at == "2026-02-07T16:40:28Z"
    assert cartridge.is_signed()
