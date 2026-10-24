"""Registry charters: what makes a URL a MachineFabric registry. Mirrors Rust
``bifaci/charter.rs``.

A registry — of cartridges, of fabric definitions, or of app releases — is
named by its ANCHOR, which may be any URL. The one convention anywhere is that
``<anchor>/charter.json`` and ``<anchor>/charter.json.sig`` exist. Everything
else is read from the charter, never derived from the shape of a URL: the
registry's slug (its folder on disk), its kind, the environment its contents
are signed under, the locations of its manifests, and for a cartridge registry
the fabric its caps resolve against.

What this module does and does not do
-------------------------------------

It reads a charter and holds it to its shape, to the folder it is stored in
and to the anchor its cartridges record. It does NOT verify the signature: this
mirror carries no chain verification (``release_cert.rs`` and ``charter.rs`` in
the Rust library are the only implementation of it, checked against the
MachineFabric roots every Rust build bakes), and a mirror that stubbed one
would be worse than a mirror that has none. What this reads is what the Rust
host, or the installer that wrote it, already verified.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Mapping, Optional, Tuple

if TYPE_CHECKING:
    import httpx

#: The format discriminator inside every charter body.
CHARTER_FORMAT = "machinefabric-registry-charter/1"

#: The format discriminator of a charter's signature envelope — distinct from
#: the manifest envelope's, so a prod-signed manifest can never be presented as
#: a charter.
CHARTER_SIG_FORMAT = "machinefabric-charter-sig/1"

#: The charter's file name under its anchor and in a registry's folder.
CHARTER_FILE = "charter.json"

#: The charter signature's file name.
CHARTER_SIG_FILE = "charter.json.sig"

#: The label a charter's certificate carries: charters are signed by prod for
#: every environment.
CHARTER_SIGNING_ENVIRONMENT = "prod"

#: The reserved folder name of cartridges built with no registry. No charter
#: may claim it.
DEV_SLUG = "dev"


class RegistryKind(str, Enum):
    """One of the three kinds of registry."""

    CARTRIDGES = "cartridges"
    FABRIC = "fabric"
    RELEASES = "releases"


#: Per kind, the locations a charter must declare, each with the placeholders
#: its template must use — all of them and no others.
_REGISTRY_LOCATIONS: Dict[RegistryKind, Dict[str, Tuple[str, ...]]] = {
    RegistryKind.CARTRIDGES: {"manifest": ("registry_version",)},
    RegistryKind.FABRIC: {
        "manifest": ("manifest_version",),
        "latest": (),
        "definition": ("kind", "urn_hash", "version"),
    },
    RegistryKind.RELEASES: {"manifest": ("app_id",)},
}

_FIELDS = (
    "format",
    "anchor",
    "kind",
    "slug",
    "environment",
    "experiment",
    "locations",
    "fabric",
    "issued_at",
    "not_after",
)
_REQUIRED_FIELDS = ("format", "anchor", "kind", "slug", "environment", "locations", "issued_at", "not_after")
_SLUG = re.compile(r"[a-z0-9][a-z0-9.-]{0,62}")
_EXPERIMENT_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
_LABEL = re.compile(r"[a-z0-9-]+")


class CharterError(ValueError):
    """A charter that does not read, or is not the one asked for."""


@dataclass
class Charter:
    """A charter body, as signed."""

    format: str
    #: The URL this registry is named by — the registry_url every cartridge
    #: from it records.
    anchor: str
    kind: RegistryKind
    #: The registry's name on disk. Never "dev".
    slug: str
    #: The label this registry's CONTENTS are signed under.
    environment: str
    #: Templates, by name.
    locations: Dict[str, str]
    issued_at: int
    #: When the charter is void; None: valid while the key that signed it is
    #: trusted.
    not_after: Optional[int]
    #: The lab experiment this registry belongs to, if any.
    experiment: Optional[str] = None
    #: For a cartridge registry, the anchor of the fabric registry its caps
    #: resolve against.
    fabric: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: Mapping) -> "Charter":
        if not isinstance(raw, Mapping):
            raise CharterError("the charter is not a charter document: not a JSON object")
        unknown = sorted(set(raw) - set(_FIELDS))
        if unknown:
            raise CharterError(f"the charter is not a charter document: unknown field '{unknown[0]}'")
        missing = [name for name in _REQUIRED_FIELDS if name not in raw]
        if missing:
            raise CharterError(f"the charter is not a charter document: no '{missing[0]}'")
        try:
            kind = RegistryKind(raw["kind"])
        except ValueError:
            raise CharterError(f"the charter is not a charter document: kind '{raw['kind']}' is not a kind of registry")
        locations = raw["locations"]
        if not isinstance(locations, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in locations.items()
        ):
            raise CharterError("the charter is not a charter document: locations are not templates by name")
        for name in ("format", "anchor", "slug", "environment"):
            if not isinstance(raw[name], str):
                raise CharterError(f"the charter is not a charter document: '{name}' is not a string")
        for name in ("experiment", "fabric"):
            if raw.get(name) is not None and not isinstance(raw[name], str):
                raise CharterError(f"the charter is not a charter document: '{name}' is not a string")
        for name in ("issued_at", "not_after"):
            value = raw[name]
            if value is None and name == "not_after":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CharterError(f"the charter is not a charter document: '{name}' is not a time")
        return cls(
            format=raw["format"],
            anchor=raw["anchor"],
            kind=kind,
            slug=raw["slug"],
            environment=raw["environment"],
            locations=dict(locations),
            issued_at=raw["issued_at"],
            not_after=raw["not_after"],
            experiment=raw.get("experiment"),
            fabric=raw.get("fabric"),
        )

    def to_dict(self) -> dict:
        out = {
            "format": self.format,
            "anchor": self.anchor,
            "kind": self.kind.value,
            "slug": self.slug,
            "environment": self.environment,
        }
        if self.experiment is not None:
            out["experiment"] = self.experiment
        out["locations"] = dict(self.locations)
        if self.fabric is not None:
            out["fabric"] = self.fabric
        out["issued_at"] = self.issued_at
        out["not_after"] = self.not_after
        return out

    def validate(self) -> None:
        """Hold the charter to the shape every charter must have, whoever
        signed it."""
        if self.format != CHARTER_FORMAT:
            raise CharterError(f"format '{self.format}' is not '{CHARTER_FORMAT}'")
        _check_https("anchor", self.anchor)
        if self.anchor.endswith("/"):
            raise CharterError(f"anchor '{self.anchor}' ends with '/'")
        if not is_slug(self.slug):
            raise CharterError(
                f"slug '{self.slug}' is not a registry slug ([a-z0-9][a-z0-9.-]{{0,62}}, not '{DEV_SLUG}')"
            )
        if not _LABEL.fullmatch(self.environment):
            raise CharterError(f"environment '{self.environment}' is not a label ([a-z0-9-]+)")
        if self.experiment is not None and not is_experiment_id(self.experiment):
            raise CharterError(
                f"experiment '{self.experiment}' is not an experiment id ([a-z0-9][a-z0-9-]{{0,39}})"
            )
        required = _REGISTRY_LOCATIONS[RegistryKind(self.kind)]
        for name in self.locations:
            if name not in required:
                raise CharterError(f"location '{name}' is not one a {self.kind.value} registry has")
        for name in sorted(required):
            template = self.locations.get(name)
            if template is None:
                raise CharterError(f"a {self.kind.value} registry must declare location '{name}'")
            _check_https(f"location '{name}'", template)
            used = _placeholders_in(template)
            for placeholder in used:
                if placeholder not in required[name]:
                    raise CharterError(f"location '{name}' uses '{{{placeholder}}}', which it does not take")
            for placeholder in required[name]:
                if placeholder not in used:
                    raise CharterError(f"location '{name}' must use '{{{placeholder}}}'")
        if self.kind is RegistryKind.CARTRIDGES:
            if self.fabric is None:
                raise CharterError("a cartridges registry must name its fabric")
            _check_https("fabric", self.fabric)
            if self.fabric.endswith("/"):
                raise CharterError(f"fabric '{self.fabric}' ends with '/'")
        elif self.fabric is not None:
            raise CharterError(
                f"only a cartridges registry names a fabric, and this is a {self.kind.value} registry"
            )
        if self.not_after is not None and self.not_after <= self.issued_at:
            raise CharterError(f"not_after {self.not_after} is not after issued_at {self.issued_at}")

    def location(self, name: str, values: Mapping[str, str]) -> str:
        """One location with its placeholders filled. Every placeholder the
        template uses must be given, and nothing else may be."""
        template = self.locations.get(name)
        if template is None:
            raise CharterError(f"the {self.kind.value} registry at {self.anchor} has no location '{name}'")
        used = _placeholders_in(template)
        for key in values:
            if key not in used:
                raise CharterError(f"location '{name}' does not take '{key}'")
        out = template
        for placeholder in used:
            if placeholder not in values:
                raise CharterError(f"location '{name}' needs '{placeholder}'")
            out = out.replace("{" + placeholder + "}", str(values[placeholder]))
        return out


def parse_charter(body: bytes) -> Charter:
    """Read a charter's bytes: the format first, then the shape."""
    try:
        raw = json.loads(body)
    except (ValueError, UnicodeDecodeError) as e:
        raise CharterError(f"the charter is not a charter document: {e}") from e
    if not isinstance(raw, dict) or "format" not in raw:
        raise CharterError("the charter is not a charter document: no format")
    if raw["format"] != CHARTER_FORMAT:
        raise CharterError(f"the charter declares format '{raw['format']}' (this build reads '{CHARTER_FORMAT}')")
    charter = Charter.from_dict(raw)
    try:
        charter.validate()
    except CharterError as e:
        raise CharterError(f"the charter is not a charter document: {e}") from e
    return charter


