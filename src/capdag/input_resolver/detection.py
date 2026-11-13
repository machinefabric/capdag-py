"""What a file is: the one detection every host runs.

A file's extension names the file media types the fabric declares for it
(its candidates: every definition in the pinned manifest that carries the
``ext=`` file-type tag and lists the extension,
:meth:`FabricRegistry.file_media_for_extension`). Its content decides between
them, by the proved model (``capdag/formal/CapDAG/Detect.lean``, generated
into ``capdag._formal``):

- a candidate whose definition declares validation rules the content fails
  never stands;
- a candidate under a cartridge's content-inspection adapter stands only if a
  consulted cartridge claims the file as it or as something more specific
  (the adapter speaks for its whole domain);
- any other candidate stands if the content met rules it declares, or if it
  is a base type of the extension: no other candidate is more general. A
  refinement (digitized text of a ``.txt``, a JSON record of a ``.json``) is a
  claim about the content, and an unproven claim is never made.

What stands is refined by the value adapters; each line of refinement then
keeps only its most specific member. A ``list`` tag stays: it says what the
content is (a CSV file is a list of records), never how many values are in
transit, which is the planner's ``is_sequence``. What is left is what the file
is; more than one is a genuine alternative a host may offer.
:func:`primary_media` picks the one a host that cannot ask uses.

What this module does itself is the I/O the model is handed: reading the
content, evaluating each definition's rules against it, and asking the
cartridges.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Protocol, Sequence, Tuple

from tagged_urn import TaggedUrnError

from capdag import _formal as model
from capdag.fabric.registry import FabricRegistry, FabricRegistryError
from capdag.input_resolver.adapter import CartridgeAdapterInvoker, MAX_CONTENT_INSPECTION_BYTES
from capdag.input_resolver.types import (
    FabricUnavailableError,
    InputResolverError,
    InspectionFailedError,
    IoError,
    NoExtensionError,
    NotFoundError,
    PermissionDeniedError,
    UnknownExtensionError,
)
from capdag.input_resolver.value_adapter_registry import ValueAdapterRegistry
from capdag.media.spec import MediaValidation
from capdag.urn.media_urn import MediaUrn, MediaUrnError

_log = logging.getLogger("capdag.input_resolver")

_URN_ERRORS = (TaggedUrnError, MediaUrnError)


@dataclass(frozen=True)
class FileMediaCandidate:
    """One file media type a file's extension names, with the validation
    rules its definition declares."""

    urn: MediaUrn
    validation: Optional[MediaValidation]


@dataclass
class AdapterVerdict:
    """The cartridges whose content-inspection adapters cover some of a
    file's candidates, and what each of them claims the file is."""

    #: The adapter URNs of every cartridge consulted.
    owners: List[MediaUrn] = field(default_factory=list)
    #: Every media URN a consulted cartridge claimed the file as.
    claimed: List[MediaUrn] = field(default_factory=list)


class AdapterSource(Protocol):
    """Where a host's content-inspection adapters come from: which cartridges
    to consult for a file whose candidates these are, as
    ``(cartridge id, adapter URN)`` pairs. The host's
    :class:`~capdag.input_resolver.adapters.MediaAdapterRegistry` is one."""

    def adapters_for(self, candidates: Sequence[MediaUrn]) -> List[Tuple[str, MediaUrn]]:
        ...


class NoAdapters:
    """A host with no content-inspection adapters."""

    def adapters_for(self, candidates: Sequence[MediaUrn]) -> List[Tuple[str, MediaUrn]]:
        return []


class NoInvoker:
    """A host that asks no cartridge: it has none to ask."""

    async def invoke_adapter_selection(self, cartridge_id: str, file_path: Path) -> Optional[list[str]]:
        raise RuntimeError(
            f"a host with no adapters was asked to consult cartridge '{cartridge_id}'"
        )


class _Unsound(ValueError):
    """A definition, or a value adapter, the content cannot be judged by: an
    invalid validation pattern, or a refinement that is no media URN."""


@dataclass
class FileMedia:
    """What a file is."""

    path: Path
    size_bytes: int
    #: The file's extension, lowercased.
    extension: str
    #: Every file media type the fabric declares for the extension.
    candidates: List[str]
    #: What the file is: one entry, or several genuine alternatives, in the
    #: candidates' order.
    media: List[str]

    def primary(self) -> str:
        """The one media a host that cannot ask uses (:func:`primary_media`)."""
        chosen = primary_media(self.media)
        if chosen is None:
            raise AssertionError(f"the detected media of {self.path} is empty")
        return chosen


