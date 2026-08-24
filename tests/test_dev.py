"""Tests for capdag.dev — mirroring the reference capdag tests.

Tests use TEST###: comments matching the Rust implementation for cross-tracking.
"""

import re
import json
import os
import stat
from pathlib import Path

import pytest

from capdag.bifaci.manifest import CapManifest
from capdag.cap.definition import Cap
from capdag.urn.cap_urn import CapUrn
from capdag.dev import (
    STUB_LANGUAGES,
    STUB_PLACEHOLDER,
    STUB_CONTRACT_VERSION,
    AlreadyExistsError,
    AmbiguousEntryError,
    FabricConflictError,
    InvalidNameError,
    NotDevError,
    check_no_fabric_conflict,
    entry_for,
    find_dev_cap_by_alias,
    language,
    languages,
    project_entry,
    read_entry_manifest,
    scaffold_cartridge,
    stage_dev_cartridge,
)
from capdag.dev import _render  # noqa: F401 — exercised through the public API


# TEST7154: EVERY vendored language scaffolds a runnable-shaped project — every
# declared file exists, no placeholder survives anywhere (contents or paths),
# the manifest/alias/media URNs are seeded from the project name, and the
# interpreted languages' entries are executable.
#
# Iterating the contract rather than testing one language is the point: a newly
# vendored language is covered the moment it appears, instead of whenever
# someone remembers to add a test for it.
def test_7154_scaffold_writes_a_runnable_project_in_every_language(tmp_path):
    assert languages(), "the vendored contract must declare at least one language"

    for lang in STUB_LANGUAGES:
        name = f"mood-tagger-{lang.id}"
        proj = scaffold_cartridge(name, lang, tmp_path)
        assert proj == tmp_path / name

        sources = ""
        for file in lang.files:
            dest = proj / file.dest.replace(STUB_PLACEHOLDER, name)
            assert dest.is_file(), f"{lang.id}: declared file {dest} was not written"
            body = dest.read_text(encoding="utf-8")
            assert STUB_PLACEHOLDER not in body, f"{lang.id}: {dest} still contains the placeholder"
            sources += body

            if file.executable:
                mode = dest.stat().st_mode
                assert mode & stat.S_IXUSR, f"{lang.id}: {dest} is declared executable but is not"

        # The rendered entry path must itself be free of the placeholder — a
        # compiled cartridge's binary is named after the project.
        assert STUB_PLACEHOLDER not in entry_for(lang, name), (
            f"{lang.id}: the entry path was not rendered"
        )

        # The project name reaches the cap it declares, in every language.
        assert f"media:enc=utf-8;{name}-input" in sources, (
            f"{lang.id}: input media URN is not seeded from the project name"
        )
        assert "command=" not in sources, f"{lang.id}: carries the removed `command=` field"


# TEST7155: scaffolding rejects a bad name and refuses to overwrite.
def test_7155_scaffold_guards(tmp_path):
    lang = STUB_LANGUAGES[0]
    with pytest.raises(InvalidNameError):
        scaffold_cartridge("Bad Name", lang, tmp_path)
    scaffold_cartridge("greeter", lang, tmp_path)
    with pytest.raises(AlreadyExistsError):
        scaffold_cartridge("greeter", lang, tmp_path)


