"""Execution plan data structures for machines.

A plan is node-centric: steps, the values they read and produce, and the maps
they run in. Mirrors the reference's ``planner/plan.rs``.

Key types:
- ExecutionNodeType: one of the kinds a plan node is (a step, an output of a
  step, a map, an item of a map, a gather, an input slot, an output)
- MachineNode: a node in the execution plan
- EdgeType: how one node is wired into another
- MachinePlanEdge: a directed edge in the plan
- MachinePlan: the complete execution DAG
- NodeExecutionResult / BodyOutcome / MachineResult: what a run reports
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from capdag.planner.argument_binding import ArgumentBindings
from capdag.planner.cardinality import InputCardinality
from capdag.planner.error import InternalError
from capdag.planner.live_cap_fab import StepToken
from capdag.planner.policy import StepPolicy


# NodeId is just a string alias
NodeId = str


def _require_fields(data: Dict[str, Any], kind: str, *names: str) -> None:
    """Refuse a node that leaves out a field its kind has: a node read with a
    part of it missing is not the node that was written."""
    for name in names:
        if name not in data:
            raise ValueError(f"a {kind} node is missing field `{name}`")


def _string(data: Dict[str, Any], kind: str, name: str) -> str:
    value = data[name]
    if not isinstance(value, str):
        raise ValueError(f"field `{name}` of a {kind} node is a string, not {value!r}")
    return value


def _strings(data: Dict[str, Any], kind: str, name: str) -> List[str]:
    value = data[name]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"field `{name}` of a {kind} node is a list of strings, not {value!r}")
    return list(value)


@dataclass(frozen=True)
class ForEachSource:
    """One sequence a map iterates."""

    #: The node that holds the sequence, as the map's own scope sees it.
    node: NodeId
    #: The Item node the body is given each item as.
    item: NodeId

    def to_dict(self) -> Dict[str, Any]:
        return {"node": self.node, "item": self.item}

    @staticmethod
    def from_dict(data: Any) -> "ForEachSource":
        if not isinstance(data, dict):
            raise ValueError(f"a map source is an object, not {data!r}")
        for name in ("node", "item"):
            if not isinstance(data.get(name), str):
                raise ValueError(f"a map source is missing field `{name}`")
        return ForEachSource(node=data["node"], item=data["item"])


class ExecutionNodeType:
    """What a plan node is. Uses a ``kind`` field to tell the kinds apart,
    matching the reference's ``serde(tag = "node_type")`` representation.

    - ``CAP``: one step — one invocation of a cap. Carries the step's stable
      identity (``token_id``), its ``cap_urn``, its ``arg_bindings``, an
      optional ``preferred_cap`` and its ``policy``.
    - ``CAP_OUTPUT``: one output of a step other than its main one, as a node
      of its own. A step's main output is the step's node; every other output
      something takes is one of these.
    - ``FOR_EACH``: a map. Its body runs once per item of its sources, zipped:
      run ``i`` is given item ``i`` of every source, and sources of unequal
      length fail the run. What a body node produces is, from outside the map,
      the sequence of it over the runs in item order.
    - ``ITEM``: what one run of a map's body is given of one of the map's
      sources.
    - ``COLLECT``: a gather — several values delivered to one sequence arg as
      one sequence, in order. A single value contributes one item, a sequence
      its items; a member that is absent contributes none.
    - ``INPUT_SLOT``: an entry point for a value the run is given.
    - ``OUTPUT``: a terminal node marking a result.
    """

    # Kind constants
    CAP = "cap"
    CAP_OUTPUT = "cap_output"
    FOR_EACH = "for_each"
    ITEM = "item"
    COLLECT = "collect"
    INPUT_SLOT = "input_slot"
    OUTPUT = "output"

    __slots__ = ("kind", "_data")

    def __init__(self, kind: str, data: Dict[str, Any]) -> None:
        self.kind = kind
        self._data = data

    # --- Factory methods ---

    @staticmethod
    def cap(
        cap_urn: str,
        arg_bindings: Optional[ArgumentBindings] = None,
        preferred_cap: Optional[str] = None,
        token_id: Optional[StepToken] = None,
        policy: Optional[StepPolicy] = None,
    ) -> ExecutionNodeType:
        """A step. With no ``token_id`` a fresh one is minted: that is for a
        plan not derived from a resolved strand. A run whose progress must map
        back to a rendered strand passes the strand step's token."""
        return ExecutionNodeType(ExecutionNodeType.CAP, {
            "token_id": token_id if token_id is not None else StepToken.mint(),
            "cap_urn": cap_urn,
            "arg_bindings": arg_bindings if arg_bindings is not None else ArgumentBindings(),
            "preferred_cap": preferred_cap,
            "policy": policy if policy is not None else StepPolicy(),
        })

    @staticmethod
    def cap_output(cap_node: str, output_media_urn: str, output_name: str,
                   carries_input: bool = False) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.CAP_OUTPUT, {
            "cap_node": cap_node,
            "output_media_urn": output_media_urn,
            "output_name": output_name,
            "carries_input": carries_input,
        })

    @staticmethod
    def for_each(sources: List[ForEachSource], body: List[str],
                 token_id: Optional[StepToken] = None) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.FOR_EACH, {
            "token_id": token_id if token_id is not None else StepToken.mint(),
            "sources": list(sources),
            "body": list(body),
        })

    @staticmethod
    def item(foreach: str, source: str, media_urn: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.ITEM, {
            "foreach": foreach,
            "source": source,
            "media_urn": media_urn,
        })

    @staticmethod
    def collect(input_nodes: List[str], output_media_urn: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.COLLECT, {
            "input_nodes": list(input_nodes),
            "output_media_urn": output_media_urn,
        })

    @staticmethod
    def input_slot(slot_name: str, expected_media_urn: str,
                   cardinality: InputCardinality = InputCardinality.SINGLE) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.INPUT_SLOT, {
            "slot_name": slot_name,
            "expected_media_urn": expected_media_urn,
            "cardinality": cardinality,
        })

    @staticmethod
    def output(output_name: str, source_node: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.OUTPUT, {
            "output_name": output_name,
            "source_node": source_node,
        })

    # --- Data accessors ---

    @property
    def token_id(self) -> StepToken:
        """Cap, ForEach: the stable identity of the step or the map. A run's
        progress is reported under it, so it maps back to the graph element a
        client rendered."""
        return self._data["token_id"]

    @property
    def cap_urn(self) -> str:
        return self._data["cap_urn"]

    @property
    def arg_bindings(self) -> ArgumentBindings:
        return self._data["arg_bindings"]

    @property
    def preferred_cap(self) -> Optional[str]:
        return self._data.get("preferred_cap")

    @property
    def policy(self) -> StepPolicy:
        """Cap: what the step does when it fails — how many further attempts a
        retryable failure gets, and whether a failure that stands leaves the
        step's outputs absent instead of failing the run."""
        return self._data["policy"]

    @policy.setter
    def policy(self, policy: StepPolicy) -> None:
        if self.kind != ExecutionNodeType.CAP:
            raise AttributeError(f"a {self.kind} node has no policy")
        self._data["policy"] = policy

    @property
    def cap_node(self) -> str:
        """CapOutput: the step whose output this is."""
        return self._data["cap_node"]

    @property
    def carries_input(self) -> bool:
        """CapOutput: the output carries the step's input, type unchanged,
        rather than its own URN (a router's outputs)."""
        return self._data["carries_input"]

    @property
    def output_media_urn(self) -> str:
        """CapOutput: the output's media URN in the cap's definition (its
        identity, and what its response stream names). Collect: the element
        type of the gathered sequence."""
        return self._data["output_media_urn"]

    @property
    def sources(self) -> List[ForEachSource]:
        """ForEach: the sequences the map zips, each with the node the body is
        given its item as. At least one."""
        return self._data["sources"]

    @property
    def body(self) -> List[str]:
        """ForEach: every node that runs once per item — the item nodes, the
        steps, the outputs and gathers that belong to them, and the maps
        opened inside this one (whose own bodies are theirs, not listed
        here)."""
        return self._data["body"]

    @property
    def foreach(self) -> str:
        """Item: the map this is an item of."""
        return self._data["foreach"]

    @property
    def source(self) -> str:
        """Item: the source node whose item it is."""
        return self._data["source"]

    @property
    def media_urn(self) -> str:
        """Item: the item's media URN — the element type of the source
        sequence."""
        return self._data["media_urn"]

    @property
    def input_nodes(self) -> List[str]:
        """Collect: the nodes gathered, in the order they are delivered."""
        return self._data["input_nodes"]

    @property
    def slot_name(self) -> str:
        return self._data["slot_name"]

    @property
    def expected_media_urn(self) -> str:
        return self._data["expected_media_urn"]

    @property
    def cardinality(self) -> InputCardinality:
        return self._data["cardinality"]

    @property
    def output_name(self) -> str:
        """Output: the result's name. CapOutput: the output's name in the
        cap's definition (a label; unique per cap)."""
        return self._data["output_name"]

    @property
    def source_node(self) -> str:
        return self._data["source_node"]

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        """The node as the reference writes it: the kind under ``node_type``
        and the kind's fields beside it."""
        data = self._data
        written: Dict[str, Any] = {"node_type": self.kind}
        if self.kind == ExecutionNodeType.CAP:
            written["token_id"] = str(data["token_id"])
            written["cap_urn"] = data["cap_urn"]
            written["arg_bindings"] = data["arg_bindings"].to_dict()
            if data.get("preferred_cap") is not None:
                written["preferred_cap"] = data["preferred_cap"]
            if not data["policy"].is_default():
                written["policy"] = data["policy"].to_dict()
        elif self.kind == ExecutionNodeType.CAP_OUTPUT:
            written["cap_node"] = data["cap_node"]
            written["output_media_urn"] = data["output_media_urn"]
            written["output_name"] = data["output_name"]
            written["carries_input"] = data["carries_input"]
        elif self.kind == ExecutionNodeType.FOR_EACH:
            written["token_id"] = str(data["token_id"])
            written["sources"] = [source.to_dict() for source in data["sources"]]
            written["body"] = list(data["body"])
        elif self.kind == ExecutionNodeType.ITEM:
            written["foreach"] = data["foreach"]
            written["source"] = data["source"]
            written["media_urn"] = data["media_urn"]
        elif self.kind == ExecutionNodeType.COLLECT:
            written["input_nodes"] = list(data["input_nodes"])
            written["output_media_urn"] = data["output_media_urn"]
        elif self.kind == ExecutionNodeType.INPUT_SLOT:
            written["slot_name"] = data["slot_name"]
            written["expected_media_urn"] = data["expected_media_urn"]
            written["cardinality"] = data["cardinality"].value
        elif self.kind == ExecutionNodeType.OUTPUT:
            written["output_name"] = data["output_name"]
            written["source_node"] = data["source_node"]
        else:
            raise ValueError(f"a node of no kind a plan has: {self.kind!r}")
        return written

    @staticmethod
    def from_dict(d: Any) -> ExecutionNodeType:
        """Read a node. A node type this library does not know is refused, and
        so is a node missing a field its kind has."""
        if not isinstance(d, dict):
            raise ValueError(f"a plan node is an object, not {d!r}")
        if "node_type" not in d:
            raise ValueError("a plan node is missing field `node_type`")
        kind = d["node_type"]
        if kind == ExecutionNodeType.CAP:
            _require_fields(d, kind, "token_id", "cap_urn")
            bindings = d.get("arg_bindings")
            policy = d.get("policy")
            return ExecutionNodeType.cap(
                cap_urn=_string(d, kind, "cap_urn"),
                arg_bindings=ArgumentBindings.from_dict(bindings) if bindings is not None else None,
                preferred_cap=d.get("preferred_cap"),
                token_id=StepToken.parse(_string(d, kind, "token_id")),
                policy=StepPolicy.from_dict(policy) if policy is not None else None,
            )
        if kind == ExecutionNodeType.CAP_OUTPUT:
            _require_fields(d, kind, "cap_node", "output_media_urn", "output_name")
            return ExecutionNodeType.cap_output(
                cap_node=_string(d, kind, "cap_node"),
                output_media_urn=_string(d, kind, "output_media_urn"),
                output_name=_string(d, kind, "output_name"),
                carries_input=bool(d.get("carries_input", False)),
            )
        if kind == ExecutionNodeType.FOR_EACH:
            _require_fields(d, kind, "token_id", "sources", "body")
            if not isinstance(d["sources"], list):
                raise ValueError(f"field `sources` of a {kind} node is a list, not {d['sources']!r}")
            return ExecutionNodeType.for_each(
                sources=[ForEachSource.from_dict(source) for source in d["sources"]],
                body=_strings(d, kind, "body"),
                token_id=StepToken.parse(_string(d, kind, "token_id")),
            )
        if kind == ExecutionNodeType.ITEM:
            _require_fields(d, kind, "foreach", "source", "media_urn")
            return ExecutionNodeType.item(
                foreach=_string(d, kind, "foreach"),
                source=_string(d, kind, "source"),
                media_urn=_string(d, kind, "media_urn"),
            )
        if kind == ExecutionNodeType.COLLECT:
            _require_fields(d, kind, "input_nodes", "output_media_urn")
            return ExecutionNodeType.collect(
                input_nodes=_strings(d, kind, "input_nodes"),
                output_media_urn=_string(d, kind, "output_media_urn"),
            )
        if kind == ExecutionNodeType.INPUT_SLOT:
            _require_fields(d, kind, "slot_name", "expected_media_urn", "cardinality")
            return ExecutionNodeType.input_slot(
                slot_name=_string(d, kind, "slot_name"),
                expected_media_urn=_string(d, kind, "expected_media_urn"),
                cardinality=InputCardinality(d["cardinality"]),
            )
        if kind == ExecutionNodeType.OUTPUT:
            _require_fields(d, kind, "output_name", "source_node")
            return ExecutionNodeType.output(
                output_name=_string(d, kind, "output_name"),
                source_node=_string(d, kind, "source_node"),
            )
        raise ValueError(f"unknown ExecutionNodeType node_type: {kind!r}")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExecutionNodeType):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"ExecutionNodeType({self.kind!r})"


