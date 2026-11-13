"""Registry of cartridge-provided content inspection adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from tagged_urn import TaggedUrnError

from capdag.fabric.registry import FabricRegistry, ParseError
from capdag.urn.media_urn import MediaUrn, MediaUrnError

_log = logging.getLogger(__name__)


class AdapterRegistrationError(Exception):
    """Raised when adapter registration would create an ambiguity."""

    def __init__(
        self,
        group_name: str,
        new_adapter_urn: str,
        existing_adapter_urn: str,
        existing_group_name: str,
        existing_cartridge_id: str,
    ) -> None:
        self.group_name = group_name
        self.new_adapter_urn = new_adapter_urn
        self.existing_adapter_urn = existing_adapter_urn
        self.existing_group_name = existing_group_name
        self.existing_cartridge_id = existing_cartridge_id
        super().__init__(
            f"Cap group '{group_name}' rejected: adapter URN '{new_adapter_urn}' conflicts "
            f"with '{existing_adapter_urn}' (registered by group '{existing_group_name}' in "
            f"cartridge '{existing_cartridge_id}'). One conforms to the other, creating ambiguity."
        )


@dataclass(frozen=True)
class RegisteredAdapter:
    media_urn: MediaUrn
    urn_string: str
    group_name: str
    cartridge_id: str


class MediaAdapterRegistry:
    """Tracks cartridge-provided content inspection adapters."""

    def __init__(self, fabric_registry: FabricRegistry) -> None:
        self._fabric_registry = fabric_registry
        self._registered_adapters: list[RegisteredAdapter] = []

    @property
    def fabric_registry(self) -> FabricRegistry:
        return self._fabric_registry

    def register_cap_group(
        self,
        group_name: str,
        adapter_urn_strs: list[str],
        cartridge_id: str,
    ) -> None:
        """Register a cap group's adapter URNs (atomic; ambiguity rejects the group).

        Exact re-registration is IDEMPOTENT: an adapter URN equivalent to one
        this same (cartridge_id, group_name) already registered is neither a
        conflict nor a second row — a cartridge attached through more than one
        hosting route (e.g. app-bundled and system-installed) is still one
        adapter provider, not an ambiguity with itself. The skip is logged.
        """
        new_adapters = [
            (MediaUrn.from_string(urn_str), urn_str)
            for urn_str in adapter_urn_strs
        ]

        # Which new adapters are exact re-registrations by the same owner —
        # skipped in the conflict scan AND in the final insert, so repeated
        # attachment of the same cartridge stays a no-op instead of either
        # refusing (self-conflict) or duplicating rows.
        already_registered: list[bool] = []
        for new_urn, new_str in new_adapters:
            dup = any(
                existing.cartridge_id == cartridge_id
                and existing.group_name == group_name
                and existing.media_urn.is_equivalent(new_urn)
                for existing in self._registered_adapters
            )
            if dup:
                _log.warning(
                    "Adapter URN '%s' of cap group '%s' is already registered by "
                    "cartridge '%s' — the cartridge is attached through more than "
                    "one hosting route; keeping the first registration and "
                    "skipping this one",
                    new_str,
                    group_name,
                    cartridge_id,
                )
            already_registered.append(dup)

        for (new_urn, new_str), is_rereg in zip(new_adapters, already_registered):
            if is_rereg:
                continue
            for existing in self._registered_adapters:
                if new_urn.conforms_to(existing.media_urn) or existing.media_urn.conforms_to(new_urn):
                    raise AdapterRegistrationError(
                        group_name=group_name,
                        new_adapter_urn=new_str,
                        existing_adapter_urn=existing.urn_string,
                        existing_group_name=existing.group_name,
                        existing_cartridge_id=existing.cartridge_id,
                    )

        for index, (a_urn, a_str) in enumerate(new_adapters):
            for b_urn, b_str in new_adapters[index + 1:]:
                if a_urn.conforms_to(b_urn) or b_urn.conforms_to(a_urn):
                    raise AdapterRegistrationError(
                        group_name=group_name,
                        new_adapter_urn=a_str,
                        existing_adapter_urn=b_str,
                        existing_group_name=group_name,
                        existing_cartridge_id=cartridge_id,
                    )

        for (media_urn, urn_string), is_rereg in zip(new_adapters, already_registered):
            if is_rereg:
                continue
            self._registered_adapters.append(
                RegisteredAdapter(
                    media_urn=media_urn,
                    urn_string=urn_string,
                    group_name=group_name,
                    cartridge_id=cartridge_id,
                )
            )

    async def _extension_candidates(self, ext: str) -> list[MediaUrn]:
        """The file media types the fabric declares for an extension, parsed.
        A definition whose URN does not parse is a ParseError naming it."""
        defs = await self._fabric_registry.file_media_for_extension(ext)
        candidates: list[MediaUrn] = []
        for d in defs:
            try:
                candidates.append(MediaUrn.from_string(d.urn))
            except (TaggedUrnError, MediaUrnError) as e:
                raise ParseError(
                    f"the fabric's media definition '{d.urn}' has no valid URN: {e}"
                ) from e
        return candidates

    async def find_adapters_for_extension(self, ext: str) -> list[tuple[str, MediaUrn]]:
        """The adapters that cover a file media type the fabric declares for
        ``ext``, one per cartridge, as ``(cartridge_id, adapter_media_urn)``
        pairs. The fabric's file types that cannot be loaded raise the
        registry's error."""
        return self.adapters_for_candidates(await self._extension_candidates(ext))

    def adapters_for_candidates(self, candidates: Sequence[MediaUrn]) -> list[tuple[str, MediaUrn]]:
        """The registered adapters some of these candidates conform to, one
        per cartridge, as ``(cartridge_id, adapter_media_urn)`` pairs."""
        results: list[tuple[str, MediaUrn]] = []
        seen_cartridges: set[str] = set()
        for registered in self._registered_adapters:
            matches = any(candidate.conforms_to(registered.media_urn) for candidate in candidates)
            if matches and registered.cartridge_id not in seen_cartridges:
                seen_cartridges.add(registered.cartridge_id)
                results.append((registered.cartridge_id, registered.media_urn))
        return results

    def adapters_for(self, candidates: Sequence[MediaUrn]) -> list[tuple[str, MediaUrn]]:
        """The host's adapters as detection consults them
        (:class:`~capdag.input_resolver.detection.AdapterSource`)."""
        return self.adapters_for_candidates(candidates)

    async def has_adapter_for_extension(self, ext: str) -> bool:
        """Whether any registered adapter covers a file media type the fabric
        declares for ``ext``."""
        candidates = await self._extension_candidates(ext)
        return any(
            candidate.conforms_to(registered.media_urn)
            for registered in self._registered_adapters
            for candidate in candidates
        )
