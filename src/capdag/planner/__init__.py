"""Planner module — execution plan construction and shape analysis

This module provides the planning infrastructure for machines:

- Cardinality and structure analysis (MediaShape, InputCardinality, InputStructure)
- Argument binding and resolution
- Collection input management
- Execution plan data structures (MachinePlan, MachineNode, MachinePlanEdge)
- Plan building from resolved paths
- Plan execution with topological ordering
- Live capability graph for path finding
"""

from capdag.planner.error import (
    PlannerError,
    InvalidInputError,
    InternalError,
    NotFoundError,
    RegistryError,
    ExecutionError,
    InvalidPathError,
)

from capdag.planner.cardinality import (
    InputCardinality,
    CardinalityCompatibility,
    InputStructure,
    StructureCompatibility,
    MediaShape,
    ShapeCompatibility,
    CapShapeInfo,
    CardinalityPattern,
    StrandShapeAnalysis,
)

from capdag.planner.live_cap_graph import (
    LiveMachinePlanEdgeType,
    LiveMachinePlanEdge,
    LiveCapGraph,
    StrandStepType,
    StrandStep,
    Strand,
    ReachableTargetInfo,
)

from capdag.planner.argument_binding import (
    SourceEntityType,
    CapFileMetadata,
    CapInputFile,
    ArgumentSource,
    ArgumentBinding,
    ResolvedArgument,
    ArgumentResolutionContext,
    ArgumentBindings,
    StrandInput,
    resolve_binding,
)

from capdag.planner.collection_input import (
    CollectionFile,
    CapInputCollection,
)

from capdag.planner.plan import (
    ExecutionNodeType,
    MergeStrategy,
    MachineNode,
    EdgeType,
    MachinePlanEdge,
    MachinePlan,
    NodeExecutionResult,
    MachineResult,
)

from capdag.planner.plan_builder import (
    ArgumentResolution,
    ArgumentInfo,
    StepArgumentRequirements,
    PathArgumentRequirements,
    MachinePlanBuilder,
)

from capdag.planner.executor import (
    CapExecutor,
    CapSettingsProvider,
    MachineExecutor,
    apply_edge_type,
    extract_json_path,
)

__all__ = [
    # Errors
    "PlannerError",
    "InvalidInputError",
    "InternalError",
    "NotFoundError",
    "RegistryError",
    "ExecutionError",
    "InvalidPathError",
    # Cardinality
    "InputCardinality",
    "CardinalityCompatibility",
    "InputStructure",
    "StructureCompatibility",
    "MediaShape",
    "ShapeCompatibility",
    "CapShapeInfo",
    "CardinalityPattern",
    "StrandShapeAnalysis",
    # Live Cap Graph
    "LiveMachinePlanEdgeType",
    "LiveMachinePlanEdge",
    "LiveCapGraph",
    "StrandStepType",
    "StrandStep",
    "Strand",
    "ReachableTargetInfo",
    # Argument Binding
    "SourceEntityType",
    "CapFileMetadata",
    "CapInputFile",
    "ArgumentSource",
    "ArgumentBinding",
    "ResolvedArgument",
    "ArgumentResolutionContext",
    "ArgumentBindings",
    "StrandInput",
    "resolve_binding",
    # Collection Input
    "CollectionFile",
    "CapInputCollection",
    # Plan
    "ExecutionNodeType",
    "MergeStrategy",
    "MachineNode",
    "EdgeType",
    "MachinePlanEdge",
    "MachinePlan",
    "NodeExecutionResult",
    "MachineResult",
    # Plan Builder
    "ArgumentResolution",
    "ArgumentInfo",
    "StepArgumentRequirements",
    "PathArgumentRequirements",
    "MachinePlanBuilder",
    # Executor
    "CapExecutor",
    "CapSettingsProvider",
    "MachineExecutor",
    "apply_edge_type",
    "extract_json_path",
]
