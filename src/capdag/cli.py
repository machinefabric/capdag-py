"""capdag — the Python capdag CLI.

A capdag mirror is not just a library: ``capdag dev new`` is how a cartridge project
comes into existence, and every mirror must be able to create the same project.
This module is the Python mirror's CLI, installed as the ``capdag`` console
script.

What this binary does and does not do
-------------------------------------

The commands here are exactly those the Python library can back today, named
and shaped as the reference capdag CLI names them::

    info <cap>...        a capability: title, aliases, URN; --json, its definition
    cache refresh|clear  renew or remove the local copy of the fabric
    dev new <path> --lang <language>
                         start a cartridge project in any vendored language
    dev install [<dir>]  install a cartridge project for local runs
    dev hash-dir <dir>   the deterministic content hash of a version directory

``run``, ``plan``, ``caps``, ``check`` and ``graph`` are NOT here, because
this mirror has no plan executor. They are absent rather than stubbed: a command
that accepted the arguments and then reported "unsupported" would be a worse lie
than not existing, and ``capdag help`` says plainly what is missing and where it
lives.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from capdag import dev
from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.bifaci.cartridge_repo import CARTRIDGE_REGISTRY_VERSION
from capdag.fabric.registry import (
    FabricRegistry,
    FabricRegistryError,
    NotFoundError,
    ParseError,
    RegistryConfig,
    ValidationError,
)


COMMANDS = ["info", "cache", "dev"]


class CliError(Exception):
    """What went wrong, said as the reference CLI says it: the problem, what
    was expected and found, and what to type next."""

    def __init__(self, problem: str, context: Optional[List[str]] = None, hint: Optional[str] = None, exit: int = 1):
        super().__init__(problem)
        self.problem = problem
        self.context = context or []
        self.hint = hint
        self.exit = exit

    def render(self) -> str:
        out = f"error: {self.problem}\n"
        for line in self.context:
            out += f"  {line}\n"
        if self.hint:
            out += f"hint: {self.hint}\n"
        return out


def usage_error(problem: str, hint: Optional[str] = None, context: Optional[List[str]] = None) -> CliError:
    return CliError(problem, context=context, hint=hint, exit=2)


def user_cartridge_dir() -> Path:
    """The per-user cartridge install root, in the same
    ``{registry_slug}/{channel}/{name}/{version}/`` tree every host uses."""
    return Path.home() / ".capdag" / "cartridges"


async def _registry() -> FabricRegistry:
    return await FabricRegistry.with_config(RegistryConfig())


async def _clear_fabric_cache() -> Path:
    """Clear the fabric cache every other command reads — the fabric this
    process is bound to, at the manifest version it is built for — without
    opening a registry on it: a cache holding a corrupt entry is one a
    registry refuses to open, and clearing is what that refusal says to do.
    Answers the folder cleared."""
    config = RegistryConfig()
    try:
        return await FabricRegistry.clear_cache_of(config, FabricRegistry._baked_manifest_version())
    except FabricRegistryError as e:
        raise CliError(f"the fabric cache of {config.anchor} could not be cleared", [str(e)])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capdag",
        description="The Python capdag CLI: capability lookup, the fabric cache and cartridge development.",
        epilog="This mirror has no plan executor: run, plan, caps, check and graph are the reference capdag's.",
    )
    parser.add_argument("--fabric", metavar="URL", help="resolve against this fabric instead of the built-in one (env: CDG_FABRIC_REGISTRY_URL)")
    parser.add_argument("--json", action="store_true", help="print JSON Lines on stdout, one record per line")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    info = sub.add_parser("info", help="show a capability", epilog="Examples:\n  capdag info disbind-pdf\n  capdag info --json disbind-pdf", formatter_class=argparse.RawDescriptionHelpFormatter)
    info.add_argument("names", nargs="+", metavar="NAME", help="capabilities, by alias or URN")
    info.add_argument("--no-cache", action="store_true", help="read the fabric afresh")

    cache = sub.add_parser("cache", help="the local copy of the fabric")
    cache_sub = cache.add_subparsers(dest="cache_command", metavar="ACTION", required=True)
    cache_sub.add_parser("refresh", help="fetch the fabric afresh", epilog="Examples:\n  capdag cache refresh", formatter_class=argparse.RawDescriptionHelpFormatter)
    cache_sub.add_parser("clear", help="remove the local copy", epilog="Examples:\n  capdag cache clear", formatter_class=argparse.RawDescriptionHelpFormatter)

    dev_parser = sub.add_parser("dev", help="develop cartridges")
    dev_sub = dev_parser.add_subparsers(dest="dev_command", metavar="ACTION", required=True)
    new = dev_sub.add_parser("new", help="start a cartridge project", epilog="Examples:\n  capdag dev new sentiment --lang python", formatter_class=argparse.RawDescriptionHelpFormatter)
    new.add_argument("path", metavar="PATH", help="where to make it; its last part is the cartridge's name")
    new.add_argument("--lang", required=True, choices=[lang.id for lang in dev.languages()], help="the language to write it in")
    install = dev_sub.add_parser("install", help="install a cartridge project for local runs", epilog="Examples:\n  capdag dev install ./sentiment", formatter_class=argparse.RawDescriptionHelpFormatter)
    install.add_argument("dir", nargs="?", default=".", metavar="DIR", help="the project's directory")
    hash_dir = dev_sub.add_parser("hash-dir")
    hash_dir.add_argument("dir", metavar="DIR")
    return parser


# ---------------------------------------------------------------------------
# dev new
# ---------------------------------------------------------------------------


def cmd_dev_new(path: Path, lang_id: str, as_json: bool) -> int:
    lang = dev.language(lang_id)
    name = path.name
    if not name:
        raise usage_error(f"'{path}' names no directory to make")
    parent = path.parent if str(path.parent) else Path(".")
    try:
        project_dir = dev.scaffold_cartridge(name, lang, parent)
    except dev.DevError as e:
        raise CliError(f"the project {path} could not be made", [str(e)])
    if as_json:
        print(json.dumps({"type": "project", "dir": str(project_dir), "language": lang.id}))
        return 0
    print(f"Made the {lang.display} cartridge '{name}' at {project_dir}", file=sys.stderr)
    print("Next:", file=sys.stderr)
    print(f"  cd {project_dir}", file=sys.stderr)
    for step in lang.build:
        print(f"  {step.replace(dev.STUB_PLACEHOLDER, name)}", file=sys.stderr)
    print("  capdag dev install", file=sys.stderr)
    print(f'  echo "I love this" | capdag run {name}', file=sys.stderr)
    print(project_dir)
    return 0


# ---------------------------------------------------------------------------
# dev install
# ---------------------------------------------------------------------------


async def cmd_dev_install(project_dir: Path, as_json: bool) -> int:
    try:
        entry = dev.project_entry(project_dir)
        manifest = dev.read_entry_manifest(entry)
    except dev.DevError as e:
        raise CliError(f"{project_dir} is not a cartridge project that is built", [str(e)],
                       "build it first, as `capdag dev new` said; then run this again")

    # A dev cartridge may declare caps the fabric does not know, but its aliases
    # must not collide with the fabric. Every alias it claims is warmed first:
    # the cached resolver only sees aliases already on disk.
    registry = await _registry()

    def resolve(alias: str) -> Optional[str]:
        return registry.resolve_alias_cached(alias)

    for group in manifest.cap_groups:
        for c in group.caps:
            for alias in c.get_aliases():
                try:
                    await registry.get_alias(alias)
                except NotFoundError:
                    # An alias the fabric does not define is the ordinary case
                    # for a dev cap; the check below finds no conflict for it.
                    # A fetch the registry refused is not that, and is raised.
                    pass
    try:
        for group in manifest.cap_groups:
            for c in group.caps:
                dev.check_no_fabric_conflict(resolve, c)
    except dev.DevError as e:
        raise CliError("the cartridge's caps conflict with the fabric", [str(e)])

    try:
        version_dir = dev.stage_dev_cartridge(
            project_dir, manifest, user_cartridge_dir(), CARTRIDGE_REGISTRY_VERSION, registry.manifest_version,
        )
    except dev.DevError as e:
        raise CliError("the cartridge could not be installed", [str(e)])

    if as_json:
        print(json.dumps({"type": "cartridge", "id": manifest.name, "version": manifest.version, "state": "dev", "dir": str(version_dir)}))
        return 0
    print(f"Installed the dev cartridge '{manifest.name}' {manifest.version} at {version_dir}", file=sys.stderr)
    for group in manifest.cap_groups:
        for c in group.caps:
            aliases = c.get_aliases()
            if aliases and aliases[0] != "identity":
                print(f"Run it: capdag run {aliases[0]} <input>", file=sys.stderr)
                print(version_dir)
                return 0
    print(version_dir)
    return 0


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


async def cmd_info(names: List[str], no_cache: bool, as_json: bool) -> int:
    if no_cache:
        await _clear_fabric_cache()
    registry = await _registry()
    for index, name in enumerate(names):
        try:
            definition = await registry.get_cap(name if ":" in name else await registry.resolve_alias(name))
        except (NotFoundError, ValidationError, ParseError) as e:
            raise usage_error(f"there is no capability named '{name}'", f"find one with the reference CLI: capdag caps {name}", [str(e)])
        except FabricRegistryError as e:
            # The registry could not be asked: say so as it is, never as a
            # capability that does not exist.
            raise CliError(str(e), [], "run the command again; if the registry keeps refusing, report it")
        if as_json:
            # The definition as the fabric publishes it, its fields in their
            # declared order, as the reference CLI writes it.
            record = {"type": "cap", "alias": definition.aliases[0] if definition.aliases else name,
                      "urn": definition.urn_string(), "bundled": [], "installed": [],
                      "definition": definition.to_dict()}
            print(json.dumps(record, separators=(",", ":")))
            continue
        if index > 0:
            print()
        alias = definition.aliases[0] if definition.aliases else name
        print(f"{alias} — {definition.title}")
        print(definition.urn_string())
        print(f"Aliases: {', '.join(definition.aliases)}")
        for alias_name in definition.aliases:
            found = dev.find_dev_cap_by_alias(user_cartridge_dir(), CARTRIDGE_REGISTRY_VERSION, alias_name)
            if found is not None:
                print(f"Provided by the dev cartridge at {found[1]}")
                break
    return 0


# ---------------------------------------------------------------------------
# cache
# ---------------------------------------------------------------------------


async def cmd_cache(action: str, as_json: bool) -> int:
    directory = await _clear_fabric_cache()
    manifest = None
    if action == "refresh":
        # The manifest and everything it pins, fetched afresh into the now
        # empty cache, so the renewal is complete rather than lazy.
        manifest = (await _registry()).manifest_version
    if as_json:
        print(json.dumps({"type": "cache", "dir": str(directory), "refreshed": manifest is not None, "manifest": manifest}))
    elif manifest is not None:
        print(f"Fabric cache refreshed at {directory}: manifest {manifest}", file=sys.stderr)
    else:
        print(f"Fabric cache cleared at {directory}; the next command fetches what it needs.", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# dev hash-dir
# ---------------------------------------------------------------------------


def cmd_hash_dir(directory: Path) -> int:
    """Print the deterministic content hash of a cartridge version directory:
    the walk every host computes at discovery time, byte-identical to it."""
    try:
        print(hash_cartridge_directory(directory))
    except Exception as e:
        raise CliError(f"{directory} could not be hashed", [str(e)])
    return 0


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv[1:])
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code in (0, None) else 2
    if args.fabric:
        if not args.fabric.startswith(("http://", "https://")):
            print(usage_error(f"--fabric '{args.fabric}' is not an http(s) URL", "for example: --fabric https://fabric-staging.capdag.com").render(), file=sys.stderr, end="")
            return 2
        os.environ["CDG_FABRIC_REGISTRY_URL"] = args.fabric
    try:
        if args.command == "info":
            return asyncio.run(cmd_info(args.names, args.no_cache, args.json))
        if args.command == "cache":
            return asyncio.run(cmd_cache(args.cache_command, args.json))
        if args.command == "dev":
            if args.dev_command == "new":
                return cmd_dev_new(Path(args.path), args.lang, args.json)
            if args.dev_command == "install":
                return asyncio.run(cmd_dev_install(Path(args.dir), args.json))
            return cmd_hash_dir(Path(args.dir))
        parser.print_help(sys.stderr)
        return 2
    except FabricRegistryError as registry_error:
        # The fabric could not be read — a refused fetch, one that got no
        # answer: said as it is, with the URL, the status and the manifest
        # version.
        error = CliError(str(registry_error), [], "run the command again; if it keeps failing, report it")
        if args.json:
            print(json.dumps({"type": "error", "problem": error.problem, "context": error.context, "hint": error.hint, "exit": error.exit}))
        print(error.render(), file=sys.stderr, end="")
        return error.exit
    except CliError as error:
        if args.json:
            print(json.dumps({"type": "error", "problem": error.problem, "context": error.context, "hint": error.hint, "exit": error.exit}))
        print(error.render(), file=sys.stderr, end="")
        return error.exit


if __name__ == "__main__":
    raise SystemExit(main())
