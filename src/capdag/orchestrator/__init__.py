"""Orchestrator module — machine notation parsing, DAG validation, plan conversion, and CBOR utilities.

Mirrors Rust's orchestrator module. Provides:
- Route notation → validated ResolvedGraph (parse_machine_to_cap_dag)
- MachinePlan → ResolvedGraph (plan_to_resolved_graph)
- DAG cycle detection (validate_dag)
- CBOR array/sequence splitting and assembly
"""

from capdag.orchestrator.types import (
    ParseOrchestrationError,
    MachineSyntaxParseFailedError,
    CapNotFoundError,
    NodeMediaConflictError,
    NotADagError,
    InvalidGraphError,
    CapUrnParseError,
    MediaUrnParseError,
    RegistryError,
    StructureMismatchError,
    ResolvedEdge,
    ResolvedGraph,
    CapRegistryTrait,
)

from capdag.orchestrator.validation import validate_dag

from capdag.orchestrator.parser import parse_machine_to_cap_dag

from capdag.orchestrator.plan_converter import plan_to_resolved_graph

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
)

__all__ = [
    # Error types
    "ParseOrchestrationError",
    "MachineSyntaxParseFailedError",
    "CapNotFoundError",
    "NodeMediaConflictError",
    "NotADagError",
    "InvalidGraphError",
    "CapUrnParseError",
    "MediaUrnParseError",
    "RegistryError",
    "StructureMismatchError",
    # Data types
    "ResolvedEdge",
    "ResolvedGraph",
    # Trait
    "CapRegistryTrait",
    # Validation
    "validate_dag",
    # Parser
    "parse_machine_to_cap_dag",
    # Plan converter
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
]
