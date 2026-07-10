"""Machine notation — strand-based DAG representation for capability pipelines.

Machine notation replaces the DOT file format for describing capability
transformation paths. It provides:

- A strand-based, anchor-realized graph model with semantic equivalence
- A compact textual format for serialization
- Resolution via FabricRegistry for source-to-arg bipartite matching

Format:

    [extract cap:in="media:ext=pdf";extract-text;out="media:enc=utf-8;ext=txt"]
    [embed cap:in="media:enc=utf-8";generate-embeddings;out="media:embedding-vector;enc=utf-8;record"]
    [doc -> extract -> text]
    [text -> embed -> vectors]

Statements are enclosed in [...]. Two kinds:
- Headers: [alias cap:...] — define a capability with an alias
- Wirings: [src -> alias -> dst] — connect nodes through capabilities

Fan-in groups: [(a, b) -> alias -> dst] — multiple sources feed one cap.

Per-item mapping (ForEach) is never authored in notation: it is DERIVED
from cardinality — a sequence-producing cap feeding a scalar-input cap
makes the resolved edge a per-item map (MachineEdge.is_loop). The retired
`LOOP` keyword has no grammar surface any more.
"""

from capdag.machine.error import (
    MachineSyntaxError,
    MachineAbstractionError,
    MachineParseError,
    NoCapabilityStepsError,
    UnknownCapError,
    UnmatchedSourceInCapArgsError,
    AmbiguousMachineNotationError,
    CyclicMachineStrandError,
    RuntimeMediaInferenceError,
    CapDoesNotDeclareInputError,
    NoStdinBindingError,
    NonProducerSecondaryArgError,
    DisconnectedStrandError,
)
from capdag.machine.graph import (
    NodeId,
    EdgeAssignmentBinding,
    MachineEdge,
    MachineStrand,
    Machine,
)
from capdag.machine.parser import parse_machine
from capdag.machine.realize import realize_strand

# Import serializer to attach to_machine_notation methods to Machine.
import capdag.machine.serializer as _serializer  # noqa: F401

__all__ = [
    # Errors
    "MachineSyntaxError",
    "MachineAbstractionError",
    "MachineParseError",
    "NoCapabilityStepsError",
    "UnknownCapError",
    "UnmatchedSourceInCapArgsError",
    "AmbiguousMachineNotationError",
    "CyclicMachineStrandError",
    "RuntimeMediaInferenceError",
    "CapDoesNotDeclareInputError",
    "NoStdinBindingError",
    "NonProducerSecondaryArgError",
    "DisconnectedStrandError",
    # Graph types
    "NodeId",
    "EdgeAssignmentBinding",
    "MachineEdge",
    "MachineStrand",
    "Machine",
    # Parser
    "parse_machine",
    # Realize
    "realize_strand",
]
