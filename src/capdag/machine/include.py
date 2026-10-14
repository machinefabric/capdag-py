"""Machines in step position: where another machine's notation comes from,
and what a machine looks like to the machine that includes it.

A header ``alias machine "<reference>"`` names another machine. The reference
is an opaque string: the host resolves it through one interface,
``MachineSource``. The parser reads the referenced notation, resolves it on
its own, and writes its steps into the including machine with node positions
of their own (capdag/docs/09-machine-notation.md, §Machines in step position).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from capdag.planner.policy import StepPolicy
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn

if TYPE_CHECKING:
    from capdag.machine.graph import Machine


@dataclass(frozen=True)
class LoadedMachine:
    """The notation of one machine, as a ``MachineSource`` gives it."""

    #: What the source knows this machine by. Two references that resolve to
    #: one machine yield one id: it is what a circle of inclusions is
    #: recognized by, and what a reference written inside this machine is
    #: resolved relative to.
    id: str
    notation: str


class MachineSourceError(Exception):
    """Why a reference did not yield a machine."""

    def __init__(self, details: str = "", no_source: bool = False):
        #: The notation is being read with nothing to resolve references
        #: against. Otherwise the source holds no machine under the
        #: reference, and `details` says what it found.
        self.no_source = no_source
        self.details = details
        super().__init__(
            "there is nothing to resolve machine references against" if no_source else details
        )


class MachineSource:
    """Where the machines named in machine headers come from.

    A command line reads a reference as a path relative to the including file
    (``FileMachineSource``); an engine reads it from its machine store.
    """

    def load(self, reference: str, including: Optional[str]) -> LoadedMachine:
        """The machine ``reference`` names. ``including`` is the id of the
        machine whose header wrote it — None when that machine has none
        (notation that came from no place the source knows). Raises
        ``MachineSourceError`` when the reference yields no machine."""
        raise NotImplementedError


class NoMachineSource(MachineSource):
    """The source of a host that resolves no references. A machine header
    read against it is refused."""

    def load(self, reference: str, including: Optional[str]) -> LoadedMachine:
        raise MachineSourceError(no_source=True)


def file_machine_id(path) -> str:
    """The id a ``FileMachineSource`` gives the machine in the file at
    ``path``: what to name the including machine by, so that its own
    references are read relative to it and an inclusion of it is recognized.
    Raises ``MachineSourceError`` when the path names no file."""
    try:
        return os.path.realpath(os.fspath(path), strict=True)
    except OSError as error:
        raise MachineSourceError(f"{path}: {error}") from error


class FileMachineSource(MachineSource):
    """Machines in files. A reference is a path: relative to the directory of
    the including file, or to the base when the including machine came from
    no file. A machine's id is its file's canonical path."""

    def __init__(self, base):
        #: What references written in notation that came from no file are
        #: read relative to.
        self._base = os.fspath(base)

    def load(self, reference: str, including: Optional[str]) -> LoadedMachine:
        directory = self._base if including is None else os.path.dirname(including)
        path = os.path.join(directory, reference)
        machine_id = file_machine_id(path)
        try:
            with open(path, encoding="utf-8") as handle:
                notation = handle.read()
        except (OSError, UnicodeDecodeError) as error:
            raise MachineSourceError(f"{path}: {error}") from error
        return LoadedMachine(id=machine_id, notation=notation)


class MapMachineSource(MachineSource):
    """Machines in memory, each under the reference that names it. A
    reference names the same machine wherever it is written. For a host that
    loads the machines a notation refers to before it parses, and for
    tests."""

    def __init__(self) -> None:
        self._machines: Dict[str, str] = {}

    def insert(self, reference: str, notation: str) -> None:
        """Hold ``notation`` under ``reference``."""
        self._machines[reference] = notation

    def load(self, reference: str, including: Optional[str]) -> LoadedMachine:
        if reference not in self._machines:
            raise MachineSourceError(f'no machine is held under "{reference}"')
        return LoadedMachine(id=reference, notation=self._machines[reference])


@dataclass(frozen=True)
class IncludedValue:
    """What a member of an included step gives its arg: a node of the included
    machine, by the name its notation wrote, or a constant."""

    is_constant: bool
    node: str = ""
    constant: Any = None


@dataclass
class IncludedStep:
    """One step of an included machine, with every member under the name of
    the arg its own resolution bound it to and every target under the name of
    the output it takes. Written into another machine, it binds what it bound
    alone: nothing about where it is included can change it."""

    cap_urn: CapUrn
    policy: StepPolicy
    #: The arg's name and what it is given.
    members: List[Tuple[str, IncludedValue]] = field(default_factory=list)
    #: The output's name and the node that takes it.
    targets: List[Tuple[str, str]] = field(default_factory=list)
    #: The machine steps this step was already included through inside the
    #: included machine, outermost first.
    included_as: List[str] = field(default_factory=list)


@dataclass
class IncludedMachine:
    """A machine as the machine that includes it sees it: its inputs and
    outputs, by the names its notation wrote, and its steps."""

    #: Every input anchor, by name, with the media it holds. In the order of
    #: the machine's strands, by name within one.
    inputs: List[Tuple[str, MediaUrn]] = field(default_factory=list)
    outputs: List[Tuple[str, MediaUrn]] = field(default_factory=list)
    #: Every node, by name, with the media it holds in the machine as it
    #: resolved alone.
    node_media: List[Tuple[str, MediaUrn]] = field(default_factory=list)
    steps: List[IncludedStep] = field(default_factory=list)

    def input_names(self) -> List[str]:
        return [name for name, _ in self.inputs]

    def output_names(self) -> List[str]:
        return [name for name, _ in self.outputs]

    def input(self, name: str) -> Optional[MediaUrn]:
        """The media the input of that name holds, or None."""
        return _media_named(self.inputs, name)

    def output(self, name: str) -> Optional[MediaUrn]:
        """The media the output of that name holds, or None."""
        return _media_named(self.outputs, name)


def _media_named(held: List[Tuple[str, MediaUrn]], name: str) -> Optional[MediaUrn]:
    for each, media in held:
        if each == name:
            return media
    return None


def included_machine_of(machine: "Machine", names: List[Dict[str, int]]) -> IncludedMachine:
    """Read a resolved machine, with the names its notation wrote
    (``names[i]`` maps a node name of strand ``i`` to its NodeId)."""
    included = IncludedMachine()
    for strand_index, strand in enumerate(machine.strands()):
        name_of = {node_id: name for name, node_id in names[strand_index].items()}

        def name(node_id: int) -> str:
            if node_id not in name_of:
                raise AssertionError("the parser names every node of a strand it resolved")
            return name_of[node_id]

        def anchors(ids) -> List[Tuple[str, MediaUrn]]:
            return sorted(
                ((name(node_id), strand.node_urn(node_id)) for node_id in ids),
                key=lambda held: held[0],
            )

        included.node_media.extend(anchors(range(len(strand.nodes()))))
        included.inputs.extend(anchors(strand.input_anchor_ids()))
        included.outputs.extend(anchors(strand.output_anchor_ids()))
        for edge in strand.edges():
            step = IncludedStep(
                cap_urn=edge.cap_urn,
                policy=edge.policy,
                included_as=list(edge.included_as),
            )
            for binding in edge.assignment:
                if binding.source.is_constant:
                    value = IncludedValue(is_constant=True, constant=binding.source.constant)
                else:
                    value = IncludedValue(is_constant=False, node=name(binding.source.node))
                step.members.append((binding.arg_name, value))
            for output in edge.outputs:
                step.targets.append((output.output_name, name(output.node)))
            included.steps.append(step)
    return included
