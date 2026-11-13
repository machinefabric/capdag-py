"""A fetch the registry refused, or did not answer, is reported as itself — the
URL, the status and the manifest version — and never as a definition the
registry does not have. Run against a stub registry on a local socket.

Tests use # TEST###: comments matching the Rust implementation for
cross-tracking.
"""

import tempfile
from pathlib import Path

import httpx
import pytest

from capdag.fabric.registry import (
    FETCH_CAUSE_STATUS,
    FETCH_CAUSE_TIMED_OUT,
    FabricLocations,
    FabricRegistry,
    FetchFailedError,
    Manifest,
    NotFoundError,
    PendingError,
    RegistryConfig,
    normalize_cap_urn,
    normalize_media_urn,
    publisher_layout_charter,
)
from capdag.machine import (
    DefinitionUnavailableError,
    MachineParseError,
    UndefinedAliasError,
    parse_machine,
)
from tests.stub_registry import Answer, StubRegistry
from tests.test_machine_notation import (
    BENCHMARK,
    HEADERS,
    compare_cap,
    fetch_cap,
    mean_cap,
    publish_cap,
    score_cap,
)

MANIFEST_VERSION = 10
MEDIA = "media:refusal-probe;enc=utf8"
CAP = 'cap:in="media:refusal-probe;enc=utf8";refusal-probe;out="media:refusal-probe;enc=utf8"'
ALIAS = "measure-returns"
DIM = "refusal-probe"


def registry_at(stub: StubRegistry, timeout: float = 10.0) -> FabricRegistry:
    """A registry pinned at manifest v10 against ``stub``: its manifest names
    one cap, media def, alias and dim, and none of them is in memory."""
    config = RegistryConfig().with_anchor(stub.anchor)
    manifest = Manifest.empty(MANIFEST_VERSION)
    manifest.caps[normalize_cap_urn(CAP)] = 1
    manifest.media[normalize_media_urn(MEDIA)] = 1
    manifest.aliases[ALIAS] = 2
    manifest.dims[DIM] = 1
    return FabricRegistry(
        Path(tempfile.mkdtemp(prefix="capdag-fetch-failure-")),
        config,
        publisher_layout_charter(stub.anchor),
        httpx.AsyncClient(timeout=timeout),
        MANIFEST_VERSION,
        manifest,
    )


def cap_what() -> str:
    return f"cap '{normalize_cap_urn(CAP)}' (defver 1)"


def media_what() -> str:
    return f"media def '{normalize_media_urn(MEDIA)}' (defver 1)"


def locations_of(stub: StubRegistry) -> FabricLocations:
    return FabricLocations.from_charter(publisher_layout_charter(stub.anchor))


# TEST7167: a manifest fetch the registry refuses (403) is reported as the
# refusal — the URL, the status and the manifest version — and not as a
# manifest that is not found. A 403 is not repeated.
@pytest.mark.asyncio
async def test_7167_a_refused_manifest_fetch_is_reported_as_the_refusal(tmp_path):
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        locations = locations_of(stub)
        async with httpx.AsyncClient() as client:
            with pytest.raises(FetchFailedError) as exc_info:
                await FabricRegistry._load_or_fetch_manifest(tmp_path, client, locations, 10)
        refusal = exc_info.value
        assert (refusal.what, refusal.url, refusal.manifest_version) == (
            "manifest v10",
            locations.manifest(10),
            10,
        )
        assert (refusal.cause.kind, refusal.cause.status) == (FETCH_CAUSE_STATUS, 403)
        text = str(refusal)
        for part in ("refused", "HTTP 403 Forbidden", refusal.url, "fabric manifest v10"):
            assert part in text, f"'{part}' is missing from: {text}"
        assert "not found" not in text.lower()
        assert stub.requests_for(refusal.url) == 1, "a 403 is not repeated"


