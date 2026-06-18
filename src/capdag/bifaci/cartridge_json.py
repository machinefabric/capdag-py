"""CartridgeJson — install-context metadata for installed cartridges.

Every installed cartridge version directory contains a ``cartridge.json`` file
that records how the cartridge was installed and where its entry point is.
This is analogous to ``provenance.json`` for run artifacts.

Layout::

    cartridges/{name}/{version}/
      cartridge.json       ← this file
      <entry_point_binary>
      <supporting_files>
"""

import hashlib
import json
import os
import stat
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class CartridgeInstallSource(str, Enum):
    """Opaque optional install-provenance metadata.

    **Not consulted for any host or engine routing decision** — kept
    around so downstream telemetry / audit tooling can record install
    provenance without growing a parallel data structure. Within the
    codebase nothing should branch on the variant; the dev-vs-not-dev
    signal the host actually uses is ``registry_url`` (``None`` ⇔ dev).
    """
    REGISTRY = "registry"
    DEV = "dev"
    BUNDLE = "bundle"
    APP_INSTALLER = "app_installer"


@dataclass
class CartridgeJson:
    """Install-context metadata stored in ``cartridge.json`` inside each cartridge
    version directory.

    `(registry_url, channel, name, version)` is the install's full
    identity. ``registry_url`` is the verbatim URL the cartridge was
    published from, or ``None`` for dev installs (the cartridge was
    built locally without ``MFR_CARTRIDGE_REGISTRY_URL``). Each
    ``(registry, channel)`` is an independent namespace; installs
    of the same id+version from different registries × channels
    coexist on disk under different top-level slug folders.
    """

    #: Cartridge name (e.g., ``"pdfcartridge"``).
    name: str
    #: Version string (e.g., ``"0.168.411"``).
    version: str
    #: Distribution channel ("release" or "nightly"). Required.
    channel: str
    #: Verbatim registry URL the cartridge was published from. ``None``
    #: ⇔ dev install. The JSON field is required-but-nullable: missing
    #: key ⇔ parse error; explicit null ⇔ dev install.
    registry_url: Optional[str]
    #: Relative path from the version directory to the executable entry point.
    #: For single-binary cartridges this is just the binary filename.
    #: For directory cartridges it may be a nested path.
    entry: str
    #: RFC3339 timestamp of when the cartridge was installed.
    installed_at: str
    #: Optional install-provenance metadata. Not consulted for any
    #: routing or attachment decision; kept around as opaque
    #: telemetry / audit hint. ``None`` (and absence in the on-disk
    #: JSON) is acceptable.
    installed_from: Optional[CartridgeInstallSource] = field(default=None)
    #: URL the package was downloaded from (empty for dev/bundle installs).
    source_url: str = field(default="")
    #: SHA256 hash of the original package (tarball or binary).
    package_sha256: str = field(default="")
    #: Size in bytes of the original package.
    package_size: int = field(default=0)
    #: Fabric registry manifest version this cartridge was built against.
    #: 0 (absent on wire) means the cartridge predates the fabric registry's
    #: versioning protocol. >= 1 means built against manifest version N.
    fabric_manifest_version: int = field(default=0)

    def __post_init__(self) -> None:
        if self.channel not in ("release", "nightly"):
            raise ValueError(
                f"CartridgeJson channel must be 'release' or 'nightly', got {self.channel!r}"
            )

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict.

        ``registry_url`` is always emitted (as JSON null for dev
        installs), never elided — the consumer's required-but-nullable
        check would reject an absent key.
        """
        d: dict = {
            "name": self.name,
            "version": self.version,
            "channel": self.channel,
            "registry_url": self.registry_url,
            "entry": self.entry,
            "installed_at": self.installed_at,
        }
        # ``installed_from`` is opaque optional metadata; we omit
        # the key when no value is set rather than emitting an
        # explicit JSON null, since a downstream reader treating
        # absent and null as the same is exactly the regime we
        # want.
        if self.installed_from is not None:
            d["installed_from"] = self.installed_from.value
        if self.source_url:
            d["source_url"] = self.source_url
        if self.package_sha256:
            d["package_sha256"] = self.package_sha256
        if self.package_size:
            d["package_size"] = self.package_size
        if self.fabric_manifest_version:
            d["fabric_manifest_version"] = self.fabric_manifest_version
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CartridgeJson":
        """Deserialize from a dict. ``channel`` and ``registry_url``
        are both required-but-``registry_url``-may-be-null. Missing
        either key surfaces as a hard error so old-schema files are
        rejected immediately."""
        if "registry_url" not in d:
            raise ValueError(
                "CartridgeJson is missing required `registry_url` field. "
                "It must be present, with value null for dev installs or "
                "a URL string for registry installs."
            )
        # ``installed_from`` is optional metadata. Missing key or
        # explicit null both deserialize to ``None``; an unknown
        # variant string still raises (Enum constructor) so a typo
        # in the on-disk file surfaces immediately rather than
        # being silently coerced.
        raw_installed_from = d.get("installed_from")
        installed_from = (
            CartridgeInstallSource(raw_installed_from)
            if raw_installed_from is not None
            else None
        )
        return cls(
            name=d["name"],
            version=d["version"],
            channel=d["channel"],
            registry_url=d["registry_url"],
            entry=d["entry"],
            installed_at=d["installed_at"],
            installed_from=installed_from,
            source_url=d.get("source_url", ""),
            package_sha256=d.get("package_sha256", ""),
            package_size=d.get("package_size", 0),
            fabric_manifest_version=d.get("fabric_manifest_version", 0),
        )

    def resolve_entry_point(self, version_dir: Path) -> Path:
        """Resolve the absolute path to the entry point binary."""
        return version_dir / self.entry

    def write_to_dir(self, version_dir: Path) -> None:
        """Write this ``cartridge.json`` to a version directory.

        Raises:
            CartridgeJsonError: If writing fails.
        """
        json_path = version_dir / "cartridge.json"
        try:
            contents = json.dumps(self.to_dict(), indent=2)
            json_path.write_text(contents, encoding="utf-8")
        except OSError as e:
            raise CartridgeJsonWriteError(json_path, e) from e


class CartridgeJsonError(Exception):
    """Base error for cartridge.json operations."""
    pass


class CartridgeJsonNotFound(CartridgeJsonError):
    def __init__(self, path: Path):
        super().__init__(f"cartridge.json not found at {path}")
        self.path = path


class CartridgeJsonReadError(CartridgeJsonError):
    def __init__(self, path: Path, cause: Exception):
        super().__init__(f"failed to read cartridge.json at {path}: {cause}")
        self.path = path
        self.cause = cause


class CartridgeJsonInvalidJson(CartridgeJsonError):
    def __init__(self, path: Path, cause: Exception):
        super().__init__(f"invalid cartridge.json at {path}: {cause}")
        self.path = path
        self.cause = cause


class CartridgeJsonEntryPointMissing(CartridgeJsonError):
    def __init__(self, path: Path, entry: str):
        super().__init__(f"cartridge.json at {path}: entry point '{entry}' does not exist")
        self.path = path
        self.entry = entry


class CartridgeJsonEntryPointNotExecutable(CartridgeJsonError):
    def __init__(self, path: Path, entry: str):
        super().__init__(f"cartridge.json at {path}: entry point '{entry}' is not executable")
        self.path = path
        self.entry = entry


class CartridgeJsonEntryPathEscape(CartridgeJsonError):
    def __init__(self, path: Path, entry: str):
        super().__init__(f"cartridge.json at {path}: entry path '{entry}' escapes version directory")
        self.path = path
        self.entry = entry


class CartridgeJsonWriteError(CartridgeJsonError):
    def __init__(self, path: Path, cause: Exception):
        super().__init__(f"failed to write cartridge.json at {path}: {cause}")
        self.path = path
        self.cause = cause


class CartridgeJsonRegistrySlugMismatch(CartridgeJsonError):
    """Three-place rule violation: the on-disk slug folder doesn't
    match the slug derived from cartridge.json:registry_url. Either
    the cartridge was hand-copied between slugs or the installer is
    buggy — either way the host refuses to attach it."""
    def __init__(
        self,
        path: Path,
        registry_url: Optional[str],
        expected_slug: str,
        actual_slug: str,
    ):
        super().__init__(
            f"cartridge.json at {path}: registry_url={registry_url!r} "
            f"hashes to slug='{expected_slug}' but the directory tree placed it under '{actual_slug}'"
        )
        self.path = path
        self.registry_url = registry_url
        self.expected_slug = expected_slug
        self.actual_slug = actual_slug


def read_cartridge_json_from_dir(version_dir: Path, expected_slug: str) -> CartridgeJson:
    """Read and validate a ``cartridge.json`` from a version directory.

    ``expected_slug`` is the on-disk registry slug folder the host
    reached the version directory through (the second-to-top-level
    folder name in the canonical
    ``{root}/{slug}/{channel}/{name}/{version}/`` layout). Passing it
    in lets the parser enforce the three-place rule (folder slug ⇔
    provenance ``registry_url``) without leaving it to every caller
    to remember.

    Validates:
    - File exists and is valid JSON
    - cartridge.json includes required ``registry_url`` field
    - ``slug_for(registry_url) == expected_slug``
    - Entry point path does not escape the version directory
    - Entry point binary exists and is executable

    Args:
        version_dir: Path to the cartridge version directory.
        expected_slug: The on-disk slug the version dir is under.

    Returns:
        Parsed :class:`CartridgeJson`.

    Raises:
        CartridgeJsonError: On any validation failure.
    """
    from capdag.bifaci.cartridge_slug import slug_for

    json_path = version_dir / "cartridge.json"

    if not json_path.exists():
        raise CartridgeJsonNotFound(json_path)

    try:
        contents = json_path.read_text(encoding="utf-8")
    except OSError as e:
        raise CartridgeJsonReadError(json_path, e) from e

    try:
        raw = json.loads(contents)
        cj = CartridgeJson.from_dict(raw)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise CartridgeJsonInvalidJson(json_path, e) from e

    # Three-place rule (places 1+2): the folder slug must match the
    # slug derived from the provenance's registry_url.
    derived_slug = slug_for(cj.registry_url)
    if derived_slug != expected_slug:
        raise CartridgeJsonRegistrySlugMismatch(
            path=json_path,
            registry_url=cj.registry_url,
            expected_slug=derived_slug,
            actual_slug=expected_slug,
        )

    # Validate entry path does not escape version directory
    entry_path = (version_dir / cj.entry).resolve()
    canonical_dir = version_dir.resolve()
    try:
        entry_path.relative_to(canonical_dir)
    except ValueError:
        raise CartridgeJsonEntryPathEscape(json_path, cj.entry)

    # Validate entry point exists
    raw_entry = version_dir / cj.entry
    if not raw_entry.exists():
        raise CartridgeJsonEntryPointMissing(json_path, cj.entry)

    # Validate entry point is executable
    mode = raw_entry.stat().st_mode
    if not (mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
        raise CartridgeJsonEntryPointNotExecutable(json_path, cj.entry)

    return cj


def hash_cartridge_directory(directory: Path) -> str:
    """Compute a deterministic SHA256 hash of a directory tree.

    Walks all files in the directory recursively, sorts them by relative path,
    then hashes each file's relative path (UTF-8 bytes) followed by its contents.
    This produces a stable identity hash regardless of filesystem ordering.

    Symbolic links are followed (their targets are hashed, not the links).
    ``cartridge.json`` itself is excluded from the hash — it contains install-time
    metadata (like ``installed_at``) that changes between installs of the same content.

    Args:
        directory: Path to the cartridge version directory.

    Returns:
        Lowercase hex-encoded SHA256 digest (64 characters).
    """
    files: list[tuple[str, Path]] = []

    for dirpath, _dirnames, filenames in os.walk(directory, followlinks=True):
        for filename in filenames:
            abs_path = Path(dirpath) / filename
            try:
                rel_path = abs_path.relative_to(directory)
            except ValueError:
                continue
            rel_str = rel_path.as_posix()
            # Exclude cartridge.json from identity hash
            if rel_str == "cartridge.json":
                continue
            files.append((rel_str, abs_path))

    files.sort(key=lambda f: f[0])

    hasher = hashlib.sha256()
    for rel_str, abs_path in files:
        hasher.update(rel_str.encode("utf-8"))
        hasher.update(abs_path.read_bytes())

    return hasher.hexdigest()