def is_slug(s: str) -> bool:
    """Whether ``s`` can be a registry slug: ``[a-z0-9][a-z0-9.-]{0,62}``, and
    not the reserved "dev"."""
    return s != DEV_SLUG and _SLUG.fullmatch(s) is not None


def is_experiment_id(s: str) -> bool:
    """Whether ``s`` can be a lab experiment id: ``[a-z0-9][a-z0-9-]{0,39}``."""
    return _EXPERIMENT_ID.fullmatch(s) is not None


def _check_https(what: str, url: str) -> None:
    scheme, sep, rest = url.partition("://")
    if not sep or scheme != "https" or not rest or rest.startswith("/"):
        raise CharterError(f"{what} '{url}' is not an https URL")
    if "?" in url or "#" in url:
        raise CharterError(f"{what} '{url}' carries a query or fragment")


def _placeholders_in(template: str) -> List[str]:
    """The {name} placeholders a template uses, in order of first use. A stray
    brace is an error rather than literal text."""
    out: List[str] = []
    rest = template
    while True:
        positions = [i for i in (rest.find("{"), rest.find("}")) if i >= 0]
        if not positions:
            return out
        at = min(positions)
        if rest[at] == "}":
            raise CharterError(f"'{template}' has an unmatched '}}'")
        after = rest[at + 1 :]
        end = after.find("}")
        if end < 0:
            raise CharterError(f"'{template}' has an unclosed '{{'")
        name = after[:end]
        if not re.fullmatch(r"[a-z_]+", name):
            raise CharterError(f"'{template}' has a placeholder '{{{name}}}' that is not a name")
        if name not in out:
            out.append(name)
        rest = after[end + 1 :]


