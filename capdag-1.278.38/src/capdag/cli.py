"""capdag — the Python capdag CLI.

A capdag mirror is not just a library: ``capdag new`` is how a cartridge project
comes into existence, and every mirror must be able to create the same project.
This module is the Python mirror's CLI, installed as the ``capdag`` console
script.

What this binary does and does not do
-------------------------------------

The commands here are exactly those the Python library can back today::

    new                  scaffold a cartridge project in any vendored language
    dev-install          install/update a dev cartridge under the dev slug
    find                 show what an alias or URN resolves to
    resolve              print cap definition JSON
    cache                clear/refresh the local fabric cache
    hash-cartridge-dir   the deterministic content hash of a version directory

``run``, single-cap dispatch, ``plan`` and ``dag-viz`` are NOT here, because
this mirror has no plan executor. They are absent rather than stubbed: a command
that accepted the arguments and then reported "unsupported" would be a worse lie
than not existing, and ``capdag help`` says plainly what is missing and where it
lives.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from capdag import dev
from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.bifaci.cartridge_repo import CARTRIDGE_REGISTRY_VERSION
from capdag.fabric.registry import FabricRegistry, RegistryConfig


COMMANDS = ["new", "dev-install", "find", "resolve", "cache", "hash-cartridge-dir"]


def _usage(program: str) -> str:
    p = os.path.basename(program)
    return f"""Usage:
  {p} new <name> <{dev.language_flag_list()}> [-o <dir>]   Scaffold a new cartridge project
  {p} dev-install [<project-dir>]     Install/update a dev cartridge under the dev slug
  {p} find <cap-alias-or-urn>         Show what an alias or URN resolves to
  {p} resolve <cap-alias-or-urn>...   Print cap definition JSON (array for >1)
  {p} cache [status|clear|refresh]    Invalidate/renew the local fabric cache
  {p} hash-cartridge-dir <dir>        Deterministic content hash of a version directory

Options:
  --fabric <url>   Resolve caps/media/aliases against this fabric registry
                   instead of the built-in one (env: CDG_FABRIC_REGISTRY_URL).
                   Works before any subcommand.
  --help           Show this help

