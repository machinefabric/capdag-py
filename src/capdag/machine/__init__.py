"""Machine notation — strand-based DAG representation for capability pipelines.

Machine notation replaces the DOT file format for describing capability
transformation paths. It provides:

- A strand-based, anchor-realized graph model with semantic equivalence
- A compact textual format for serialization
- Resolution via FabricRegistry for source-to-arg bipartite matching

Format:

    [extract cap:in="media:pdf";extract-text;out="media:enc=utf-8;ext=txt"]
    [embed cap:in="media:enc=utf-8";generate-embeddings;out="media:embedding-vector;enc=utf-8;record"]
    [doc -> extract -> text]
    [text -> embed -> vectors]

Statements are enclosed in [...]. Two kinds:
- Headers: [alias cap:...] — define a capability with an alias
- Wirings: [src -> alias -> dst] — connect nodes through capabilities

Fan-in groups: [(a, b) -> alias -> dst] — multiple sources feed one cap.
Loop edges: [src -> LOOP alias -> dst] — ForEach iteration semantics.
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
)
from capdag.machine.graph import (
    NodeId,
    EdgeAssignmentBinding,
    MachineEdge,
    MachineStrand,
    Machine,
)
from capdag.machine.parser import parse_machine

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
    # Graph types
    "NodeId",
    "EdgeAssignmentBinding",
    "MachineEdge",
    "MachineStrand",
    "Machine",
    # Parser
    "parse_machine",
]