def _decoded(content: bytes) -> Optional[str]:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _number(text: str) -> Optional[float]:
    """The number ``text`` spells, as a decimal or float literal, or None."""
    if "_" in text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _meets(content: bytes, urn: MediaUrn, rules: MediaValidation) -> bool:
    """Does the content meet the rules? An invalid pattern is a defect of
    the definition and an error naming it."""
    text = _decoded(content)
    if rules.pattern is not None:
        try:
            compiled = re.compile(rules.pattern)
        except re.error as e:
            raise _Unsound(
                f"the media definition '{urn}' declares an invalid validation pattern "
                f"'{rules.pattern}': {e}"
            ) from e
        if text is None or compiled.search(text) is None:
            return False
    if rules.min_length is not None and len(content) < rules.min_length:
        return False
    if rules.max_length is not None and len(content) > rules.max_length:
        return False
    if rules.allowed_values is not None:
        if text is None or text.strip() not in rules.allowed_values:
            return False
    if rules.min is not None or rules.max is not None:
        value = _number(text.strip()) if text is not None else None
        if value is None:
            return False
        if rules.min is not None and value < rules.min:
            return False
        if rules.max is not None and value > rules.max:
            return False
    return True


def _rules_verdict(content: bytes, candidate: FileMediaCandidate) -> model.Rules:
    """What a candidate's rules say of the content, as the model takes it."""
    rules = candidate.validation
    if rules is None or rules.is_empty():
        return model.RulesUnruled()
    return model.RulesMet() if _meets(content, candidate.urn, rules) else model.RulesUnmet()


def _formal(urn: MediaUrn):
    return urn.inner().formal


def surviving_candidates(
    content: bytes,
    candidates: Sequence[FileMediaCandidate],
    verdict: AdapterVerdict,
) -> List[MediaUrn]:
    """The candidates that stand (the module's rule, decided by the model's
    ``stands``), in the candidates' order. An invalid validation pattern is a
    ValueError naming its definition."""
    modelled = [
        model.Candidate(_formal(c.urn), _rules_verdict(content, c)) for c in candidates
    ]
    owners = [_formal(u) for u in verdict.owners]
    claims = [_formal(u) for u in verdict.claimed]
    return [
        c.urn
        for c, m in zip(candidates, modelled)
        if model.stands(modelled, owners, claims, m)
    ]


def settle(
    survivors: Sequence[MediaUrn],
    value_adapters: ValueAdapterRegistry,
    content: bytes,
) -> List[str]:
    """Refine what stands through the value adapters and keep only the most
    specific member of each line of refinement (the model's
    ``mostSpecific``), in order. A refinement that is no media URN is a
    ValueError naming it."""
    text = _decoded(content) or ""
    refined: List[MediaUrn] = []
    for urn in survivors:
        urn_str = value_adapters.refine_media_urn(urn.to_string(), text)
        try:
            refined_urn = MediaUrn.from_string(urn_str)
        except _URN_ERRORS as e:
            raise _Unsound(
                f"a value adapter refined a file's media to '{urn_str}', which is no media URN: {e}"
            ) from e
        if not any(seen.is_equivalent(refined_urn) for seen in refined):
            refined.append(refined_urn)
    every = [_formal(u) for u in refined]
    return [u.to_string() for u in refined if model.most_specific(every, _formal(u))]


def primary_media(media: Sequence[str]) -> Optional[str]:
    """The one media a host that cannot ask uses: the most specific, the
    first of them on a tie (the model's ``primary``). ``None`` only for an
    empty list; a member that is no media URN is a ValueError naming it."""
    every = []
    for m in media:
        try:
            every.append(_formal(MediaUrn.from_string(m)))
        except _URN_ERRORS as e:
            raise ValueError(f"'{m}' is no media URN: {e}") from e
    position = model.primary(every)
    if position is None:
        return None
    return media[position]


def _lowercase_extension(path: Path) -> str:
    suffix = path.suffix
    return suffix[1:].lower() if suffix.startswith(".") else ""