def read_stored_charter(folder: Path, kind: RegistryKind) -> Charter:
    """Read the charter stored in a registry's folder, hold it to its shape and
    its kind, and require the folder to be named for it. The signature beside
    it is the Rust host's to verify (see the module docstring)."""
    folder = Path(folder)
    path = folder / CHARTER_FILE
    try:
        body = path.read_bytes()
    except OSError as e:
        raise CharterError(f"cannot read {path}: {e}") from e
    if not (folder / CHARTER_SIG_FILE).is_file():
        raise CharterError(f"the charter in {folder} has no signature beside it")
    charter = parse_charter(body)
    if charter.kind is not RegistryKind(kind):
        raise CharterError(f"the charter is for a {charter.kind.value} registry, not a {RegistryKind(kind).value} one")
    if folder.name != charter.slug:
        raise CharterError(
            f"the charter for '{charter.anchor}' names slug '{charter.slug}', "
            f"but it is stored in a folder named '{folder.name}'"
        )
    return charter


def stored_charter_for(root: Path, anchor: str, kind: RegistryKind) -> Optional[Tuple[Path, Charter]]:
    """Among the registry folders under ``root``, the one whose stored charter
    is of ``kind`` and for ``anchor``: its folder and charter. A folder whose
    charter does not read is passed over."""
    root = Path(root)
    if not root.is_dir():
        return None
    for folder in sorted(root.iterdir()):
        if not (folder / CHARTER_FILE).is_file():
            continue
        try:
            charter = read_stored_charter(folder, kind)
        except CharterError as e:
            print(f"[WARN] the charter stored in {folder} is not used: {e}", file=sys.stderr)
            continue
        if charter.anchor == anchor:
            return folder, charter
    return None