# TEST7168: a manifest the registry answers 404 for is the registry's word
# that it has no such manifest: NotFound, naming the URL and the status.
@pytest.mark.asyncio
async def test_7168_a_manifest_the_registry_does_not_have_is_not_found(tmp_path):
    async with StubRegistry(lambda path: Answer(status=404)) as stub:
        locations = locations_of(stub)
        async with httpx.AsyncClient() as client:
            with pytest.raises(NotFoundError) as exc_info:
                await FabricRegistry._load_or_fetch_manifest(tmp_path, client, locations, 10)
        assert "HTTP 404" in str(exc_info.value)
        assert locations.manifest(10) in str(exc_info.value)


# TEST7169: a refused fetch of a cap, a media def, an alias or a dim is
# reported as the refusal, each with its own URL, the status and the manifest
# version it was fetched for.
@pytest.mark.asyncio
async def test_7169_a_refused_definition_fetch_is_reported_as_the_refusal():
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        registry = registry_at(stub)
        fetches = [
            (registry.get_cap(CAP), cap_what()),
            (registry.get_media_def(MEDIA), media_what()),
            (registry.get_alias(ALIAS), f"alias '{ALIAS}' (defver 2)"),
            (registry.get_dim(DIM), f"dim '{DIM}' (defver 1)"),
        ]
        for fetch, what in fetches:
            with pytest.raises(FetchFailedError) as exc_info:
                await fetch
            refusal = exc_info.value
            assert refusal.what == what
            assert (refusal.cause.kind, refusal.cause.status) == (FETCH_CAUSE_STATUS, 403)
            assert refusal.manifest_version == MANIFEST_VERSION
            assert stub.requests_for(refusal.url) == 1, f"{what} was fetched from {refusal.url}"
            assert refusal.url in str(refusal) and "403" in str(refusal)


# TEST7170: a registry that answers 503 is reported with the 503 — never as a
# missing definition. (This mirror has no retry layer: the reference asks a
# 503 again before it reports it.)
@pytest.mark.asyncio
async def test_7170_a_registry_that_keeps_failing_is_reported_with_its_status():
    async with StubRegistry(lambda path: Answer(status=503)) as stub:
        registry = registry_at(stub)
        with pytest.raises(FetchFailedError) as exc_info:
            await registry.get_media_def(MEDIA)
        assert exc_info.value.what == media_what()
        assert (exc_info.value.cause.kind, exc_info.value.cause.status) == (FETCH_CAUSE_STATUS, 503)


# TEST7171: a registry that does not answer is reported as a fetch that timed
# out, with the URL and the manifest version.
@pytest.mark.asyncio
async def test_7171_a_registry_that_does_not_answer_is_reported_as_a_timeout():
    async with StubRegistry(lambda path: Answer(silence=True)) as stub:
        registry = registry_at(stub, timeout=0.2)
        with pytest.raises(FetchFailedError) as exc_info:
            await registry.get_media_def(MEDIA)
        timeout = exc_info.value
        assert timeout.what == media_what()
        assert timeout.cause.kind == FETCH_CAUSE_TIMED_OUT
        assert timeout.manifest_version == MANIFEST_VERSION
        assert "timed out" in str(timeout) and timeout.url in str(timeout)


# TEST7172: a definition the registry answers 404 for is the registry's word
# that it does not have it, and only that is NotFound.
@pytest.mark.asyncio
async def test_7172_a_definition_the_registry_does_not_have_is_not_found():
    async with StubRegistry(lambda path: Answer(status=404)) as stub:
        registry = registry_at(stub)
        for fetch in (registry.get_cap(CAP), registry.get_media_def(MEDIA), registry.get_alias(ALIAS)):
            with pytest.raises(NotFoundError) as exc_info:
                await fetch
            assert "HTTP 404" in str(exc_info.value) and stub.anchor in str(exc_info.value)


# TEST7173: the synchronous lookups report a refused fetch as the refusal,
# where they used to come back empty — and report a definition the manifest
# does not name as not found.
@pytest.mark.asyncio
async def test_7173_a_synchronous_lookup_reports_a_refused_fetch():
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        registry = registry_at(stub)
        for fetch in (registry.get_media_def(MEDIA), registry.get_cap(CAP)):
            with pytest.raises(FetchFailedError):
                await fetch
        with pytest.raises(FetchFailedError) as media:
            registry.get_cached_media_def(MEDIA)
        assert (media.value.what, media.value.cause.status) == (media_what(), 403)
        with pytest.raises(FetchFailedError) as cap:
            registry.get_cached_cap(CAP)
        assert (cap.value.what, cap.value.cause.status) == (cap_what(), 403)
        with pytest.raises(NotFoundError):
            registry.get_cached_media_def("media:named-by-no-manifest")


