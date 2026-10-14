"""Machine notation — strand-based DAG representation for capability pipelines.

Machine notation describes capability transformation paths. It provides:

- A strand-based, anchor-realized graph model with semantic equivalence
- A compact textual format for serialization
- Resolution via FabricRegistry for binding a wiring's members to cap args

Format (capdag/docs/09-machine-notation.md)::

    [extract cap:in="media:document;ext=pdf";extract-text;out="media:enc=utf-8;ext=txt"]
    [embed cap:in="media:enc=utf-8";generate-embeddings;out="media:embedding-vector;enc=utf-8;record"]
    [doc -> extract -> text]
    [text -> embed -> vectors]

Statements may be enclosed in ``[...]`` or written one per line. Three kinds:

- Cap headers: ``alias cap:...`` — give a cap an alias
- Machine headers: ``alias machine "reference"`` — another machine, usable as
  a step
- Wirings: ``sources -> step -> targets`` — one invocation

A wiring's members may name the arg they are for and may be constants; its
step may carry a policy; its targets may name the output they take::

    (path, benchmark=bench) -> compare -> result
    (prices, window=20) -> rolling{retry=3} -> (smooth, tail=rest)
    () -> now -> stamp
    report -> publish -> ()

Per-item mapping is never authored in notation: it is DERIVED from
cardinality — a sequence bound to an arg that takes one value makes the
resolved edge a per-item map (``MachineEdge.is_loop``).
"""

from capdag.machine.error import (
    AliasNotACapError,
    AmbiguousMachineMembersError,
    AmbiguousMachineNotationError,
    ArgBoundTwiceError,
    CapDoesNotDeclareInputError,
    ConstantFailsValidationError,
    CyclicMachineReferenceError,
    CyclicMachineStrandError,
    DisconnectedStrandError,
    DuplicateAliasError,
    EmptyMachineError,
    InvalidCapUrnError,
    InvalidIncludedMachineError,
    InvalidMediaUrnError,
    InvalidPolicyError,
    MachineAbstractionError,
    MachineInputBindingError,
    MachineOutputTakenTwiceError,
    MachineParseError,
    MachineReferenceWithoutSourceError,
    MachineSyntaxError,
    MainInputUnboundError,
    NoCapabilityStepsError,
    NodeAliasCollisionError,
    NodeMediaConflictError,
    UncachedCapError,
    UncachedMediaDefError,
    NoEdgesError,
    NoMainOutputError,
    OutputTakenTwiceError,
    ParseError,
    PolicyOnMachineError,
    ReservedNodeNameError,
    RuntimeMediaInferenceError,
    SeveralUnnamedTargetsError,
    SourceDoesNotConformToArgError,
    SourceDoesNotConformToMachineInputError,
    UndecidedMember,
    UndefinedAliasError,
    UnknownArgNameError,
    UnknownCapError,
    UnknownMachineInputError,
    UnknownMachineOutputError,
    UnknownMachineReferenceError,
    UnknownOutputNameError,
    UnmatchedMachineMemberError,
    UnmatchedSourceInCapArgsError,
    UnnamedConstantError,
    UnnamedMachineTargetError,
    UntypedMachineInputError,
    UntypedMachineMemberError,
)
from capdag.machine.graph import (
    BindingSource,
    EdgeAssignmentBinding,
    EdgeOutput,
    Machine,
    MachineEdge,
    MachineStrand,
    NodeId,
)
from capdag.machine.include import (
    FileMachineSource,
    LoadedMachine,
    MachineSource,
    MachineSourceError,
    MapMachineSource,
    NoMachineSource,
    file_machine_id,
)
from capdag.machine.iteration import (
    SCOPE_ROOT,
    CyclicSteps,
    IterationStructure,
    MemberShape,
    OutputShape,
    StepPlacement,
    StepShape,
    iteration_of,
)
from capdag.machine.parser import (
    parse_machine,
    parse_machine_with_node_names,
    parse_machine_with_sources,
)
from capdag.machine.serializer import (
    FORMAT_BRACKETED,
    FORMAT_LINE_BASED,
    strand_to_machine_notation,
)
from capdag.planner.policy import ON_ERROR_ABSENT, ON_ERROR_FAIL, StepPolicy

__all__ = [
    # Errors
    "MachineSyntaxError",
    "MachineAbstractionError",
    "MachineParseError",
    "EmptyMachineError",
    "InvalidCapUrnError",
    "UndefinedAliasError",
    "AliasNotACapError",
    "DuplicateAliasError",
    "InvalidMediaUrnError",
    "NoEdgesError",
    "NodeAliasCollisionError",
    "ParseError",
    "MachineReferenceWithoutSourceError",
    "UnnamedConstantError",
    "ReservedNodeNameError",
    "SeveralUnnamedTargetsError",
    "InvalidPolicyError",
    "UndecidedMember",
    "NoCapabilityStepsError",
    "UnknownCapError",
    "UnmatchedSourceInCapArgsError",
    "AmbiguousMachineNotationError",
    "CyclicMachineStrandError",
    "RuntimeMediaInferenceError",
    "CapDoesNotDeclareInputError",
    "DisconnectedStrandError",
    "UnknownArgNameError",
    "UnknownOutputNameError",
    "SourceDoesNotConformToArgError",
    "ConstantFailsValidationError",
    "ArgBoundTwiceError",
    "MainInputUnboundError",
    "OutputTakenTwiceError",
    "NoMainOutputError",
    "UntypedMachineInputError",
    "UnknownMachineReferenceError",
    "CyclicMachineReferenceError",
    "InvalidIncludedMachineError",
    "PolicyOnMachineError",
    "UnknownMachineInputError",
    "UnknownMachineOutputError",
    "MachineInputBindingError",
    "MachineOutputTakenTwiceError",
    "UnnamedMachineTargetError",
    "UntypedMachineMemberError",
    "UnmatchedMachineMemberError",
    "AmbiguousMachineMembersError",
    "SourceDoesNotConformToMachineInputError",
    "NodeMediaConflictError",
    "UncachedCapError",
    "UncachedMediaDefError",
    # Graph types
    "NodeId",
    "BindingSource",
    "EdgeAssignmentBinding",
    "EdgeOutput",
    "MachineEdge",
    "MachineStrand",
    "Machine",
    # Step policy
    "StepPolicy",
    "ON_ERROR_FAIL",
    "ON_ERROR_ABSENT",
    # Machines in step position
    "MachineSource",
    "MachineSourceError",
    "LoadedMachine",
    "NoMachineSource",
    "FileMachineSource",
    "MapMachineSource",
    "file_machine_id",
    # Iteration
    "SCOPE_ROOT",
    "CyclicSteps",
    "IterationStructure",
    "MemberShape",
    "OutputShape",
    "StepPlacement",
    "StepShape",
    "iteration_of",
    # Parser
    "parse_machine",
    "parse_machine_with_node_names",
    "parse_machine_with_sources",
    # Serializer
    "FORMAT_BRACKETED",
    "FORMAT_LINE_BASED",
    "strand_to_machine_notation",
]