def _write_stub_entry(directory: Path, name: str, alias: str, cap_urn: str) -> Path:
    """Write a cartridge entry (a bash script) that prints a canned CapManifest
    on `manifest`, exercising the capdag-side staging/parsing/resolution without
    any language runtime.

    It is written at the PYTHON entry because that is the one language whose
    entry is a source file with no build step, so a bash script standing in for
    it is discovered by exactly the same path a real project would be.
    """
    python = language("python")
    assert python is not None, "the contract must cover python"
    urn_json = cap_urn.replace('"', '\\"')
    manifest = (
        f'{{"name":"{name}","version":"0.1.0","channel":"nightly","registry_url":null,'
        f'"description":"stub","cap_groups":[{{"name":"default","caps":['
        f'{{"urn":"cap:effect=none","title":"Identity","aliases":["identity"]}},'
        f'{{"urn":"{urn_json}","title":"{name}","aliases":["{alias}"]}}]}}]}}'
    )
    script = "#!/usr/bin/env bash\nif [ \"$1\" = manifest ]; then\n  cat <<'EOF'\n" + manifest + "\nEOF\nfi\n"
    path = directory / entry_for(python, directory.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


# TEST7156: read_entry_manifest + stage_dev_cartridge + find_dev_cap_by_alias
# round-trip: a stub project installs under dev/v{N}/nightly/<name>/<ver>/,
# writes a cartridge.json, and its custom cap is resolvable by alias.
def test_7156_dev_install_and_find_by_alias(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    cap_urn = 'cap:greet;in="media:enc=utf-8";out="media:enc=utf-8;greeting"'
    _write_stub_entry(project, "greeter", "greet", cap_urn)

    user_dir = tmp_path / "cartridges"
    entry = project_entry(project)
    manifest = read_entry_manifest(entry)
    assert manifest.name == "greeter"
    assert manifest.registry_url is None

    version_dir = stage_dev_cartridge(project, manifest, user_dir, 1, 7)
    assert str(version_dir).endswith(os.path.join("dev", "v1", "nightly", "greeter", "0.1.0"))
    assert (version_dir / "cartridge.json").is_file()
    assert (version_dir / entry_for(language("python"), "proj")).is_file()

    found = find_dev_cap_by_alias(user_dir, 1, "greet")
    assert found is not None, "the dev cap must be resolvable by its alias"
    cap, resolved_dir = found
    assert resolved_dir == version_dir
    assert "greet" in cap.get_aliases()


# TEST7157: dev-install refuses a PUBLISHED manifest. `registry_url` non-null
# means the cartridge belongs to a registry, and staging it under the dev slug
# would put a published identity in a slot reserved for local work.
def test_7157_dev_install_rejects_published_manifest(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    manifest = CapManifest(
        name="greeter",
        version="0.1.0",
        channel="nightly",
        registry_url="https://cartridges.machinefabric.com/v1/manifest",
        description="published",
        cap_groups=[],
    )
    with pytest.raises(NotDevError):
        stage_dev_cartridge(project, manifest, tmp_path / "cartridges", 1, 7)


# TEST7159: a project with two languages' entries is REFUSED, not silently
# resolved. A project is one cartridge; installing whichever entry sorted first
# would be a coin flip the developer never sees.
def test_7159_two_entries_is_ambiguous_not_a_coin_flip(tmp_path):
    proj = tmp_path / "twoheaded"
    proj.mkdir()

    written = 0
    for lang in STUB_LANGUAGES:
        entry = proj / entry_for(lang, "twoheaded")
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        entry.chmod(0o755)
        written += 1
        if written == 2:
            break
    assert written == 2, "the contract must cover at least two languages"

    with pytest.raises(AmbiguousEntryError):
        project_entry(proj)


# TEST7160: the vendored stub contract is IDENTICAL to the canonical source.
#
# This is the whole promise of `capdag new`: the same command from any capdag
# binary writes the same project. Every mirror's copy is generated from this
# one source, so a difference here means the reference itself was vendored from
# a different commit than the stub repo currently holds — which would ship
# capdags that disagree about what a cartridge looks like, silently.

VERSION = re.compile(r"\b\d+\.\d+\.\d+\b")

# A dependency line naming capdag, in any language's manifest syntax.
CAPDAG_DEPENDENCY = re.compile(
    r"capdag.*(path\s*[:=]|git\s*=|tag\s*=|url:|from:)|^\s*(require|replace)\s+\S*capdag"
)


def _logical_lines(text: str) -> list[str]:
    """Split on real newlines AND the escaped ones inside string literals.

    The generated module embeds each stub file — manifests included — as a
    single-line string literal whose newlines are the two characters `\n`. A
    rule applied only to real lines cannot see inside them, which is exactly
    where the versions and the dependency lines live."""
    return re.split(r"(\\n|\n)", text)


def _comparable(text: str) -> str:
    """The stub, with everything that moves on its own removed.

    Two things change without the stub changing, and neither says anything
    about whether the stub is the canonical one:

      * the capdag DEPENDENCY — a path while somebody works locally, a git tag
        or a registry version once published. The same stub, reached two ways,
        and the two forms are different LINES rather than one line differing
        in a version.
      * every stamped VERSION — capdag's, and the stub project's own. Both are
        written by the templates and move on every release.

    Both go, so the comparison is about the stub's CODE. Anything else that
    differs is a real edit, which is what this check exists to find."""
    out = []
    for piece in _logical_lines(text):
        if piece in ("\n", "\\n"):
            out.append(piece)
            continue
        if CAPDAG_DEPENDENCY.search(piece):
            continue
        out.append(VERSION.sub("<version>", piece))
    return "".join(out)


def _assert_stub_matches(language: str, dest: str, vendored: str, canonical: str) -> None:
    """The vendored stub IS the canonical one, once the things that move on
    their own are set aside."""
    if vendored == canonical:
        return
    assert _comparable(vendored) == _comparable(canonical), (
        f"{language}: vendored {dest} differs from the canonical stub in more than its "
        "versions and capdag dependency — re-vendor the stubs"
    )


def test_7160_vendored_stub_contract_matches_the_canonical_source():
    # Locate the canonical stubs relative to this mirror inside the workspace.
    # Absent (a standalone checkout of capdag-py), there is nothing to compare
    # against and the vendored copy IS the contract — that is not a skip to hide
    # behind, it is the only meaningful statement available.
    stub_root = Path(__file__).resolve().parents[2] / "capdag-stub-cartridges"
    canonical = stub_root / "stubs.json"
    if not canonical.is_file():
        pytest.skip(f"canonical stubs not present at {canonical} (standalone checkout)")

    contract = json.loads(canonical.read_text(encoding="utf-8"))
    assert contract["contract_version"] == STUB_CONTRACT_VERSION, (
        "vendored contract version differs from canonical — re-vendor the stubs"
    )
    assert contract["placeholder"] == STUB_PLACEHOLDER
    assert len(contract["languages"]) == len(STUB_LANGUAGES), (
        "vendored language count differs from canonical — re-vendor the stubs"
    )

    for vendored in STUB_LANGUAGES:
        spec = contract["languages"].get(vendored.id)
        assert spec is not None, f"vendored language {vendored.id} is not in the canonical contract"
        assert spec["flag"] == vendored.flag
        assert spec["entry"] == vendored.entry
        assert len(spec["files"]) == len(vendored.files)
        for declared, got in zip(spec["files"], vendored.files):
            want = (stub_root / declared["source"]).read_text(encoding="utf-8")
            assert got.dest == declared["dest"]
            assert got.executable == declared["executable"]
            _assert_stub_matches(vendored.id, got.dest, got.contents, want)


# TEST7158: the fabric-conflict guard — a dev cap whose alias the fabric maps to
# a DIFFERENT cap is rejected; a brand-new alias, and a dev cap that matches an
# existing fabric cap exactly, are both accepted.
def test_7158_fabric_conflict_guard():
    alpha_urn = 'cap:alpha;in="media:enc=utf-8";out="media:enc=utf-8;alpha"'
    alpha = Cap(CapUrn.from_string(alpha_urn), "Alpha", ["alpha"])

    # The fabric knows exactly one alias: `alpha`.
    def resolve(alias):
        return alpha_urn if alias == "alpha" else None

    # A dev cap claiming `alpha` but with a DIFFERENT URN => conflict.
    clashing = Cap(
        CapUrn.from_string('cap:beta;in="media:enc=utf-8";out="media:enc=utf-8;beta"'),
        "Clash",
        ["alpha"],
    )
    with pytest.raises(FabricConflictError) as excinfo:
        check_no_fabric_conflict(resolve, clashing)
    assert "alpha" in str(excinfo.value), "the error must name the conflicting alias"

    # A brand-new alias the fabric never heard of => fine.
    fresh = Cap(
        CapUrn.from_string('cap:gamma;in="media:enc=utf-8";out="media:enc=utf-8;gamma"'),
        "Fresh",
        ["gamma"],
    )
    check_no_fabric_conflict(resolve, fresh)

    # The very same fabric cap (same alias => same URN) => not a conflict.
    check_no_fabric_conflict(resolve, alpha)
