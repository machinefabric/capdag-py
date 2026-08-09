"""Cartridge-development support for the capdag CLI.

This package backs three developer commands and the local-manifest run path:

- :func:`scaffold_cartridge` — ``capdag new <name> --<language>``: write a
  fresh, runnable cartridge project (one custom cap, one Op that peer-calls a
  model, one manifest) into a new directory, in any language the vendored
  canonical stubs cover. The stubs are the SAME bytes in every capdag
  implementation (see :mod:`capdag.dev.stubs_generated`), so the project you get
  does not depend on which capdag binary you ran.
- :func:`stage_dev_cartridge` — ``capdag dev-install <project-dir>``: read the
  project's manifest, then copy it under the per-user cartridge root's reserved
  ``dev`` slug so the capdag host discovers it. Re-running overwrites the same
  version directory — the update step of the edit/reinstall loop.
- :func:`find_dev_cap_by_alias` + :func:`check_no_fabric_conflict` — the
  local-manifest run path: when ``capdag <alias>`` names a cap the fabric does
  NOT define, a locally dev-installed cartridge's OWN manifest answers it, as
  long as the cap does not conflict with the fabric. A dev cap never needs to be
  published to be developed and run locally.

The on-disk layout mirrors every other host exactly:
``{user_cartridge_dir}/dev/v{registry_version}/{channel}/{name}/{version}/``

Mirrors the reference implementation in ``capdag/src/dev.rs``.
"""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from capdag.bifaci.cartridge_json import (
    CartridgeInstallSource,
    CartridgeJson,
    install_timestamp_now,
    read_cartridge_json_from_dir,
)
from capdag.bifaci.cartridge_slug import DEV_SLUG
from capdag.bifaci.manifest import CapManifest
from capdag.cap.definition import Cap
from capdag.urn.cap_urn import CapUrn

from .stubs_generated import (
    STUB_CONTRACT_VERSION,
    STUB_LANGUAGES,
    STUB_PLACEHOLDER,
    StubFile,
    StubLanguage,
)

__all__ = [
    "DevError",
    "InvalidNameError",
    "AlreadyExistsError",
    "NoEntryError",
    "AmbiguousEntryError",
    "NotDevError",
    "FabricConflictError",
    "STUB_CONTRACT_VERSION",
    "STUB_LANGUAGES",
    "STUB_PLACEHOLDER",
    "StubFile",
    "StubLanguage",
    "languages",
    "language",
    "language_flag_list",
    "entry_for",
    "valid_cartridge_name",
    "scaffold_cartridge",
    "project_entry",
    "read_entry_manifest",
    "dev_version_dir",
    "stage_dev_cartridge",
    "find_dev_cap_by_alias",
    "check_no_fabric_conflict",
]


# ---------------------------------------------------------------------------
# Errors — each names the file, entry or conflicting alias so a developer can
# act on it without reproducing the failure.
# ---------------------------------------------------------------------------


class DevError(Exception):
    """Base for every cartridge-development failure."""


class InvalidNameError(DevError):
    """A project name that is not path-safe."""

    def __init__(self, name: str):
        super().__init__(
            f"invalid cartridge name {name!r}: use a lowercase, path-safe name matching "
            "[a-z0-9] with '-' or '_' separators (e.g. sentiment-tagger)"
        )
        self.name = name


class AlreadyExistsError(DevError):
    """A scaffold target that already exists. Scaffolding never overwrites."""

    def __init__(self, path: Path):
        super().__init__(f"'{path}' already exists — pick a new name or remove it first")
        self.path = path


class NoEntryError(DevError):
    """A project with no cartridge entry for any known language."""

    def __init__(self, project: Path):
        super().__init__(
            f"no cartridge entry found in '{project}'. Looked for "
            f"{_entry_candidates_description(project)}. A compiled cartridge must be BUILT "
            "before it is installed — the host launches the binary, not the sources. "
            "Create the project with `capdag new`."
        )
        self.project = project


class AmbiguousEntryError(DevError):
    """A project carrying more than one language's entry."""

    def __init__(self, project: Path, found: List[Path]):
        listed = ", ".join(str(p) for p in found)
        super().__init__(
            f"'{project}' contains more than one cartridge entry ({listed}) — capdag cannot "
            "tell which one to install. A project is ONE cartridge; remove the build outputs "
            "of the language you are not developing."
        )
        self.project = project
        self.found = found


