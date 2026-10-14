"""Cap definitions and registries the machine notation tests share.

A fixture is built through `definition`, which holds it to the definition
rules: a fixture that breaks one is not a fixture.
"""

from typing import List, Optional

from capdag.cap.definition import Cap, CapArg, CapOutput, CliFlagSource, StdinSource
from capdag.cap.registry import FabricRegistry
from capdag.cap.validation import validate_cap_definition
from capdag.fabric.registry import StoredMediaDef
from capdag.machine.graph import Machine, MachineEdge
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


def media(text: str) -> MediaUrn:
    return MediaUrn.from_string(text)


def canonical(text: str) -> str:
    """A media URN as the library writes it."""
    return MediaUrn.from_string(text).to_string()


def definition(cap_urn: str, title: str, args: List[CapArg], outputs: List[CapOutput]) -> Cap:
    cap = Cap.with_args(CapUrn.from_string(cap_urn), title, [title], list(args))
    cap.version = 1
    cap.set_outputs(outputs)
    validate_cap_definition(cap)
    return cap


def flag_arg(media_urn: str, name: str, is_sequence: bool = False) -> CapArg:
    return CapArg(media_urn, name, False, [CliFlagSource("--" + name)], is_sequence=is_sequence)


def stdin_arg(media_urn: str, name: str, is_sequence: bool = False) -> CapArg:
    return CapArg(media_urn, name, True, [StdinSource(media_urn)], is_sequence=is_sequence)


def output_of(media_urn: str, name: str, description: str = "", is_sequence: bool = False) -> CapOutput:
    return CapOutput(media_urn, name, description, is_sequence=is_sequence)


def stdin_cap(cap_urn: str, title: str, in_urn: str, out_urn: str) -> Cap:
    """A cap of one arg, its main input, and its one output."""
    return definition(
        cap_urn, title, [stdin_arg(in_urn, "input")], [output_of(out_urn, "output", title)]
    )


def media_def(media_urn: str, validation: Optional[dict] = None, schema=None) -> StoredMediaDef:
    return StoredMediaDef(
        urn=media_urn,
        media_type="application/json",
        title=media_urn,
        schema=schema,
        validation=validation,
    )


def registry_of(caps: List[Cap]) -> FabricRegistry:
    registry = FabricRegistry.new_for_test()
    registry.add_caps_to_cache(caps)
    return registry


def all_edges(machine: Machine) -> List[MachineEdge]:
    return [edge for strand in machine.strands() for edge in strand.edges()]


def edges_of(machine: Machine, step: str) -> List[MachineEdge]:
    """Every edge of the machine whose cap URN bears the tag `step`."""
    return [
        edge
        for edge in all_edges(machine)
        if step in edge.cap_urn.to_string()[len("cap:"):].split(";")
    ]


def one_edge_of(machine: Machine, step: str) -> MachineEdge:
    edges = edges_of(machine, step)
    assert len(edges) == 1, f"one {step} step, got {len(edges)}"
    return edges[0]
