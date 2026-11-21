"""Registry of value-based media URN refinements."""

from __future__ import annotations

from typing import List, Tuple

from capdag import _formal as model
from capdag.input_resolver.value_adapter import ValueAdapter, ValueAdapterError
from capdag.urn.media_urn import MediaUrn, MediaUrnError
from tagged_urn import TaggedUrnError


class ValueAdapterRegistry:
    """Value adapters, each registered under a media URN, its key: the type
    whose values it can refine. A base media URN is refined by the adapter
    chosen by inclusion, as the proved model chooses
    (``CapDAG.Detect.adapterFor``): of the adapters whose key the base falls
    under, the one registered for the most specific key. Two most specific
    keys neither of which refines the other are ambiguous, and refused."""

    def __init__(self) -> None:
        # Adapters by the key they are registered under, in registration order.
        self._adapters: List[Tuple[MediaUrn, ValueAdapter]] = []

    @staticmethod
    def _key(key: str) -> MediaUrn:
        try:
            return MediaUrn.from_string(key)
        except (TaggedUrnError, MediaUrnError) as e:
            raise ValueAdapterError("bad-key", f"value adapter key '{key}' is no media URN: {e}") from e

    def register(self, key: str, adapter: ValueAdapter) -> None:
        """Register a value adapter under ``key``, the media URN of the type
        whose values it refines. A key that is no media URN, or one equivalent
        to a registered key, is refused."""
        key_urn = self._key(key)
        for existing, _ in self._adapters:
            if existing.is_equivalent(key_urn):
                raise ValueAdapterError(
                    "duplicate-key",
                    f"value adapter key '{key_urn}' is equivalent to the registered key '{existing}'",
                )
        self._adapters.append((key_urn, adapter))

    def refine_media_urn(self, base: MediaUrn, value: str) -> MediaUrn:
        """Refine ``base``, the media URN an argument slot declares, by the
        value filling the slot.

        The adapter is the one chosen by inclusion. With none covering the
        base, or when the chosen adapter declines (``None``), the base is
        kept. A refinement must be a media URN that conforms to the base: the
        adapter says which of the base's values this one is, never something
        else."""
        keys = [k.inner().formal for k, _ in self._adapters]
        choice = model.adapter_for(keys, base.inner().formal)
        if isinstance(choice, model.AdapterChoiceUncovered):
            return base
        if isinstance(choice, model.AdapterChoiceAmbiguous):
            raise ValueAdapterError(
                "ambiguous",
                f"'{base}' falls under the value adapter keys '{self._adapters[choice.i][0]}' and "
                f"'{self._adapters[choice.j][0]}', neither of which refines the other",
            )
        if not isinstance(choice, model.AdapterChoiceOne):
            raise TypeError(f"adapter_for answered {choice!r}, no AdapterChoice")
        adapter = self._adapters[choice.i][1]
        result = adapter.refine(str(base), value)
        if result is None:
            return base
        try:
            refined = MediaUrn.from_string(result)
        except (TaggedUrnError, MediaUrnError) as e:
            raise ValueAdapterError(
                "bad-refinement",
                f"value adapter {adapter.name} refined '{base}' to '{result}', which is no media URN: {e}",
            ) from e
        if not refined.conforms_to(base):
            raise ValueAdapterError(
                "not-inside",
                f"value adapter {adapter.name} refined '{base}' to '{refined}', which does not conform to it",
            )
        return refined

    def has_adapter(self, key: str) -> bool:
        """Whether an adapter is registered under a key equivalent to ``key``.
        A key that is no media URN is refused."""
        key_urn = self._key(key)
        return any(k.is_equivalent(key_urn) for k, _ in self._adapters)

    def registered_keys(self) -> List[str]:
        """Every registered key, in canonical form and registration order."""
        return [str(k) for k, _ in self._adapters]
