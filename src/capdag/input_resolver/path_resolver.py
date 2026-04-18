"""Path resolution for files, directories, and globs."""

from __future__ import annotations

import glob as glob_mod
import os
from pathlib import Path

from capdag.input_resolver.os_filter import should_exclude, should_exclude_dir
from capdag.input_resolver.types import (
    EmptyInputError,
    InputItem,
    InvalidGlobError,
    NoFilesResolvedError,
    NotFoundError,
)

MAX_RECURSION_DEPTH = 100


def _expand_tilde(path: Path) -> Path:
    return Path(os.path.expanduser(str(path)))


def _expand_tilde_string(value: str) -> str:
    return os.path.expanduser(value)


def resolve_item(item: InputItem) -> list[Path]:
    if item.kind == "file":
        return resolve_file(Path(item.value))
    if item.kind == "directory":
        return resolve_directory(Path(item.value))
    if item.kind == "glob":
        return resolve_glob(str(item.value))
    raise ValueError(f"Unknown input item kind: {item.kind}")


def resolve_items(items: list[InputItem]) -> list[Path]:
    if not items:
        raise EmptyInputError()

    seen: set[Path] = set()
    result: list[Path] = []
    for item in items:
        for path in resolve_item(item):
            canonical = path.resolve(strict=False)
            if canonical not in seen:
                seen.add(canonical)
                result.append(path)

    if not result:
        raise NoFilesResolvedError()

    result.sort()
    return result


def resolve_file(path: Path) -> list[Path]:
    expanded = _expand_tilde(path)
    if not expanded.exists():
        raise NotFoundError(expanded)
    if expanded.is_dir():
        return resolve_directory(expanded)
    if should_exclude(expanded):
        return []
    return [expanded.resolve()]


def resolve_directory(path: Path) -> list[Path]:
    expanded = _expand_tilde(path)
    if not expanded.exists():
        raise NotFoundError(expanded)
    if not expanded.is_dir():
        return resolve_file(expanded)

    files: list[Path] = []
    visited: set[Path] = set()
    _resolve_directory_recursive(expanded, files, visited, 0)
    files.sort()
    return files


def _resolve_directory_recursive(dir_path: Path, files: list[Path], visited: set[Path], depth: int) -> None:
    if depth > MAX_RECURSION_DEPTH:
        raise RecursionError(f"Maximum recursion depth exceeded at {dir_path}")

    canonical = dir_path.resolve()
    if canonical in visited:
        return
    visited.add(canonical)

    for entry in dir_path.iterdir():
        if entry.is_dir():
            if should_exclude_dir(entry):
                continue
            _resolve_directory_recursive(entry, files, visited, depth + 1)
        elif entry.is_file() and not should_exclude(entry):
            files.append(entry)


def resolve_glob(pattern: str) -> list[Path]:
    expanded = _expand_tilde_string(pattern)
    if expanded.count("[") != expanded.count("]"):
        raise InvalidGlobError(pattern, "unbalanced character class brackets")

    files: list[Path] = []
    for match in glob_mod.glob(expanded, recursive=True):
        path = Path(match)
        if path.is_file() and not should_exclude(path):
            files.append(path)
    files.sort()
    return files