class NotDevError(DevError):
    """A manifest that declares a registry URL, i.e. a published cartridge."""

    def __init__(self, registry_url: str):
        super().__init__(
            f"this project's manifest declares registry_url {registry_url!r}, so it is a "
            "PUBLISHED cartridge, not a dev one. `dev-install` stages only dev cartridges "
            "(registry_url null)."
        )
        self.registry_url = registry_url


class FabricConflictError(DevError):
    """A dev cap whose alias already means a different cap upstream."""

    def __init__(self, alias: str, dev_urn: str, fabric_urn: str):
        super().__init__(
            f"the dev cap {dev_urn!r} claims alias {alias!r}, which the fabric already "
            f"resolves to {fabric_urn!r}. Rename the dev cap's alias — a dev cartridge may "
            "not shadow a published cap."
        )
        self.alias = alias
        self.dev_urn = dev_urn
        self.fabric_urn = fabric_urn


# ---------------------------------------------------------------------------
# The vendored stub contract.
# ---------------------------------------------------------------------------


def languages() -> List[StubLanguage]:
    """Every language ``capdag new`` can scaffold, in contract order.

    A mirror that offered a subset would silently make ``capdag new --rust``
    mean different things depending on which capdag binary you happened to run.
    """
    return STUB_LANGUAGES


def language(selector: str) -> Optional[StubLanguage]:
    """Look a language up by its id (``python``) or its flag (``--python``).

    Returns ``None`` for anything else; the caller turns that into an error that
    lists what IS available, which is the only useful thing to say.
    """
    for candidate in STUB_LANGUAGES:
        if candidate.id == selector or candidate.flag == selector:
            return candidate
    return None


def language_flag_list() -> str:
    """The scaffoldable flags, for usage and error messages.

    Built from the contract so a newly vendored language appears everywhere at
    once rather than in whichever message someone remembered to update.
    """
    return " | ".join(candidate.flag for candidate in STUB_LANGUAGES)


def _render(template: str, name: str) -> str:
    """Substitute the project name into a stub's text.

    The placeholder appears in file CONTENTS, in destination PATHS, and in the
    entry — a compiled cartridge's binary is named after the project — so one
    function serves all three rather than three call sites each remembering.
    """
    return template.replace(STUB_PLACEHOLDER, name)


def entry_for(lang: StubLanguage, name: str) -> str:
    """The executable the host launches, relative to the project directory."""
    return _render(lang.entry, name)


def valid_cartridge_name(name: str) -> bool:
    """Whether a name is safe as a directory, a cap alias and a media-URN
    fragment all at once."""
    if not name:
        return False
    first = name[0]
    if not (first.islower() and first.isascii() and first.isalpha()) and not (
        first.isascii() and first.isdigit()
    ):
        return False
    for ch in name:
        is_lower = ch.isascii() and ch.isalpha() and ch.islower()
        is_digit = ch.isascii() and ch.isdigit()
        if not is_lower and not is_digit and ch not in "-_":
            return False
    return True


# ---------------------------------------------------------------------------
# new — scaffold a project.
# ---------------------------------------------------------------------------


def scaffold_cartridge(name: str, lang: StubLanguage, parent_dir: Path) -> Path:
    """Write a new cartridge project named ``name`` under ``parent_dir``.

    Fails hard if the name is not path-safe or the target already exists — never
    overwrites existing work, and never half-writes: a failure part-way names
    the exact file it could not write.
    """
    if not valid_cartridge_name(name):
        raise InvalidNameError(name)
    parent_dir = Path(parent_dir)
    project_dir = parent_dir / name
    if project_dir.exists():
        raise AlreadyExistsError(project_dir)
    project_dir.mkdir(parents=True)

    for file in lang.files:
        dest = project_dir / _render(file.dest, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_render(file.contents, name), encoding="utf-8")
        if file.executable:
            dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return project_dir


# ---------------------------------------------------------------------------
# Entry discovery.
# ---------------------------------------------------------------------------