class MachineNode:
    """A node in the execution plan."""

    __slots__ = ("id", "node_type", "description")

    def __init__(self, id: str, node_type: ExecutionNodeType,
                 description: Optional[str] = None) -> None:
        self.id = id
        self.node_type = node_type
        self.description = description

    # --- Static constructors ---

    @staticmethod
    def cap(id: str, cap_urn: str) -> MachineNode:
        """A step with no bindings. Mints a fresh token: this builds steps for
        plans that are not derived from a resolved strand."""
        return MachineNode(id, ExecutionNodeType.cap(cap_urn))

    @staticmethod
    def cap_with_bindings(id: str, cap_urn: str, bindings: ArgumentBindings) -> MachineNode:
        """A step with bindings. Mints a fresh token."""
        return MachineNode(id, ExecutionNodeType.cap(cap_urn, bindings))

    @staticmethod
    def cap_with_bindings_token(id: str, cap_urn: str, bindings: ArgumentBindings,
                                token_id: StepToken) -> MachineNode:
        """A step with bindings, keeping a strand step's identity."""
        return MachineNode(id, ExecutionNodeType.cap(cap_urn, bindings, token_id=token_id))

    @staticmethod
    def cap_with_preference(id: str, cap_urn: str, bindings: ArgumentBindings,
                            preferred_cap: Optional[str] = None) -> MachineNode:
        """A step with bindings and a preferred cap. Mints a fresh token."""
        return MachineNode(id, ExecutionNodeType.cap(cap_urn, bindings, preferred_cap))

    @staticmethod
    def for_each(id: str, sources: List[ForEachSource], body: List[str]) -> MachineNode:
        """A map. Mints a fresh token; a run whose progress must map back to a
        rendered strand uses :meth:`for_each_token`."""
        return MachineNode.for_each_token(id, sources, body, StepToken.mint())

    @staticmethod
    def for_each_token(id: str, sources: List[ForEachSource], body: List[str],
                       token_id: StepToken) -> MachineNode:
        """A map, keeping the originating step's identity."""
        return MachineNode(
            id, ExecutionNodeType.for_each(sources, body, token_id),
            description="Map: run the body once per item",
        )

    @staticmethod
    def item(id: str, foreach: str, source: str, media_urn: str) -> MachineNode:
        """The node a map's body is given one source's item as."""
        return MachineNode(
            id, ExecutionNodeType.item(foreach, source, media_urn),
            description=f"Item of {source}",
        )

    @staticmethod
    def cap_output(id: str, cap_node: str, output_media_urn: str, output_name: str,
                   carries_input: bool = False) -> MachineNode:
        """The node of an output of ``cap_node`` other than its main one."""
        return MachineNode(
            id, ExecutionNodeType.cap_output(cap_node, output_media_urn, output_name, carries_input),
            description=f"Output: {output_name}",
        )

    @staticmethod
    def collect(id: str, input_nodes: List[str], output_media_urn: str) -> MachineNode:
        """A gather."""
        return MachineNode(
            id, ExecutionNodeType.collect(input_nodes, output_media_urn),
            description="Gather: several values into one sequence",
        )

    @staticmethod
    def input_slot(id: str, slot_name: str, media_urn: str,
                   cardinality: InputCardinality = InputCardinality.SINGLE) -> MachineNode:
        return MachineNode(
            id, ExecutionNodeType.input_slot(slot_name, media_urn, cardinality),
            description=f"Input: {slot_name}",
        )

    @staticmethod
    def output(id: str, output_name: str, source_node: str) -> MachineNode:
        return MachineNode(
            id, ExecutionNodeType.output(output_name, source_node),
            description=f"Output: {output_name}",
        )

    # --- Query methods ---

    def is_cap(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.CAP

    def is_fan_out(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.FOR_EACH

    def is_fan_in(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.COLLECT

    def get_cap_urn(self) -> Optional[str]:
        if self.node_type.kind == ExecutionNodeType.CAP:
            return self.node_type.cap_urn
        return None

    def get_preferred_cap(self) -> Optional[str]:
        if self.node_type.kind == ExecutionNodeType.CAP:
            return self.node_type.preferred_cap
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "node_type": self.node_type.to_dict(),
        }
        if self.description is not None:
            d["description"] = self.description
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> MachineNode:
        return MachineNode(
            id=d["id"],
            node_type=ExecutionNodeType.from_dict(d["node_type"]),
            description=d.get("description"),
        )

    def __repr__(self) -> str:
        return f"MachineNode(id={self.id!r}, type={self.node_type.kind!r})"


class EdgeType:
    """How one node is wired into another.

    - ``DIRECT``: the whole value, into a step's main input (or into a map, an
      output, a gather).
    - ``ARG``: the whole value, into the arg of a step that ``arg_urn`` names.
    - ``ITERATION``: from a map to an item of it.
    - ``COLLECTION``: from a member into the gather that takes it.

    An edge carries the whole value: a part of it is not something an edge can
    be asked for.
    """

    DIRECT = "direct"
    ARG = "arg"
    ITERATION = "iteration"
    COLLECTION = "collection"

    _PLAIN = (DIRECT, ITERATION, COLLECTION)

    __slots__ = ("kind", "_arg_urn")

    def __init__(self, kind: str, arg_urn: Optional[str] = None) -> None:
        if kind == EdgeType.ARG:
            if not isinstance(arg_urn, str):
                raise ValueError("an arg edge names the arg it feeds")
        elif kind in EdgeType._PLAIN:
            if arg_urn is not None:
                raise ValueError(f"only an arg edge names an argument, not a {kind} edge")
        else:
            raise ValueError(f"unknown EdgeType: {kind!r}")
        self.kind = kind
        self._arg_urn = arg_urn

    @staticmethod
    def direct() -> EdgeType:
        return EdgeType(EdgeType.DIRECT)

    @staticmethod
    def arg(arg_urn: str) -> EdgeType:
        return EdgeType(EdgeType.ARG, arg_urn)

    @staticmethod
    def iteration() -> EdgeType:
        return EdgeType(EdgeType.ITERATION)

    @staticmethod
    def collection() -> EdgeType:
        return EdgeType(EdgeType.COLLECTION)

    @property
    def arg_urn(self) -> Optional[str]:
        """The arg an ``ARG`` edge feeds, by its URN. ``None`` for every other
        kind."""
        return self._arg_urn

    def to_dict(self) -> Any:
        """The edge type as the reference writes it: a kind that carries
        nothing is its name (``"direct"``); an arg edge is
        ``{"arg": {"arg_urn": "…"}}``."""
        if self.kind == EdgeType.ARG:
            return {"arg": {"arg_urn": self._arg_urn}}
        return self.kind

    @staticmethod
    def from_dict(value: Any) -> EdgeType:
        """Read an edge type. A kind this library does not know is refused: an
        edge of a kind nobody here can carry is not an edge."""
        if isinstance(value, str):
            if value not in EdgeType._PLAIN:
                raise ValueError(f"unknown EdgeType: {value}")
            return EdgeType(value)
        if not isinstance(value, dict) or len(value) != 1:
            raise ValueError(f"an EdgeType is a name, or one kind with what it carries: {value!r}")
        (kind, carried), = value.items()
        if kind != EdgeType.ARG:
            raise ValueError(f"unknown EdgeType: {kind}")
        if not isinstance(carried, dict) or not isinstance(carried.get("arg_urn"), str):
            raise ValueError("an arg edge is missing field `arg_urn`")
        return EdgeType.arg(carried["arg_urn"])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EdgeType):
            return NotImplemented
        return self.kind == other.kind and self._arg_urn == other._arg_urn

    def __hash__(self) -> int:
        return hash((self.kind, self._arg_urn))

    def __repr__(self) -> str:
        if self.kind == EdgeType.ARG:
            return f"EdgeType({self.kind!r}, {self._arg_urn!r})"
        return f"EdgeType({self.kind!r})"


class MachinePlanEdge:
    """A directed edge in the execution plan."""

    __slots__ = ("from_node", "to_node", "edge_type")

    def __init__(self, from_node: str, to_node: str,
                 edge_type: Optional[EdgeType] = None) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.edge_type = edge_type or EdgeType.direct()

    @staticmethod
    def direct(from_node: str, to_node: str) -> MachinePlanEdge:
        return MachinePlanEdge(from_node, to_node, EdgeType.direct())

    @staticmethod
    def arg(from_node: str, to_node: str, arg_urn: str) -> MachinePlanEdge:
        return MachinePlanEdge(from_node, to_node, EdgeType.arg(arg_urn))

    @staticmethod
    def iteration(from_node: str, to_node: str) -> MachinePlanEdge:
        return MachinePlanEdge(from_node, to_node, EdgeType.iteration())

    @staticmethod
    def collection(from_node: str, to_node: str) -> MachinePlanEdge:
        return MachinePlanEdge(from_node, to_node, EdgeType.collection())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "edge_type": self.edge_type.to_dict(),
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> MachinePlanEdge:
        # An edge written without a type is a direct one, as the reference
        # reads it.
        return MachinePlanEdge(
            from_node=d["from_node"],
            to_node=d["to_node"],
            edge_type=EdgeType.from_dict(d["edge_type"]) if "edge_type" in d else EdgeType.direct(),
        )

    def __repr__(self) -> str:
        return f"MachinePlanEdge({self.from_node!r} -> {self.to_node!r}, {self.edge_type!r})"


class MachinePlan:
    """Complete execution plan DAG.

    Manages nodes, edges, entry points, and output nodes. Supports validation,
    topological ordering, and saying which map each node runs in.
    """

    __slots__ = ("name", "nodes", "edges", "entry_nodes", "output_nodes", "metadata")

    def __init__(self, name: str) -> None:
        self.name = name
        self.nodes: Dict[str, MachineNode] = {}
        self.edges: List[MachinePlanEdge] = []
        self.entry_nodes: List[str] = []
        self.output_nodes: List[str] = []
        self.metadata: Optional[Dict[str, Any]] = None

    def add_node(self, node: MachineNode) -> None:
        """Add a node. InputSlot nodes are auto-registered as entry nodes,
        Output nodes as output nodes."""
        node_id = node.id
        self.nodes[node_id] = node
        if node.node_type.kind == ExecutionNodeType.INPUT_SLOT:
            self.entry_nodes.append(node_id)
        elif node.node_type.kind == ExecutionNodeType.OUTPUT:
            self.output_nodes.append(node_id)

    def add_edge(self, edge: MachinePlanEdge) -> None:
        self.edges.append(edge)

    def get_node(self, id: str) -> Optional[MachineNode]:
        return self.nodes.get(id)

    def validate(self) -> None:
        """Check plan structure: every edge, entry and output names a node of
        the plan, and what a node names is there and is what it is named as.
        Raises InternalError otherwise."""
        for edge in self.edges:
            if edge.from_node not in self.nodes:
                raise InternalError(f"Edge from_node '{edge.from_node}' not found in plan")
            if edge.to_node not in self.nodes:
                raise InternalError(f"Edge to_node '{edge.to_node}' not found in plan")
        for entry_id in self.entry_nodes:
            if entry_id not in self.nodes:
                raise InternalError(f"Entry node '{entry_id}' not found in plan")
        for output_id in self.output_nodes:
            if output_id not in self.nodes:
                raise InternalError(f"Output node '{output_id}' not found in plan")

        def known(owner: str, what: str, node_id: str) -> None:
            if node_id not in self.nodes:
                raise InternalError(
                    f"node '{owner}' names {what} '{node_id}', which is not in the plan"
                )

        in_body: Dict[str, str] = {}
        # In node-id order, so the same plan is refused the same way every time.
        for node_id in sorted(self.nodes):
            nt = self.nodes[node_id].node_type
            kind = nt.kind
            if kind in (ExecutionNodeType.CAP, ExecutionNodeType.INPUT_SLOT):
                continue
            if kind == ExecutionNodeType.OUTPUT:
                known(node_id, "source", nt.source_node)
            elif kind == ExecutionNodeType.COLLECT:
                for member in nt.input_nodes:
                    known(node_id, "gathered node", member)
            elif kind == ExecutionNodeType.CAP_OUTPUT:
                known(node_id, "step", nt.cap_node)
                if not self.nodes[nt.cap_node].is_cap():
                    raise InternalError(
                        f"output node '{node_id}' names '{nt.cap_node}' as its step, which is not a step"
                    )
            elif kind == ExecutionNodeType.ITEM:
                known(node_id, "map", nt.foreach)
                of = self.nodes[nt.foreach].node_type
                listed = of.kind == ExecutionNodeType.FOR_EACH and any(
                    source.item == node_id and source.node == nt.source for source in of.sources
                )
                if not listed:
                    raise InternalError(
                        f"item node '{node_id}' names map '{nt.foreach}' and source '{nt.source}', "
                        f"and that map does not list it so"
                    )
            elif kind == ExecutionNodeType.FOR_EACH:
                if not nt.sources:
                    raise InternalError(f"map '{node_id}' iterates nothing")
                for source in nt.sources:
                    known(node_id, "source", source.node)
                    known(node_id, "item", source.item)
                    item = self.nodes[source.item].node_type
                    if (
                        item.kind != ExecutionNodeType.ITEM
                        or item.foreach != node_id
                        or item.source != source.node
                    ):
                        raise InternalError(
                            f"map '{node_id}' lists '{source.item}' as its item of '{source.node}', "
                            f"which is not that"
                        )
                    if source.item not in nt.body:
                        raise InternalError(
                            f"map '{node_id}' does not list its item '{source.item}' in its body"
                        )
                for member in nt.body:
                    known(node_id, "body node", member)
                    if member == node_id:
                        raise InternalError(f"map '{node_id}' lists itself in its body")
                    if member in in_body:
                        raise InternalError(
                            f"node '{member}' is in the body of two maps "
                            f"('{in_body[member]}' and '{node_id}')"
                        )
                    in_body[member] = node_id
            else:
                raise InternalError(f"node '{node_id}' is of no kind a plan has")

    def enclosing_maps(self) -> Dict[str, str]:
        """The map each node runs in: node id → the id of the map whose body
        lists it. A node of the machine itself has no entry."""
        enclosing: Dict[str, str] = {}
        for node_id, node in self.nodes.items():
            if node.node_type.kind == ExecutionNodeType.FOR_EACH:
                for member in node.node_type.body:
                    enclosing[member] = node_id
        return enclosing

    def map_members(self, foreach_id: str) -> Set[str]:
        """Every node inside map ``foreach_id``: its body, and the bodies of
        the maps opened inside it."""
        members: Set[str] = set()
        pending = [foreach_id]
        while pending:
            node = self.nodes.get(pending.pop())
            if node is None or node.node_type.kind != ExecutionNodeType.FOR_EACH:
                continue
            for member in node.node_type.body:
                if member not in members:
                    members.add(member)
                    pending.append(member)
        return members

    def topological_order(self) -> List[MachineNode]:
        """Return nodes in topological order using Kahn's algorithm.
        Raises InternalError if cycle detected."""
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}

        for edge in self.edges:
            if edge.to_node in in_degree:
                in_degree[edge.to_node] += 1
            if edge.from_node in adj:
                adj[edge.from_node].append(edge.to_node)

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[MachineNode] = []

        while queue:
            nid = queue.popleft()
            node = self.nodes.get(nid)
            if node is not None:
                result.append(node)
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise InternalError("Cycle detected in execution plan")
        return result

    @staticmethod
    def single_cap(cap_urn: str, input_media: str, _output_media: str,
                   file_path_arg_name: str) -> MachinePlan:
        """Create a simple 3-node plan: input → cap → output."""
        plan = MachinePlan(f"single_{cap_urn}")
        plan.add_node(MachineNode.input_slot("input_slot", "input", input_media, InputCardinality.SINGLE))

        bindings = ArgumentBindings()
        bindings.add_file_path(file_path_arg_name)
        plan.add_node(MachineNode.cap_with_bindings("cap_0", cap_urn, bindings))
        plan.add_node(MachineNode.output("output", "result", "cap_0"))

        plan.add_edge(MachinePlanEdge.direct("input_slot", "cap_0"))
        plan.add_edge(MachinePlanEdge.direct("cap_0", "output"))
        return plan

    @staticmethod
    def linear_chain(cap_urns: List[str], input_media: str, _output_media: str,
                     file_path_arg_names: List[str]) -> MachinePlan:
        """Create a linear chain plan: input → cap_0 → cap_1 → ... → output."""
        plan = MachinePlan("linear_chain")
        if not cap_urns:
            return plan

        plan.add_node(MachineNode.input_slot("input_slot", "input", input_media, InputCardinality.SINGLE))

        prev_id = "input_slot"
        for i, urn in enumerate(cap_urns):
            node_id = f"cap_{i}"
            bindings = ArgumentBindings()
            if i < len(file_path_arg_names):
                bindings.add_file_path(file_path_arg_names[i])
            plan.add_node(MachineNode.cap_with_bindings(node_id, urn, bindings))
            plan.add_edge(MachinePlanEdge.direct(prev_id, node_id))
            prev_id = node_id

        plan.add_node(MachineNode.output("output", "result", prev_id))
        plan.add_edge(MachinePlanEdge.direct(prev_id, "output"))
        return plan

    def has_foreach(self) -> bool:
        """Whether this plan contains a map."""
        return any(
            n.node_type.kind == ExecutionNodeType.FOR_EACH
            for n in self.nodes.values()
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "entry_nodes": self.entry_nodes,
            "output_nodes": self.output_nodes,
        }
        if self.metadata is not None:
            d["metadata"] = self.metadata
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> MachinePlan:
        plan = MachinePlan(d["name"])
        plan.nodes = {
            node_id: MachineNode.from_dict(node_data)
            for node_id, node_data in d["nodes"].items()
        }
        plan.edges = [MachinePlanEdge.from_dict(edge_data) for edge_data in d["edges"]]
        plan.entry_nodes = list(d["entry_nodes"])
        plan.output_nodes = list(d["output_nodes"])
        plan.metadata = d.get("metadata")
        return plan

    def __repr__(self) -> str:
        return (
            f"MachinePlan(name={self.name!r}, "
            f"nodes={len(self.nodes)}, edges={len(self.edges)})"
        )


