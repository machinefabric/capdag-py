"""How a cartridge entry is started, in every language.

The reference is ``capdag-rs/src/bifaci/launch.rs``; these numbers mean the
same behaviour in every mirror.
"""

from __future__ import annotations

import os
from pathlib import Path

from capdag.bifaci import launch


# TEST7162: a script cartridge is started through its interpreter.
#
# A scaffolded Python cartridge is `cartridge.py`, and on Unix its shebang
# makes it directly executable. Windows has no shebang, so `CreateProcess`
# refuses the file outright:
#
#     %1 is not a valid Win32 application
#
# Every caller built its own `[str(entry)]` argument list and all three —
# reading a manifest, probing caps, hosting — were wrong on Windows at once. No
# scaffolded Python cartridge could be launched on the platform at all.
def test7162_a_script_entry_is_launched_through_an_interpreter() -> None:
    entry = str(Path("proj") / "cartridge.py")
    argv = launch.launcher(entry)
    assert len(argv) == 2, f"a .py needs an interpreter before it: {argv}"
    assert argv[0] != entry, f"a .py must not be launched as a program: {argv}"
    assert argv[1] == entry

    # Case does not decide it.
    assert launch.launcher("CARTRIDGE.PY")[0] != "CARTRIDGE.PY"


# TEST7163: a compiled cartridge is started as itself.
#
# The rule keys on the extension, so it has to leave alone the entries that
# already are programs — a Rust or Go cartridge's binary. Running one through
# an interpreter would be a new failure invented by the fix.
def test7163_a_compiled_entry_runs_itself() -> None:
    entry = str(Path("target") / "release" / ("mood-tagger" + launch.executable_suffix()))
    assert launch.launcher(entry) == [entry]


# TEST7164: a compiled entry carries the platform's suffix.
#
# The stub declares `target/release/<name>` — one string, vendored into four
# mirrors, so it cannot carry one platform's spelling. Cargo writes
# `<name>.exe` on Windows, and looking for the declared spelling found nothing:
# a project that had built perfectly reported that it had no entry.
def test7164_a_compiled_entry_carries_the_platforms_suffix() -> None:
    if os.name == "nt":
        assert launch.executable_suffix() == ".exe"
    else:
        assert launch.executable_suffix() == ""


# TEST7165: the entry's own arguments come after the interpreter's.
#
# `command(entry, "manifest")` has to produce `python3 cartridge.py manifest`
# and never `python3 manifest cartridge.py`, which would ask the interpreter to
# run a file called `manifest`.
def test7165_the_entrys_arguments_follow_it() -> None:
    argv = launch.command(Path("proj") / "cartridge.py", "manifest")
    assert argv[-1] == "manifest"
    assert argv[-2].endswith("cartridge.py")
