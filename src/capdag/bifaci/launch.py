"""How a cartridge entry is started.

A scaffolded Python cartridge is ``cartridge.py``, and on Unix its shebang
makes it directly executable. Windows has no shebang: ``CreateProcess`` — and
so every language's ``exec`` — refuses the file outright with

.. code-block:: text

    %1 is not a valid Win32 application

so ``capdag dev-install`` could not read a Python project's manifest, and no
scaffolded Python cartridge could be launched on the platform at all. Naming
the interpreter is what the shebang was doing; doing it here does it on both.

One module, because starting a cartridge happens in three places — reading a
manifest, probing its caps, hosting it — and each of them built its own
argument list. All three were wrong in the same way at once, which is what
having three of them buys.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

#: How an entry that is a SCRIPT is run, by extension.
#:
#: Keyed on the extension rather than on the language, because the callers that
#: need it have a PATH and not a language: ``project_entry`` finds an entry by
#: looking, and what it finds is a filename.
INTERPRETERS = {".py": "python3", ".js": "node"}


def executable_suffix() -> str:
    """What a COMPILED entry is called on this platform.

    A scaffolded Rust cartridge declares ``target/release/<name>`` and Cargo
    writes ``target/release/<name>.exe``. Looking for the declared spelling
    found nothing on Windows, so a project that had built perfectly reported
    that it had no entry.
    """
    return ".exe" if os.name == "nt" else ""


def launcher(entry: str | Path) -> list[str]:
    """The command that runs ``entry``, without the entry's own arguments.

    A compiled entry runs itself, so the command is one word. A script entry
    runs under the interpreter its extension names, so it is two.
    """
    entry = Path(entry)
    interpreter = INTERPRETERS.get(entry.suffix.lower())
    if interpreter is None:
        return [str(entry)]
    if os.name == "nt" and interpreter == "python3":
        # `python3` is the name everywhere except a Windows install, which
        # ships `python.exe` and no `python3.exe`. This interpreter is the last
        # answer rather than the first: a cartridge is a separate process on
        # purpose, and reaching for `sys.executable` first would host every
        # Python cartridge inside whatever happened to be running capdag.
        for candidate in ("python3", "python"):
            if shutil.which(candidate):
                return [candidate, str(entry)]
        return [sys.executable, str(entry)]
    return [interpreter, str(entry)]


def command(entry: str | Path, *arguments: str) -> list[str]:
    """The full argument list that runs a cartridge entry."""
    return [*launcher(entry), *arguments]
