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
    FabricRegistryError,
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

from capdag.planner.live_cap_fab import (
    LiveMachinePlanEdgeType,
    LiveMachinePlanEdge,
    LiveCapFab,
    ArgSourceRef,
    CapInput,
    StepToken,
    StepTokenError,
    StrandStepType,
    StrandStep,
    Strand,
    ReachableTargetInfo,
    PathFindingEventDepthComplete,
    PathFindingEventPathFound,
    PathFindingEventComplete,
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
    ForEachSource,
    MachineNode,
    EdgeType,
    MachinePlanEdge,
    MachinePlan,
    NodeExecutionResult,
    MapRun,
    BodyOutcome,
    MachineResult,
)

from capdag.planner.policy import (
    StepPolicy,
    ON_ERROR_FAIL,
    ON_ERROR_ABSENT,
    MAX_RETRY,
)

from capdag.planner.plan_builder import (
    ArgumentResolution,
    ArgumentInfo,
    StepArgumentRequirements,
    PathArgumentRequirements,
    MachinePlanBuilder,
)

__all__ = [
    # Errors
    "PlannerError",
    "InvalidInputError",
    "InternalError",
    "NotFoundError",
    "FabricRegistryError",
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
    # Live CapFab
    "LiveMachinePlanEdgeType",
    "LiveMachinePlanEdge",
    "LiveCapFab",
    "ArgSourceRef",
    "CapInput",
    "StrandStepType",
    "StrandStep",
    "StepToken",
    "StepTokenError",
    "Strand",
    "ReachableTargetInfo",
    "PathFindingEventDepthComplete",
    "PathFindingEventPathFound",
    "PathFindingEventComplete",
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
    "ForEachSource",
    "MachineNode",
    "EdgeType",
    "MachinePlanEdge",
    "MachinePlan",
    "NodeExecutionResult",
    "MapRun",
    "BodyOutcome",
    "MachineResult",
    # Policy
    "StepPolicy",
    "ON_ERROR_FAIL",
    "ON_ERROR_ABSENT",
    "MAX_RETRY",
    # Plan Builder
    "ArgumentResolution",
    "ArgumentInfo",
    "StepArgumentRequirements",
    "PathArgumentRequirements",
    "MachinePlanBuilder",
]
