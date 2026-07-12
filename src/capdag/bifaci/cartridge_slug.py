"""Cartridge registry slug — deterministic, human-readable mapping from a
registry URL to a top-level folder name under the cartridges install root.

Mirrors capdag::cartridge_slug byte-for-byte: the slug is a path-safe transform
of the URL's AUTHORITY (host, plus ``:port`` if present) — the substring after
``://`` up to the next ``/``, ``?``, or ``#`` — lowercased, with every character
outside ``[a-z0-9.-]`` replaced by ``-`` (so a port ``:`` becomes ``-``). The
manifest path (incl. the ``/v<N>/manifest`` version segment), query, and
trailing slash are discarded, so the slug is version- and path-independent. No
hashing — domains are unique and a readable folder name is easier to reason
about. The literal string "dev" is reserved for dev cartridges with no registry.

The mapping is one-way: folder → URL is recovered from each installed
cartridge's own ``cartridge.json:registry_url``. The host validates
``slug_for(cartridge_json.registry_url) == folder_name`` at parse time.
"""

from typing import Optional

#: Reserved folder name for cartridges with no registry. A real registry
#: authority is never the literal "dev", so the namespaces never overlap.
DEV_SLUG = "dev"


def _authority_of(url: str) -> str:
    """The authority (host[:port]) of a registry URL: after ``://`` up to the
    next ``/``, ``?``, or ``#`` (path/query/fragment discarded)."""
    after_scheme = url.split("://", 1)[1] if "://" in url else url
    end = len(after_scheme)
    for i, ch in enumerate(after_scheme):
        if ch in "/?#":
            end = i
            break
    return after_scheme[:end]


def slug_for(registry_url: Optional[str]) -> str:
    """Compute the on-disk slug for a registry URL.

    ``None`` (a dev cartridge) → ``DEV_SLUG``. Non-None → a path-safe transform
    of the URL's authority: lowercased, with every character outside
    ``[a-z0-9.-]`` replaced by ``-``. Depends ONLY on the authority — path
    (incl. the version segment), query, trailing slash, and host case do not
    change it.
    """
    if registry_url is None:
        return DEV_SLUG
    out = []
    for ch in _authority_of(registry_url):
        # ASCII-lowercase only (matches Rust to_ascii_lowercase — non-ASCII
        # is left unchanged and then replaced, never kept).
        if "A" <= ch <= "Z":
            ch = ch.lower()
        if ("a" <= ch <= "z") or ("0" <= ch <= "9") or ch in ".-":
            out.append(ch)
        else:
            out.append("-")
    return "".join(out)


def _is_authority_char(c: str) -> bool:
    return ("a" <= c <= "z") or ("0" <= c <= "9") or c in ".-"


def is_registry_slug(s: str) -> bool:
    """True if ``s`` could be a valid slug for a non-dev registry: a non-empty
    path-safe authority string (``[a-z0-9.-]+``) that is not the dev sentinel.

    Used by host scanners to distinguish dev folders from registry folders
    before they read any cartridge.json.
    """
    if not s or s == DEV_SLUG:
        return False
    return all(_is_authority_char(c) for c in s)
