"""Cartridge registry slug — deterministic mapping from a registry
URL to a top-level folder name under the cartridges install root.

Mirrors capdag::cartridge_slug byte-for-byte: SHA-256 of the URL
bytes, lowercase hex, first 16 chars. The literal string "dev" is
reserved for dev cartridges that have no registry — by length alone
(3 != 16) it can never collide with a hex slug.

The mapping is one-way: folder → URL is recovered from each
installed cartridge's own ``cartridge.json:registry_url``. The host
validates ``slug_for(cartridge_json.registry_url) == folder_name``
at parse time.
"""

import hashlib
import string
from typing import Optional

#: Reserved folder name for cartridges with no registry. The
#: four-character literal can never collide with a 16-character hex
#: slug — distinguishable by length alone.
DEV_SLUG = "dev"

#: Number of hex characters in a registry slug. 16 chars = 64 bits =
#: ~10^19 possible values; collision probability across thousands of
#: registries is astronomically low.
SLUG_HEX_LEN = 16


def slug_for(registry_url: Optional[str]) -> str:
    """Compute the on-disk slug for a registry URL.

    ``None`` (i.e. a dev cartridge) → returns ``DEV_SLUG``.
    Non-None → returns the first ``SLUG_HEX_LEN`` hex characters of
    ``sha256(registry_url.encode())``, lowercase.

    The URL is hashed verbatim. Two URLs that differ in any byte
    (case, trailing slash, port, path, query) hash to different
    slugs — that's intentional, because the URL is the registry's
    identity and the installer treats it as opaque.
    """
    if registry_url is None:
        return DEV_SLUG
    digest = hashlib.sha256(registry_url.encode("utf-8")).hexdigest()
    return digest[:SLUG_HEX_LEN]


_HEX_LOWER = set(string.hexdigits.lower())


def is_registry_slug(s: str) -> bool:
    """True if ``s`` could be a valid slug for a non-dev registry.

    Used by host scanners to distinguish dev folders from registry
    folders before they read any cartridge.json.
    """
    if len(s) != SLUG_HEX_LEN:
        return False
    return all(c in _HEX_LOWER for c in s)
