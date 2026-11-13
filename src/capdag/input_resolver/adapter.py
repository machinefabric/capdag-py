"""Interfaces for cartridge-backed content inspection adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol

#: How much of a file content inspection reads: the content a definition's
#: validation rules are evaluated against is at most this many bytes from the
#: start of the file.
MAX_CONTENT_INSPECTION_BYTES = 100 * 1024


class CartridgeAdapterInvoker(Protocol):
    """Invokes a cartridge's adapter-selection capability for a file."""

    async def invoke_adapter_selection(
        self,
        cartridge_id: str,
        file_path: Path,
    ) -> Optional[list[str]]:
        """Return the media URNs the cartridge claims the file as, or ``None``
        when it declines. A cartridge whose inspection fails raises
        :class:`~capdag.input_resolver.types.InputResolverError`."""
