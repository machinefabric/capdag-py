"""Orchestrator module — plan conversion and CBOR utilities.

Mirrors the reference's orchestrator module. Provides:
- the steps of a MachinePlan as a ResolvedGraph (steps_to_resolved_graph,
  plan_to_resolved_graph)
- CBOR array/sequence splitting and assembly
- how a run's progress maps into the range of its part
"""

from capdag.orchestrator.types import (
    ParseOrchestrationError,
    CapNotFoundError,
    InvalidGraphError,
    StepSource,
    StepInput,
    StepOutput,
    ResolvedStep,
    ResolvedGraph,
)

from capdag.orchestrator.plan_converter import (
    steps_to_resolved_graph,
    plan_to_resolved_graph,
)

from capdag.orchestrator.cbor_util import (
    CborUtilError,
    CborDeserializeError,
    CborNotAnArrayError,
    CborSerializeError,
    CborEmptyArrayError,
    split_cbor_array,
    assemble_cbor_array,
    split_cbor_sequence,
    assemble_cbor_sequence,
    wrap_raw_items_as_cbor_sequence,
)

from capdag.orchestrator.executor import (
    CapProgressFn,
    map_progress,
    ProgressMapper,
)

__all__ = [
    # Error types
    "ParseOrchestrationError",
    "CapNotFoundError",
    "InvalidGraphError",
    # Data types
    "StepSource",
    "StepInput",
    "StepOutput",
    "ResolvedStep",
    "ResolvedGraph",
    # Plan converter
    "steps_to_resolved_graph",
    "plan_to_resolved_graph",
    # CBOR utilities
    "CborUtilError",
    "CborDeserializeError",
    "CborNotAnArrayError",
    "CborSerializeError",
    "CborEmptyArrayError",
    "split_cbor_array",
    "assemble_cbor_array",
    "split_cbor_sequence",
    "assemble_cbor_sequence",
    "wrap_raw_items_as_cbor_sequence",
    # Progress mapping
    "CapProgressFn",
    "map_progress",
    "ProgressMapper",
]
