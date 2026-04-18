"""Registry of value-based media URN refinements."""

from __future__ import annotations

from capdag.input_resolver.value_adapter import ValueAdapter


class ValueAdapterRegistry:
    """Registers adapters keyed by their base media URN prefixes."""

    def __init__(self) -> None:
        self._adapters: dict[str, ValueAdapter] = {}

    def register(self, base_media_urn: str, adapter: ValueAdapter) -> None:
        self._adapters[base_media_urn] = adapter

    def refine_media_urn(self, base_media_urn: str, value: str) -> str:
        matching_prefixes = [
            prefix for prefix in self._adapters
            if base_media_urn == prefix or base_media_urn.startswith(f"{prefix};")
        ]
        if not matching_prefixes:
            return base_media_urn

        prefix = max(matching_prefixes, key=len)
        refined = self._adapters[prefix].refine(base_media_urn, value)
        return refined if refined is not None else base_media_urn

    def has_adapter(self, base_media_urn: str) -> bool:
        return base_media_urn in self._adapters