class NodeExecutionResult:
    """Result of executing a single node."""

    __slots__ = (
        "node_id", "success", "binary_output", "binary_items",
        "saved_paths", "is_sequence_output", "total_bytes",
        "media_urn_output", "error", "duration_ms",
    )

    def __init__(
        self,
        node_id: str,
        success: bool,
        binary_output: Optional[bytes] = None,
        binary_items: Optional[List[bytes]] = None,
        saved_paths: Optional[List[str]] = None,
        is_sequence_output: bool = False,
        total_bytes: int = 0,
        media_urn_output: str = "",
        error: Optional[str] = None,
        duration_ms: int = 0,
    ) -> None:
        self.node_id = node_id
        self.success = success
        # binary_output: single raw output bytes (standalone executor)
        self.binary_output = binary_output
        # binary_items: individual output items for is_sequence=True outputs (standalone executor)
        self.binary_items = binary_items
        # saved_paths: file paths written by IncrementalWriter (pipeline executor)
        self.saved_paths = saved_paths or []
        # is_sequence_output: True if the cap emitted a sequence (from STREAM_START is_sequence)
        self.is_sequence_output = is_sequence_output
        # total_bytes: bytes written to disk; 0 when binary_output is used
        self.total_bytes = total_bytes
        # media_urn_output: output media URN from STREAM_START or plan derivation
        self.media_urn_output = media_urn_output
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "node_id": self.node_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }
        if self.saved_paths:
            d["saved_paths"] = self.saved_paths
        if self.is_sequence_output:
            d["is_sequence_output"] = self.is_sequence_output
        if self.total_bytes:
            d["total_bytes"] = self.total_bytes
        if self.media_urn_output:
            d["media_urn_output"] = self.media_urn_output
        if self.error is not None:
            d["error"] = self.error
        # binary_output and binary_items are not included in dict (too large / not JSON-safe)
        return d

    def __repr__(self) -> str:
        return f"NodeExecutionResult(node_id={self.node_id!r}, success={self.success})"