@dataclass(frozen=True)
class RegistryFolder:
    """What one top-level folder of a cartridge tree holds: the cartridges
    built with no registry, or a chartered registry's — named by the charter
    stored in it, never by its own name."""

    #: None for the reserved dev folder.
    charter: Optional[Charter] = None

    @staticmethod
    def open(folder: Path) -> "RegistryFolder":
        """Open a top-level folder: "dev" by its reserved name, any other by
        the cartridges charter stored in it."""
        if Path(folder).name == DEV_SLUG:
            return RegistryFolder()
        return RegistryFolder(charter=read_stored_charter(Path(folder), RegistryKind.CARTRIDGES))

    @property
    def slug(self) -> str:
        """The folder's name."""
        return DEV_SLUG if self.charter is None else self.charter.slug

    @property
    def anchor(self) -> Optional[str]:
        """The anchor every cartridge in the folder must record: None for dev."""
        return None if self.charter is None else self.charter.anchor


@dataclass
class FetchedCharter:
    """A charter as its anchor serves it: the exact bytes of the body and of
    its signature, and the body read."""

    charter: Charter
    body: bytes
    signature: bytes


class CharterFetchError(Exception):
    """Why fetching a charter from its anchor failed."""

    UNREACHABLE = "unreachable"
    #: Nothing is at ``<anchor>/charter.json`` — the URL is not a MachineFabric
    #: registry.
    UNCHARTERED = "unchartered"
    HTTP = "http"
    #: A charter is there, and it is not this registry's.
    REFUSED = "refused"

    def __init__(self, kind: str, anchor: str, url: str = "", status: Optional[int] = None, cause: object = None):
        self.kind = kind
        self.anchor = anchor
        self.url = url
        self.status = status
        self.cause = cause
        if kind == self.UNCHARTERED:
            message = f"{anchor} has no charter ({url} answered 404) — it is not a MachineFabric registry"
        elif kind == self.HTTP:
            message = f"{url} answered HTTP {status}"
        elif kind == self.REFUSED:
            message = f"the charter of {anchor} was refused: {cause}"
        else:
            message = f"cannot reach {url}: {cause}"
        super().__init__(message)


async def fetch_charter(client: "httpx.AsyncClient", anchor: str, kind: RegistryKind) -> FetchedCharter:
    """Fetch ``<anchor>/charter.json`` and its signature, read the body and
    hold it to the anchor and kind asked. The signature is carried for the Rust
    host to verify (see the module docstring).

    The two are fetched with one cache-bust token, because the signature holds
    only over a coherent pair and a CDN may cache them from different issues.
    """
    cache_bust = int(time.time() * 1000)
    body = await _get_charter_file(client, anchor, f"{anchor}/{CHARTER_FILE}", cache_bust)
    signature = await _get_charter_file(client, anchor, f"{anchor}/{CHARTER_SIG_FILE}", cache_bust)
    try:
        charter = parse_charter(body)
    except CharterError as e:
        raise CharterFetchError(CharterFetchError.REFUSED, anchor, cause=e) from e
    if charter.anchor != anchor:
        raise CharterFetchError(CharterFetchError.REFUSED, anchor, cause=f"it is the charter of {charter.anchor}")
    if charter.kind is not RegistryKind(kind):
        raise CharterFetchError(
            CharterFetchError.REFUSED,
            anchor,
            cause=f"it charters a {charter.kind.value} registry, not a {RegistryKind(kind).value} one",
        )
    return FetchedCharter(charter=charter, body=body, signature=signature)


async def _get_charter_file(client: "httpx.AsyncClient", anchor: str, url: str, cache_bust: int) -> bytes:
    import httpx

    try:
        response = await client.get(f"{url}?cb={cache_bust}")
    except httpx.HTTPError as e:
        raise CharterFetchError(CharterFetchError.UNREACHABLE, anchor, url=url, cause=e) from e
    if response.status_code == 404:
        raise CharterFetchError(CharterFetchError.UNCHARTERED, anchor, url=url)
    if not 200 <= response.status_code <= 299:
        raise CharterFetchError(CharterFetchError.HTTP, anchor, url=url, status=response.status_code)
    return response.content


def store_charter(fetched: FetchedCharter, folder: Path) -> None:
    """Write a fetched charter and its signature, byte for byte, into
    ``folder`` — which must be named for the charter's slug, as
    :func:`read_stored_charter` requires of every folder it reads."""
    folder = Path(folder)
    if folder.name != fetched.charter.slug:
        raise CharterError(
            f"the charter of {fetched.charter.anchor} names slug '{fetched.charter.slug}' "
            f"and cannot be stored in a folder named '{folder.name}'"
        )
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomic(folder / CHARTER_FILE, fetched.body)
    _write_atomic(folder / CHARTER_SIG_FILE, fetched.signature)


def _write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)
