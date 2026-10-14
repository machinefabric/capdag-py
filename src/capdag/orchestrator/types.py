"""Orchestrator types — the errors of turning a plan into steps, and the
steps themselves.

Mirrors the reference's ``orchestrator/types.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from capdag.cap.definition import Cap
from capdag.planner.live_cap_fab import StepToken
from capdag.planner.policy import StepPolicy


# --- Error hierarchy ---

class ParseOrchestrationError(Exception):
    """Base class for all orchestration errors."""
    pass


class CapNotFoundError(ParseOrchestrationError):
    """A cap URN is not in the registry."""

    def __init__(self, cap_urn: str) -> None:
        self.cap_urn = cap_urn
        super().__init__(f"Cap URN '{cap_urn}' not found in registry")


class InvalidGraphError(ParseOrchestrationError):
    """The plan or graph is not one that can be run as asked."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Invalid graph: {message}")


# --- Data types ---

@dataclass(frozen=True)
class StepSource:
    """What one input of a step is sent: one node's value as it is
    (:meth:`of_node`), or several nodes' values gathered, in order, into one
    sequence (:meth:`gather`) — a single value contributes one item, a
    sequence its items. A gather with no members is an empty sequence."""

    #: Which of the two this is.
    is_gather: bool
    #: The nodes read, in order: the one node, or the gather's members.
    members: Tuple[str, ...]

    @staticmethod
    def of_node(node: str) -> "StepSource":
        """The source that sends one node's value as it is."""
        return StepSource(is_gather=False, members=(node,))

    @staticmethod
    def gather(members: List[str]) -> "StepSource":
        """The source that gathers ``members``, in order."""
        return StepSource(is_gather=True, members=tuple(members))

    @property
    def node(self) -> str:
        """The node whose value is sent, when this is not a gather."""
        if self.is_gather:
            raise ValueError("a gather is several nodes, not one")
        return self.members[0]

    def nodes(self) -> List[str]:
        """Every node this source reads, in order."""
        return list(self.members)


@dataclass(frozen=True)
class StepInput:
    """One input stream of a step."""

    #: The URN the stream is delivered under: the cap's ``in=`` for its main
    #: input, the arg's stream URN for any other. A cartridge tells its
    #: inputs apart by this.
    stream_urn: str
    source: StepSource


@dataclass(frozen=True)
class StepOutput:
    """An output of a step other than its main one that something takes."""

    #: The output's media URN in the cap's definition: what its response
    #: stream names.
    output_media_urn: str
    #: The node its value is stored at.
    node: str


@dataclass
class ResolvedStep:
    """One step of a resolved graph: one invocation of a cap."""

    #: Stable per-step identity carried from the originating strand step (via
    #: the plan's Cap node). The key by which a run's live progress maps back
    #: to the graph element a client rendered.
    token_id: StepToken
    #: The step's node: where its MAIN output is stored.
    node: str
    #: Cap URN string.
    cap_urn: str
    #: Resolved cap definition.
    cap: Cap
    #: The streams the step is sent, besides the values its args are given by
    #: the run. None for a step nothing is wired into.
    inputs: List[StepInput]
    #: The outputs other than the main one that something takes.
    outputs: List[StepOutput]
    #: The media URN of the main output, from the cap definition.
    out_media: str
    #: What the step does when it fails.
    policy: StepPolicy = field(default_factory=StepPolicy)

    def source_nodes(self) -> List[str]:
        """Every node the step reads, in input order."""
        return [node for step_input in self.inputs for node in step_input.source.nodes()]

    def produced_nodes(self) -> List[str]:
        """Every node the step produces: its own, then its other taken
        outputs'."""
        return [self.node] + [output.node for output in self.outputs]


@dataclass
class ResolvedGraph:
    """Steps with the cap definitions they run, wired by the nodes they read
    and produce. A node no step of the graph produces is an input of the
    graph: its value is supplied when the graph is run."""

    #: Map from node name to the media URN it holds.
    nodes: Dict[str, str]
    #: The steps, in the order they were asked for.
    steps: List[ResolvedStep]
    #: The name of the plan the graph came from.
    graph_name: Optional[str] = None
