"""OS file filtering for input resolution."""

from __future__ import annotations

from pathlib import Path

EXCLUDED_FILES = {
    ".DS_Store",
    ".localized",
    ".AppleDouble",
    ".LSOverride",
    ".DocumentRevisions-V100",
    ".fseventsd",
    ".Spotlight-V100",
    ".TemporaryItems",
    ".Trashes",
    ".VolumeIcon.icns",
    ".com.apple.timemachine.donotpresent",
    ".AppleDB",
    ".AppleDesktop",
    "Network Trash Folder",
    "Temporary Items",
    ".apdisk",
    "Thumbs.db",
    "Thumbs.db:encryptable",
    "ehthumbs.db",
    "ehthumbs_vista.db",
    "desktop.ini",
    ".directory",
    ".project",
    ".settings",
    ".classpath",
}

EXCLUDED_DIRS = {
    ".git",
    ".svn",
    ".hg",
    ".bzr",
    "_darcs",
    ".fossil",
    ".Spotlight-V100",
    ".Trashes",
    ".fseventsd",
    ".TemporaryItems",
    "__MACOSX",
    ".DocumentRevisions-V100",
    ".idea",
    ".vscode",
    ".vs",
    "__pycache__",
    "node_modules",
    ".tox",
    ".nox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".hypothesis",
}

EXCLUDED_EXTENSIONS = {"tmp", "temp", "swp", "swo", "swn", "bak", "backup", "orig"}


def should_exclude(path: Path) -> bool:
    name = path.name
    if name in EXCLUDED_FILES:
        return True
    if name.startswith("._"):
        return True
    if name.startswith("~$"):
        return True
    if name in {"Icon\r", "Icon\x0d"}:
        return True
    ext = path.suffix[1:].lower() if path.suffix.startswith(".") else path.suffix.lower()
    if ext in EXCLUDED_EXTENSIONS:
        return True
    return False


def should_exclude_dir(path: Path) -> bool:
    return path.name in EXCLUDED_DIRS