@dataclass(frozen=True)
class MapRun:
    """One run of a map's body: which map, and which of its runs."""

    #: Stable identity of the map.
    foreach_token_id: StepToken
    #: Index of the run within the map (0-based, item order).
    body_index: int

    def __post_init__(self) -> None:
        if not isinstance(self.foreach_token_id, StepToken):
            raise ValueError("a map run names its map by its token")
        if type(self.body_index) is not int or self.body_index < 0:
            raise ValueError("a map run's body_index must be a non-negative integer")

    def to_dict(self) -> Dict[str, Any]:
        return {"foreach_token_id": str(self.foreach_token_id), "body_index": self.body_index}

    @staticmethod
    def from_dict(data: Any) -> "MapRun":
        """Read a run. One that names no map is not a run."""
        if not isinstance(data, dict):
            raise ValueError(f"a map run is an object, not {data!r}")
        for name in ("foreach_token_id", "body_index"):
            if name not in data:
                raise ValueError(f"a map run is missing field `{name}`")
        token = data["foreach_token_id"]
        if not isinstance(token, str):
            raise ValueError("a map run names its map by its token")
        return MapRun(foreach_token_id=StepToken.parse(token), body_index=data["body_index"])


class BodyOutcome:
    """Outcome of a single ForEach body execution.

    For linear (non-ForEach) pipelines, a single BodyOutcome with body_index=0
    represents the entire execution.
    """

    __slots__ = (
        "body_index", "foreach_token_id", "enclosing", "success", "cap_urns", "failed_token_id",
        "error", "failed_arg_urn", "title", "saved_paths", "total_bytes",
        "duration_ms", "item_preview_text", "item_byte_count",
    )

    def __init__(
        self,
        body_index: int,
        foreach_token_id: Optional[str],
        success: bool,
        cap_urns: Optional[List[str]] = None,
        failed_token_id: Optional[str] = None,
        error: Optional[str] = None,
        failed_arg_urn: Optional[str] = None,
        title: Optional[str] = None,
        saved_paths: Optional[List[str]] = None,
        total_bytes: int = 0,
        duration_ms: int = 0,
        item_preview_text: Optional[str] = None,
        item_byte_count: int = 0,
        enclosing: Optional[List[MapRun]] = None,
    ) -> None:
        if type(body_index) is not int or body_index < 0:
            raise ValueError("body_index must be a non-negative integer")
        if foreach_token_id is None and body_index != 0:
            raise ValueError("a linear BodyOutcome must use body_index 0")
        if foreach_token_id is None and enclosing:
            raise ValueError("a linear BodyOutcome is inside no map")
        if foreach_token_id is not None and (
            not isinstance(foreach_token_id, str) or not foreach_token_id
        ):
            raise ValueError("foreach_token_id must be None or a non-empty string")
        if failed_token_id is not None and (
            not isinstance(failed_token_id, str) or not failed_token_id
        ):
            raise ValueError("failed_token_id must be None or a non-empty string")
        if failed_arg_urn is not None and (
            not isinstance(failed_arg_urn, str) or not failed_arg_urn
        ):
            raise ValueError("failed_arg_urn must be None or a non-empty string")
        for run in enclosing or []:
            if not isinstance(run, MapRun):
                raise ValueError("the runs a body is inside are map runs")
        # body_index: index of this body within the ForEach (0-based)
        self.body_index = body_index
        # Stable ForEach StrandStep token; None only for a linear whole-run outcome.
        self.foreach_token_id = foreach_token_id
        # enclosing: the runs this body is inside, when its map is opened inside
        # another's body — outermost first. Empty for a map of the machine
        # itself, and for a linear pipeline. A body index alone does not name a
        # run of a nested map: it recurs under every run of the map around it.
        self.enclosing: List[MapRun] = list(enclosing or [])
        self.success = success
        # cap_urns: cap URNs in the body's execution pathway (in execution order)
        self.cap_urns = cap_urns or []
        # failed_token_id: stable StrandStep.token_id that failed (None if succeeded)
        self.failed_token_id = failed_token_id
        self.error = error
        self.failed_arg_urn = failed_arg_urn
        # title: human-readable title from stream metadata (per-item for ForEach, stream-level for linear)
        self.title = title
        self.saved_paths = saved_paths or []
        self.total_bytes = total_bytes
        self.duration_ms = duration_ms
        self.item_preview_text = item_preview_text
        self.item_byte_count = item_byte_count

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "body_index": self.body_index,
            "foreach_token_id": self.foreach_token_id,
            "enclosing": [run.to_dict() for run in self.enclosing],
            "success": self.success,
            "cap_urns": self.cap_urns,
            "failed_token_id": self.failed_token_id,
            "error": self.error,
            "failed_arg_urn": self.failed_arg_urn,
            "title": self.title,
            "saved_paths": self.saved_paths,
            "total_bytes": self.total_bytes,
            "duration_ms": self.duration_ms,
            "item_preview_text": self.item_preview_text,
            "item_byte_count": self.item_byte_count,
        }
        return d

    @staticmethod
    def from_dict(data: Any) -> "BodyOutcome":
        """Read an outcome. The coordinates of a failure are required and may
        be null: a missing key is not an outcome. A null ``foreach_token_id``
        is the one whole-run outcome of a linear machine; null failure fields
        mean the source did not attribute the failure to a step or an arg."""
        if not isinstance(data, dict):
            raise ValueError(f"a body outcome is an object, not {data!r}")
        for name in ("foreach_token_id", "failed_token_id", "failed_arg_urn"):
            if name not in data:
                raise ValueError(f"body outcome missing required nullable field `{name}`")
        for name in ("body_index", "success", "cap_urns", "saved_paths", "total_bytes", "duration_ms"):
            if name not in data:
                raise ValueError(f"body outcome missing field `{name}`")
        enclosing = data.get("enclosing", [])
        if not isinstance(enclosing, list):
            raise ValueError("the runs a body is inside are a list")
        return BodyOutcome(
            body_index=data["body_index"],
            foreach_token_id=data["foreach_token_id"],
            enclosing=[MapRun.from_dict(run) for run in enclosing],
            success=data["success"],
            cap_urns=list(data["cap_urns"]),
            failed_token_id=data["failed_token_id"],
            error=data.get("error"),
            failed_arg_urn=data["failed_arg_urn"],
            title=data.get("title"),
            saved_paths=list(data["saved_paths"]),
            total_bytes=data["total_bytes"],
            duration_ms=data["duration_ms"],
            item_preview_text=data.get("item_preview_text"),
            item_byte_count=data.get("item_byte_count", 0),
        )

    def __repr__(self) -> str:
        return (
            f"BodyOutcome(foreach_token_id={self.foreach_token_id!r}, "
            f"body_index={self.body_index}, success={self.success})"
        )