def _project_name(project_dir: Path) -> str:
    """The name a scaffolded directory carries: its own directory name.

    ``capdag new <name>`` creates ``<parent>/<name>`` and every rendered path is
    seeded from that name, so the directory IS the name. Reading it back is how
    dev-install knows what a compiled entry is called without being told.
    """
    return Path(project_dir).resolve().name


def _entry_candidates_description(project_dir: Path) -> str:
    """Name every entry path that WOULD have been accepted, turning "no entry
    found" into an instruction."""
    name = _project_name(project_dir)
    return ", ".join(f"{entry_for(l, name)} ({l.display})" for l in STUB_LANGUAGES)


def project_entry(project_dir: Path) -> Path:
    """The project's entry, discovered across every scaffoldable language.

    A project is ONE cartridge, so finding two entries is an error rather than a
    silent pick: installing whichever language happened to sort first would be a
    coin flip the developer never sees.
    """
    project_dir = Path(project_dir)
    name = _project_name(project_dir)
    found = [
        project_dir / entry_for(l, name)
        for l in STUB_LANGUAGES
        if (project_dir / entry_for(l, name)).is_file()
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise NoEntryError(project_dir)
    raise AmbiguousEntryError(project_dir, found)


# ---------------------------------------------------------------------------
# Reading a project's manifest.
# ---------------------------------------------------------------------------


def read_entry_manifest(entry: Path) -> CapManifest:
    """Run a cartridge entry's ``manifest`` subcommand and parse the printed
    ``CapManifest`` JSON.

    Every cartridge in every language prints the same wire shape, which is what
    lets capdag read a Rust project's manifest from Python without knowing or
    caring which language wrote it.
    """
    entry = Path(entry)
    try:
        completed = subprocess.run(
            [str(entry), "manifest"], capture_output=True, check=False
        )
    except OSError as error:
        raise DevError(
            f"could not run the cartridge entry '{entry}' to read its manifest: {error}. "
            "Make sure it is executable and its dependencies are importable."
        ) from error
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        raise DevError(
            f"the cartridge entry '{entry}' exited {completed.returncode} when asked for "
            f"its manifest: {stderr}"
        )
    try:
        return CapManifest.from_dict(json.loads(completed.stdout))
    except (ValueError, KeyError, TypeError) as error:
        raise DevError(
            f"the cartridge entry '{entry}' printed a manifest capdag cannot parse: {error}"
        ) from error


# ---------------------------------------------------------------------------
# dev-install — stage a project under the `dev` slug.
# ---------------------------------------------------------------------------


def dev_version_dir(
    user_cartridge_dir: Path, registry_version: int, channel: str, name: str, version: str
) -> Path:
    """``dev/v{registry_version}/{channel}/{name}/{version}/`` under the root."""
    return Path(user_cartridge_dir) / DEV_SLUG / f"v{registry_version}" / channel / name / version


#: Project entries the install copy skips.
#:
#: Developer scratch, plus build trees: a compiled cartridge's intermediates are
#: gigabytes of object files and dependency sources the host never reads — only
#: the linked entry matters, and :func:`stage_dev_cartridge` copies that
#: explicitly after the walk.
_IGNORED_PROJECT_ENTRIES = frozenset(
    {
        ".venv",
        "__pycache__",
        ".git",
        ".pytest_cache",
        "cartridge.json",
        "target",
        ".build",
        ".swiftpm",
        "node_modules",
    }
)


def _is_ignored_project_entry(name: str) -> bool:
    return name in _IGNORED_PROJECT_ENTRIES or name.endswith(".pyc")


def _copy_project_tree(src: Path, dst: Path) -> None:
    for entry in sorted(src.iterdir(), key=lambda p: p.name):
        if _is_ignored_project_entry(entry.name):
            continue
        target = dst / entry.name
        if entry.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            _copy_project_tree(entry, target)
        else:
            shutil.copy2(entry, target)


def stage_dev_cartridge(
    project_dir: Path,
    manifest: CapManifest,
    user_cartridge_dir: Path,
    registry_version: int,
    fabric_manifest_version: int,
) -> Path:
    """Copy a project under the ``dev`` slug and write its ``cartridge.json``.

    ``manifest`` must already have been read from the project (via
    :func:`read_entry_manifest`) and is verified here to be a dev cartridge
    (``registry_url`` null); this staging step does not itself re-run the entry.
    """
    if manifest.registry_url is not None:
        raise NotDevError(manifest.registry_url)

    project_dir = Path(project_dir)
    version_dir = dev_version_dir(
        user_cartridge_dir, registry_version, manifest.channel, manifest.name, manifest.version
    )

    # The entry is discovered in the PROJECT, then recorded relative to the
    # install — a compiled cartridge's entry lives under its build directory
    # (target/release/<name>), and the two are the same relative path.
    entry_path = project_entry(project_dir)
    relative_entry = str(entry_path.relative_to(project_dir))

    # Update semantics: replace the version directory wholesale so a removed
    # file in the project does not linger in a stale install.
    if version_dir.exists():
        shutil.rmtree(version_dir)
    version_dir.mkdir(parents=True)

    _copy_project_tree(project_dir, version_dir)

    # The entry is copied explicitly because a compiled one lives INSIDE a build
    # tree the walk above deliberately skips. Doing it here rather than
    # exempting the whole tree keeps the install to the sources plus the one
    # binary the host actually launches.
    installed_entry = version_dir / relative_entry
    if not installed_entry.is_file():
        installed_entry.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(entry_path, installed_entry)
    installed_entry.chmod(
        installed_entry.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )

    CartridgeJson(
        name=manifest.name,
        version=manifest.version,
        channel=manifest.channel,
        registry_url=None,
        entry=relative_entry,
        installed_at=install_timestamp_now(),
        installed_from=CartridgeInstallSource.DEV,
        fabric_manifest_version=fabric_manifest_version,
    ).write_to_dir(version_dir)

    return version_dir


# ---------------------------------------------------------------------------
# The local-manifest run path.
# ---------------------------------------------------------------------------


def find_dev_cap_by_alias(
    user_cartridge_dir: Path, registry_version: int, alias: str
) -> Optional[Tuple[Cap, Path]]:
    """Search every dev-installed cartridge's own manifest for a cap carrying
    ``alias``, returning ``(cap, version_dir)``.

    Returns ``None`` when no dev cartridge claims the alias — an ordinary
    outcome, not an error: the caller then reports the alias as unknown to both
    the fabric and the dev slug.
    """
    dev_root = Path(user_cartridge_dir) / DEV_SLUG / f"v{registry_version}"
    for version_dir in _walk_version_dirs(dev_root):
        # A version directory with no cartridge.json is not an install — it is a
        # leftover directory. Skipping it is not a fallback: the reader
        # distinguishes "absent" from "unreadable", and only the latter is worth
        # stopping the whole lookup for.
        if not (version_dir / "cartridge.json").is_file():
            continue
        cj = read_cartridge_json_from_dir(version_dir, DEV_SLUG)
        manifest = read_entry_manifest(cj.resolve_entry_point(version_dir))
        for group in manifest.cap_groups:
            for cap in group.caps:
                if alias in cap.get_aliases():
                    return cap, version_dir
    return None


def _walk_version_dirs(dev_root: Path) -> List[Path]:
    """Every ``{channel}/{name}/{version}/`` directory under a dev root.

    A missing root is not an error — nothing has been dev-installed yet.
    """
    out: List[Path] = []
    for channel in _read_subdirs(dev_root):
        for name in _read_subdirs(channel):
            out.extend(_read_subdirs(name))
    return sorted(out)


def _read_subdirs(directory: Path) -> List[Path]:
    if not directory.is_dir():
        return []
    return sorted(child for child in directory.iterdir() if child.is_dir())


def check_no_fabric_conflict(
    resolve_alias: Callable[[str], Optional[str]], cap: Cap
) -> None:
    """Refuse a dev cap whose alias already means a DIFFERENT cap in the fabric.

    A dev cap providing the same fabric cap (e.g. identity) is not a conflict —
    the comparison is on canonical URNs, not on the alias alone.
    """
    dev_urn = cap.urn.to_string()
    for alias in cap.get_aliases():
        target = resolve_alias(alias)
        if target is None:
            # The fabric does not define this alias — nothing to conflict with.
            continue
        try:
            fabric_urn = CapUrn.from_string(target).to_string()
        except Exception:
            fabric_urn = target
        if fabric_urn != dev_urn:
            raise FabricConflictError(alias, dev_urn, fabric_urn)