# TEST7174: a machine whose cap alias the registry refused to serve fails
# with the refusal, never as an undefined alias; an alias the registry does
# not have is still undefined.
@pytest.mark.asyncio
async def test_7174_a_refused_alias_is_reported_as_the_refusal_not_as_undefined():
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        registry = registry_at(stub)
        with pytest.raises(FetchFailedError):
            await registry.get_alias(ALIAS)
        with pytest.raises(MachineParseError) as exc_info:
            parse_machine(f"[doc -> {ALIAS} -> text]", registry)
        cause = exc_info.value.cause
        assert isinstance(cause, DefinitionUnavailableError), repr(cause)
        assert cause.urn == ALIAS
        assert isinstance(cause.error, FetchFailedError)
        assert (cause.error.what, cause.error.cause.status) == (f"alias '{ALIAS}' (defver 2)", 403)
        text = str(exc_info.value)
        for part in ("refused", "403", ALIAS, "fabric manifest v10", stub.anchor):
            assert part in text, f"'{part}' is missing from: {text}"

        with pytest.raises(MachineParseError) as undefined:
            parse_machine("[doc -> named-by-no-manifest -> text]", registry)
        assert isinstance(undefined.value.cause, UndefinedAliasError), repr(undefined.value.cause)


# TEST7175: what a fetch came to is kept: a lookup that never touches the
# network reports the refusal the fetch got, says a definition that has not
# been fetched is pending, and finds an alias the manifest does not name to be
# no alias.
@pytest.mark.asyncio
async def test_7175_a_refused_fetch_is_remembered_by_lookups_that_cannot_wait():
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        registry = registry_at(stub)
        with pytest.raises(PendingError):
            registry.resolve_alias_cached(ALIAS)
        with pytest.raises(PendingError):
            registry.get_cached_media_def(MEDIA)

        with pytest.raises(FetchFailedError):
            await registry.get_alias(ALIAS)
        with pytest.raises(FetchFailedError) as alias:
            registry.resolve_alias_cached(ALIAS)
        assert (alias.value.what, alias.value.cause.status) == (f"alias '{ALIAS}' (defver 2)", 403)
        assert registry.resolve_alias_cached("named-by-no-manifest") is None


# TEST7176: a constant whose arg's media definition is in the registry, and
# whose fetch the registry refused, is reported as the refusal — the URL, the
# status and the manifest version — not as a definition that is not available.
@pytest.mark.asyncio
async def test_7176_a_constant_whose_definition_was_refused_reports_the_refusal():
    async with StubRegistry(lambda path: Answer(status=403)) as stub:
        registry = FabricRegistry.new_for_test_with_config(RegistryConfig().with_anchor(stub.anchor))
        registry.add_caps_to_cache([compare_cap(), fetch_cap(), publish_cap(), mean_cap(), score_cap()])
        registry.manifest.media[normalize_media_urn(BENCHMARK)] = 1
        with pytest.raises(FetchFailedError):
            await registry.get_media_def(BENCHMARK)
        with pytest.raises(MachineParseError) as exc_info:
            parse_machine(HEADERS + "[(path, benchmark=[1, 2]) -> compare -> result]", registry)
        cause = exc_info.value.cause
        assert isinstance(cause, DefinitionUnavailableError), repr(cause)
        assert cause.urn == BENCHMARK
        assert isinstance(cause.error, FetchFailedError)
        assert (cause.error.cause.status, cause.error.manifest_version) == (403, 1)
        assert stub.requests_for(cause.error.url) == 1
        text = str(exc_info.value)
        assert "not available" not in text
        assert "refused" in text and "403" in text
