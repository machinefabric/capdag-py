"""Planner module — execution plan construction and shape analysis

This module provides the planning infrastructure for cap chains:

- Cardinality and structure analysis (MediaShape, InputCardinality, InputStructure)
- Argument binding and resolution
- Collection input management
- Execution plan data structures (CapExecutionPlan, CapNode, CapEdge)
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
    ShapeChainAnalysis,
)

from capdag.planner.live_cap_graph import (
    LiveCapEdgeType,
    LiveCapEdge,
    LiveCapGraph,
    CapChainStepType,
    CapChainStepInfo,
    CapChainPathInfo,
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
    CapChainInput,
    resolve_binding,
)

from capdag.planner.collection_input import (
    CollectionFile,
    CapInputCollection,
)

from capdag.planner.plan import (
    ExecutionNodeType,
    MergeStrategy,
    CapNode,
    EdgeType,
    CapEdge,
    CapExecutionPlan,
    NodeExecutionResult,
    CapChainExecutionResult,
)

from capdag.planner.plan_builder import (
    ArgumentResolution,
    ArgumentInfo,
    StepArgumentRequirements,
    PathArgumentRequirements,
    CapPlanBuilder,
)

from capdag.planner.executor import (
    CapExecutor,
    CapSettingsProvider,
    PlanExecutor,
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
    "ShapeChainAnalysis",
    # Live Cap Graph
    "LiveCapEdgeType",
    "LiveCapEdge",
    "LiveCapGraph",
    "CapChainStepType",
    "CapChainStepInfo",
    "CapChainPathInfo",
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
    "CapChainInput",
    "resolve_binding",
    # Collection Input
    "CollectionFile",
    "CapInputCollection",
    # Plan
    "ExecutionNodeType",
    "MergeStrategy",
    "CapNode",
    "EdgeType",
    "CapEdge",
    "CapExecutionPlan",
    "NodeExecutionResult",
    "CapChainExecutionResult",
    # Plan Builder
    "ArgumentResolution",
    "ArgumentInfo",
    "StepArgumentRequirements",
    "PathArgumentRequirements",
    "CapPlanBuilder",
    # Executor
    "CapExecutor",
    "CapSettingsProvider",
    "PlanExecutor",
    "apply_edge_type",
    "extract_json_path",
]