Not in this mirror: run, single-cap dispatch, plan, dag-viz. They need the plan
executor, which the Python library does not implement. Use the reference capdag
CLI for those.
"""


def _die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def _take_fabric_flag(argv: List[str]) -> List[str]:
    """Strip ``--fabric <url>`` from argv and apply it to the environment.

    It is stripped before dispatch so it works in front of ANY subcommand and
    never reaches a cap's own argument parsing. A caller-chosen origin
    invalidates any baked schema base: pairing a runtime fabric with a
    build-time schema URL would validate one origin's definitions against
    another's schemas.
    """
    out: List[str] = []
    i = 0
    while i < len(argv):
        if argv[i] != "--fabric":
            out.append(argv[i])
            i += 1
            continue
        if i + 1 >= len(argv):
            _die("--fabric requires a registry URL", 2)
        url = argv[i + 1]
        if not url or url.startswith("-"):
            _die(f"--fabric requires a registry URL, got {url!r}", 2)
        os.environ.pop("CDG_SCHEMA_BASE_URL", None)
        os.environ["CDG_FABRIC_REGISTRY_URL"] = url
        i += 2
    return out


def user_cartridge_dir() -> Path:
    """The per-user cartridge install root, in the same
    ``{registry_slug}/{channel}/{name}/{version}/`` tree every host uses."""
    return Path.home() / ".capdag" / "cartridges"


async def _registry() -> FabricRegistry:
    return await FabricRegistry.with_config(RegistryConfig())


# ---------------------------------------------------------------------------
# new
# ---------------------------------------------------------------------------


def cmd_new(argv: List[str]) -> int:
    name: Optional[str] = None
    lang = None
    parent = Path(".")

    i = 2
    while i < len(argv):
        arg = argv[i]
        if arg in ("-o", "--output"):
            i += 1
            if i >= len(argv):
                _die("--output requires a directory path", 2)
            parent = Path(argv[i])
        elif dev.language(arg) is not None:
            # Two language flags is not a preference to resolve, it is a
            # command that cannot mean one thing.
            if lang is not None:
                _die(
                    f"`new` takes one language: '{lang.flag}' was already given, then '{arg}'.",
                    2,
                )
            lang = dev.language(arg)
        elif arg.startswith("--"):
            _die(
                f"Unknown option '{arg}' for `new`. Languages: {dev.language_flag_list()}.",
                2,
            )
        elif name is None:
            name = arg
        else:
            _die(f"Unexpected argument '{arg}' for `new`.", 2)
        i += 1

    if name is None:
        _die(
            f"Usage: {os.path.basename(argv[0])} new <name> "
            f"<{dev.language_flag_list()}> [-o <dir>]",
            2,
        )
    # No default language. Defaulting would make `capdag new mycart` produce a
    # different project as the stub set grows, and silently pick for someone who
    # simply forgot to say.
    if lang is None:
        _die(
            f"`new` requires a language: {dev.language_flag_list()}. "
            "Each scaffolds the same cartridge, in that language.",
            2,
        )

    try:
        project_dir = dev.scaffold_cartridge(name, lang, parent)
    except dev.DevError as e:
        _die(str(e))

    print(f"Scaffolded {lang.display} cartridge '{name}' at {project_dir}", file=sys.stderr)
    print("Next:", file=sys.stderr)
    print(f"  cd {project_dir}", file=sys.stderr)
    for step in lang.build:
        print(f"  {step.replace(dev.STUB_PLACEHOLDER, name)}", file=sys.stderr)
    print("  capdag dev-install .          # install under the local `dev` slug", file=sys.stderr)
    print(f'  echo "I love this" | capdag {name}', file=sys.stderr)
    print(project_dir)
    return 0


# ---------------------------------------------------------------------------
# dev-install
# ---------------------------------------------------------------------------


async def cmd_dev_install(argv: List[str]) -> int:
    project_dir = Path(argv[2]) if len(argv) > 2 else Path(".")

    try:
        entry = dev.project_entry(project_dir)
        manifest = dev.read_entry_manifest(entry)
    except dev.DevError as e:
        _die(str(e))

    # A dev cartridge may declare caps the fabric does not know, but its aliases
    # must not collide with the fabric. Check every declared cap up front so a
    # conflict is reported before anything is written to disk.
    registry = await _registry()

    def resolve(alias: str) -> Optional[str]:
        return registry.resolve_alias_cached(alias)

    # The cached resolver only sees aliases already on disk, so warm every alias
    # the dev cartridge claims before checking — an unwarmed cache would report
    # "no conflict" for an alias the fabric does in fact own.
    for group in manifest.cap_groups:
        for c in group.caps:
            for alias in c.get_aliases():
                try:
                    await registry.get_alias(alias)
                except Exception:
                    # An alias the fabric does not define is the ordinary case
                    # for a dev cap; the conflict check below reads the cache
                    # and finds nothing, which is the correct answer.
                    pass

    try:
        for group in manifest.cap_groups:
            for c in group.caps:
                dev.check_no_fabric_conflict(resolve, c)
    except dev.DevError as e:
        _die(str(e))

    try:
        version_dir = dev.stage_dev_cartridge(
            project_dir,
            manifest,
            user_cartridge_dir(),
            CARTRIDGE_REGISTRY_VERSION,
            registry.manifest_version,
        )
    except dev.DevError as e:
        _die(str(e))

    print(
        f"Installed dev cartridge '{manifest.name}' v{manifest.version} "
        f"({manifest.channel}) at {version_dir}",
        file=sys.stderr,
    )
    # Hint the run command using the first non-identity cap alias.
    for group in manifest.cap_groups:
        for c in group.caps:
            aliases = c.get_aliases()
            if aliases and aliases[0] != "identity":
                print(f'Run it:  echo "..." | capdag {aliases[0]}', file=sys.stderr)
                print(version_dir)
                return 0
    print(version_dir)
    return 0


# ---------------------------------------------------------------------------
# find
# ---------------------------------------------------------------------------


async def cmd_find(argv: List[str]) -> int:
    if len(argv) < 3:
        _die(f"Usage: {os.path.basename(argv[0])} find <cap-alias-or-urn>", 2)
    token = argv[2]
    registry = await _registry()

    cap_urn = token
    if ":" not in token:
        cap_urn = await registry.resolve_alias(token)
        print(f"alias  {token} -> {cap_urn}")

    definition = await registry.get_cap(cap_urn)
    print(f"cap    {definition.urn_string()}")
    print(f"title  {definition.title}")
    print(f"aliases {', '.join(definition.aliases)}")

    # A dev-installed cartridge answers caps the fabric does not, and it is the
    # thing a developer is most often looking for here.
    for alias in definition.aliases:
        found = dev.find_dev_cap_by_alias(
            user_cartridge_dir(), CARTRIDGE_REGISTRY_VERSION, alias
        )
        if found is not None:
            print(f"dev    {found[1]} (alias {alias})")
            break
    return 0


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


async def cmd_resolve(argv: List[str]) -> int:
    tokens = argv[2:]
    if not tokens:
        _die(f"Usage: {os.path.basename(argv[0])} resolve <cap-alias-or-urn>...", 2)
    registry = await _registry()

    definitions = [(await registry.get_cap(t)).to_dict() for t in tokens]
    # One argument prints the object; several print the array. Callers pipe this
    # into jq, and wrapping a single result would make every one-cap invocation
    # index into an array for no reason.
    payload = definitions[0] if len(definitions) == 1 else definitions
    print(json.dumps(payload, indent=2))
    return 0


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


async def cmd_cache(argv: List[str]) -> int:
    sub = argv[2] if len(argv) > 2 else "status"
    registry = await _registry()

    if sub == "status":
        print(f"origin   {registry.config.registry_base_url}")
        print(f"manifest v{registry.manifest_version}")
        print(f"root     {registry.cache_dir}")
        print(f"caps     {len(await registry.get_cached_caps())}")
        print(f"media    {len(await registry.get_cached_media_defs())}")
        print(f"aliases  {len(registry.cached_cap_aliases())}")
    elif sub == "clear":
        registry.clear_cache()
        print(f"Cleared {registry.cache_dir}", file=sys.stderr)
    elif sub == "refresh":
        # Refresh is clear followed by a re-read: the manifest is re-fetched by
        # the next construction, which is what makes the following lookups warm
        # against the current snapshot rather than the one on disk.
        registry.clear_cache()
        refreshed = await _registry()
        print(
            f"Refreshed {refreshed.cache_dir} at manifest v{refreshed.manifest_version}",
            file=sys.stderr,
        )
    else:
        _die(f"Usage: {os.path.basename(argv[0])} cache [status|clear|refresh]", 2)
    return 0


# ---------------------------------------------------------------------------
# hash-cartridge-dir
# ---------------------------------------------------------------------------


def cmd_hash_cartridge_dir(argv: List[str]) -> int:
    """Print the deterministic content hash of a cartridge version directory.

    This is the same walk every host computes at discovery time, so a hash
    printed here is byte-identical to the one a running engine derives. Never
    reimplement the walk elsewhere — it would silently drift.
    """
    if len(argv) < 3:
        _die(f"Usage: {os.path.basename(argv[0])} hash-cartridge-dir <version-dir>", 2)
    try:
        print(hash_cartridge_directory(Path(argv[2])))
    except Exception as e:
        _die(f"hash-cartridge-dir: failed to hash '{argv[2]}': {e}")
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    argv = _take_fabric_flag(argv)

    if len(argv) < 2:
        print(_usage(argv[0]), file=sys.stderr, end="")
        return 1

    command = argv[1]
    if command == "new":
        return cmd_new(argv)
    if command == "dev-install":
        return asyncio.run(cmd_dev_install(argv))
    if command == "find":
        return asyncio.run(cmd_find(argv))
    if command == "resolve":
        return asyncio.run(cmd_resolve(argv))
    if command == "cache":
        return asyncio.run(cmd_cache(argv))
    if command == "hash-cartridge-dir":
        return cmd_hash_cartridge_dir(argv)
    if command in ("help", "--help", "-h"):
        print(_usage(argv[0]), file=sys.stderr, end="")
        return 0

    # A `.machine` file or a bare cap alias means the caller wants to EXECUTE
    # something, which this mirror cannot do. Saying so — and naming what does —
    # beats "unknown command".
    if command.endswith(".machine") or not command.startswith("-"):
        _die(
            f"{command}: this mirror does not execute machines or caps — it has no "
            "plan executor.\nRun it with the reference capdag CLI (the Rust build) "
            f"instead.\nThis binary covers: {', '.join(COMMANDS)}",
            2,
        )
    print(f"Unknown option '{command}'.", file=sys.stderr)
    print(_usage(argv[0]), file=sys.stderr, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