class MachineResult:
    """Result of executing a complete machine."""

    __slots__ = ("success", "node_results", "outputs", "error", "total_duration_ms", "body_outcomes")

    def __init__(
        self,
        success: bool,
        node_results: Optional[Dict[str, NodeExecutionResult]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        total_duration_ms: int = 0,
        body_outcomes: Optional[List[BodyOutcome]] = None,
    ) -> None:
        self.success = success
        self.node_results = node_results or {}
        self.outputs = outputs or {}
        self.error = error
        self.total_duration_ms = total_duration_ms
        # body_outcomes: per-body outcomes for ForEach pipelines, or single entry for linear plans
        # Populated by the pipeline executor; empty for the standalone executor.
        self.body_outcomes = body_outcomes or []

    def primary_output(self) -> Optional[Any]:
        """Get the first output value (non-deterministic ordering)."""
        for v in self.outputs.values():
            return v
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "node_results": {nid: r.to_dict() for nid, r in self.node_results.items()},
            "outputs": self.outputs,
            "total_duration_ms": self.total_duration_ms,
            "body_outcomes": [b.to_dict() for b in self.body_outcomes],
        }
        if self.error is not None:
            d["error"] = self.error
        return d

    def __repr__(self) -> str:
        return (
            f"MachineResult(success={self.success}, "
            f"outputs={len(self.outputs)})"
        )