async def _candidates_for(
    path: Path, extension: str, registry: FabricRegistry
) -> List[FileMediaCandidate]:
    """The file media types a file with this extension can be, with their
    validation rules: the fabric's answer, loaded when first asked."""
    if not extension:
        raise NoExtensionError(path)
    try:
        defs = await registry.file_media_for_extension(extension)
    except FabricRegistryError as e:
        raise FabricUnavailableError(path, str(e)) from e
    if not defs:
        raise UnknownExtensionError(path, extension)
    candidates: List[FileMediaCandidate] = []
    for d in defs:
        try:
            urn = MediaUrn.from_string(d.urn)
        except _URN_ERRORS as e:
            raise InspectionFailedError(
                path, f"the fabric's media definition '{d.urn}' has no valid URN: {e}"
            ) from e
        if d.validation is None:
            validation = None
        elif isinstance(d.validation, dict):
            validation = MediaValidation.from_dict(d.validation)
        else:
            raise InspectionFailedError(
                path,
                f"the fabric's media definition '{d.urn}' declares validation "
                f"{d.validation!r}, which is no object of rules",
            )
        candidates.append(FileMediaCandidate(urn=urn, validation=validation))
    return candidates


def _read_prefix(path: Path) -> Tuple[int, bytes]:
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            content = f.read(MAX_CONTENT_INSPECTION_BYTES)
    except FileNotFoundError as e:
        raise NotFoundError(path) from e
    except PermissionError as e:
        raise PermissionDeniedError(path) from e
    except OSError as e:
        raise IoError(path, e) from e
    return size, content


async def _consult(
    path: Path,
    candidates: Sequence[FileMediaCandidate],
    adapters: AdapterSource,
    invoker: CartridgeAdapterInvoker,
) -> AdapterVerdict:
    """Ask every cartridge whose adapter covers a candidate what the file is.
    A cartridge that declines, or fails, claims nothing; its domain stays
    covered, so its candidates fall."""
    pairs = adapters.adapters_for([c.urn for c in candidates])
    verdict = AdapterVerdict()
    asked: set[str] = set()
    for cartridge_id, adapter_urn in pairs:
        verdict.owners.append(adapter_urn)
        if cartridge_id in asked:
            continue
        asked.add(cartridge_id)
        try:
            claims = await invoker.invoke_adapter_selection(cartridge_id, path)
        except InputResolverError as e:
            _log.error(
                "a cartridge's content inspection failed: cartridge %s, adapter %s, file %s: %s",
                cartridge_id,
                adapter_urn,
                path,
                e,
            )
            continue
        if claims is None:
            continue
        for claim in claims:
            try:
                verdict.claimed.append(MediaUrn.from_string(claim))
            except _URN_ERRORS as e:
                _log.error(
                    "cartridge %s claimed a file as '%s', which is no media URN: %s",
                    cartridge_id,
                    claim,
                    e,
                )
    return verdict


async def detect_file_media(
    path: Path,
    registry: FabricRegistry,
    adapters: AdapterSource,
    invoker: CartridgeAdapterInvoker,
    value_adapters: ValueAdapterRegistry,
) -> FileMedia:
    """What a file is, by its extension and its content: the one detection
    every host runs (see the module's documentation). A host with no
    cartridges passes :class:`NoAdapters` and :class:`NoInvoker`."""
    path = Path(path)
    extension = _lowercase_extension(path)
    candidates = await _candidates_for(path, extension, registry)
    size_bytes, content = _read_prefix(path)
    verdict = await _consult(path, candidates, adapters, invoker)
    try:
        survivors = surviving_candidates(content, candidates, verdict)
        if not survivors:
            raise InspectionFailedError(
                path,
                f"its content is none of the {len(candidates)} media types the fabric "
                f"declares for .{extension}",
            )
        media = settle(survivors, value_adapters, content)
    except _Unsound as e:
        raise InspectionFailedError(path, str(e)) from e
    return FileMedia(
        path=path,
        size_bytes=size_bytes,
        extension=extension,
        candidates=[c.urn.to_string() for c in candidates],
        media=media,
    )


async def extension_media(extension: str, registry: FabricRegistry) -> List[str]:
    """What a file with this extension is before its content is read: the
    extension's base types (no candidate is more general), in the
    candidates' order — the model's rule with no rules read and no cartridge
    asked. Hosts that name a file's media from its name alone use this, and
    :func:`primary_media` when they need one."""
    path = Path(f"*.{extension}")
    candidates = await _candidates_for(path, extension.lower(), registry)
    unread = [FileMediaCandidate(urn=c.urn, validation=None) for c in candidates]
    bases = surviving_candidates(b"", unread, AdapterVerdict())
    return [u.to_string() for u in bases]
