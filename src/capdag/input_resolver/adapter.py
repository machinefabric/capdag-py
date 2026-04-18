"""Interfaces for cartridge-backed content inspection adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol


class CartridgeAdapterInvoker(Protocol):
    """Invokes a cartridge's adapter-selection capability for a file."""

    async def invoke_adapter_selection(
        self,
        cartridge_id: str,
        file_path: Path,
    ) -> Optional[list[str]]:
        """Return confirmed media URNs for the file, or `None` for no match."""

