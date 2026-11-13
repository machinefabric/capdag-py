"""Where a fabric registry's definitions are kept on disk, and how an entry is
written and read there.

The cache is shared: every capdag process on a machine that reads the same
fabric reads and writes the same folder, and they run at once (a test run
starts many builds within milliseconds of each other). Two rules follow.

- **One folder per fabric manifest version.** A registry pinned at manifest
  ``N`` keeps everything under ``<registry folder>/v<N>/``::

      <os cache>/capdag/<charter slug>/        the registry's folder; its charter
        v<N>/manifest.json                     manifest N, as the registry served it
        v<N>/file_types.json                   which of manifest N's media are file types, worked
                                               out once from manifest.json (and its hash)
        v<N>/caps/<sha256 of URN>/<defver>.json
        v<N>/media/<sha256 of URN>/<defver>.json
        v<N>/aliases/<sha256 of name>/<defver>.json
        v<N>/dims/<sha256 of name>/<defver>.json

  capdag releases built against different manifests can be installed side by
  side; each reads and writes only its own ``v<N>``, so none ever reads a
  definition another wrote under other rules.

- **An entry is replaced whole.** It is written to a temporary file in the
  folder it belongs in and renamed over the entry, so a reader sees the old
  entry or the new one, never part of one. A temporary file is named
  ``.<entry>.<pid>-<n>.tmp``; one a killed writer left behind is never read,
  and ``capdag cache clear`` removes it.

An entry that is there and cannot be read, or does not parse, or is not the
definition its path names, is corrupt: it is an error naming the file, never
treated as missing.

Before this layout, every manifest version shared the registry's folder
(``<charter slug>/{caps,media,aliases,dims,manifests}``). This library neither
reads nor writes those folders: capdag releases from before it still do.
``capdag cache clear`` removes them.
"""

import hashlib
import itertools
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TypeVar

#: The folders a manifest version's definitions live in, one per kind.
KIND_FOLDERS = ("caps", "media", "aliases", "dims")

#: The file a manifest version's manifest is kept in, in its folder.
MANIFEST_FILE = "manifest.json"

#: The file the file types a manifest version's manifest names are kept in,
#: in its folder: which of its media definitions carry the ``ext=`` tag, with
#: the hash of the manifest file they were worked out from.
FILE_TYPES_FILE = "file_types.json"

#: The folders the shared layout before this one kept in a registry's folder.
#: Nothing reads them; clearing the cache removes them.
LEGACY_FOLDERS = ("caps", "media", "aliases", "dims", "manifests")

T = TypeVar("T")


def _cache_error(message: str) -> Exception:
    # The registry module defines the error and imports this one, so the
    # error class is looked up when it is raised.
    from capdag.fabric.registry import CacheError

    return CacheError(message)


def version_dir(registry_dir: Path, manifest_version: int) -> Path:
    """The folder manifest ``manifest_version`` of a registry keeps its cache
    in."""
    return registry_dir / f"v{manifest_version}"


def key_hash(key: str) -> str:
    """The hash a definition is filed under, in the cache as in the
    registry."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def entry_path(version_folder: Path, kind: str, key: str, defver: int) -> Path:
    """The file the definition ``key`` (a normalized URN, or an alias or dim
    name) of ``kind`` at ``defver`` is kept in, under a manifest version's
    folder."""
    return version_folder / kind / key_hash(key) / f"{defver}.json"


# Tells apart the temporary files one process writes at once.
_temporary_files = itertools.count()
_temporary_files_lock = threading.Lock()


def _next_temporary() -> int:
    with _temporary_files_lock:
        return next(_temporary_files)


def write_atomically(path: Path, data: bytes) -> None:
    """Put ``data`` at ``path`` whole: written to a temporary file beside it,
    then renamed over it. A reader opening ``path`` meanwhile reads what was
    there before, or ``data``, never part of them. The folder is made when
    missing."""
    folder = path.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise _cache_error(f"failed to create the cache folder {folder}: {e}") from e
    temporary = folder / f".{path.name}.{os.getpid()}-{_next_temporary()}.tmp"
    try:
        with open(temporary, "wb") as f:
            f.write(data)
    except OSError as e:
        temporary.unlink(missing_ok=True)
        raise _cache_error(f"failed to write the cache file {temporary}: {e}") from e
    try:
        _rename_over(temporary, path)
    except OSError as e:
        temporary.unlink(missing_ok=True)
        raise _cache_error(f"failed to put the cache file {path} in place: {e}") from e


def _rename_over(source: Path, target: Path) -> None:
    """Rename ``source`` over ``target``, replacing it.

    Unix replaces the name in one step whatever else has it open. Windows
    refuses the replacement with "access denied" while another process is
    replacing the same entry, or reading it, at that moment; that is a peer
    using the same definition, so the rename is asked again for a short bound,
    after which the refusal is raised as it stands."""
    attempts = 0
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if sys.platform != "win32" or attempts >= 50:
                raise
            attempts += 1
            time.sleep(0.01)


def store_entry(path: Path, entry: Dict[str, Any], what: str) -> None:
    """Serialize ``entry`` (an entry's ``to_dict()``) and put it at ``path``
    whole (:func:`write_atomically`). ``what`` names the kind of entry in the
    error."""
    try:
        data = json.dumps(entry, indent=2).encode("utf-8")
    except (TypeError, ValueError) as e:
        raise _cache_error(f"failed to serialize the {what} cache entry: {e}") from e
    write_atomically(path, data)


def read_entry(path: Path, what: str, parse: Callable[[Any], T]) -> Optional[T]:
    """The entry at ``path``: ``None`` when there is none, ``parse`` of its
    JSON when it parses, and an error naming the file when it is there and
    cannot be read or does not parse. ``what`` names the kind of entry in the
    error."""
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise _cache_error(f"the cached {what} {path} cannot be read: {e}") from e
    try:
        return parse(json.loads(data))
    # Whatever the parser refuses — not JSON, a field missing or of the wrong
    # type, a URN that does not parse — the file is not an entry.
    except Exception as e:
        raise corrupt(path, what, f"{type(e).__name__}: {e}") from e


def corrupt(path: Path, what: str, detail: str) -> Exception:
    """The error for a cache entry that is there and is not what its path
    says."""
    return _cache_error(
        f"the cached {what} {path} is corrupt: {detail}; "
        f"remove the file, or run `capdag cache clear`"
    )
