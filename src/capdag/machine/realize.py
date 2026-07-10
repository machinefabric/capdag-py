"""Realize a resolved MachineStrand into an executable Strand of steps.

This is the single, shared conversion from a resolved notation strand into
the Strand the canonical plan builder (MachinePlanBuilder.build_plan_from_path)
consumes. It is the inverse of planner.live_cap_fab.Strand.knit and the
logic the engine's editor-run realization and the reference/CLI path both
use — one implementation, no duplication.

What it does:
    Walking the strand in data-flow (dependency) order, it emits one Cap
    step per edge, instantiating the runtime media type through each cap's
    MAIN input (CapUrn.infer_runtime_output_media, the mirror's equivalent
    of Rust's CapUrn::apply_to_runtime_input_media), and inserts a ForEach
    step before any cap the resolver already marked is_loop.

    A cap edge's resolver `assignment` binds each wiring source to one of
    the cap's arguments by media URN. Exactly one of those is the cap's
    stdin (main) input — it threads the runtime media of the chain and is
    the step's from_spec. Every OTHER binding is a convergence input:
    another cap's output routed into a non-main argument, recorded on the
    step as one of its `inputs`. This is what lets a strand express a DAG
    (a cap with more than one incoming producer), not just a linear chain —
    the executable model the engine and reference path share.

    is_loop is the single source of truth for cardinality: resolve.py
    derives it from Cap.needs_foreach (a sequence source feeding a
    scalar-input cap); this converter reads edge.is_loop, never
    recomputing it.

Invariants (enforced, no fallbacks):
    - Exactly one stdin (main) input per cap. The cap definition declares
      one Stdin argument; the resolver's assignment binds a source to it.
      A cap with no stdin arg, or an edge with no binding to it, is a hard
      error.
    - Convergence wires only cap outputs. A non-main argument fed by
      wiring must be another cap's output. A raw input feeding a non-main
      arg is an argument VALUE (default / setting / config / user input),
      delivered through the value channel, never wired — a wiring source
      that is not a producer is a hard error.
    - Connected data-flow graph per strand. Every edge's sources must
      become available (input anchors, or already-emitted producers); an
      unreachable edge is a hard error.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from capdag.urn.media_urn import MediaUrn
from capdag.machine.graph import MachineStrand, NodeId
from capdag.machine.error import (
    CapDoesNotDeclareInputError,
    DisconnectedStrandError,
    NoStdinBindingError,
    NonProducerSecondaryArgError,
    RuntimeMediaInferenceError,
    UnknownCapError,
)

if TYPE_CHECKING:
    from capdag.cap.registry import FabricRegistry
    from capdag.planner.live_cap_fab import CapInput, Strand, StrandStep


def realize_strand(
    machine_strand: MachineStrand,
    registry: "FabricRegistry",
    source_urn: MediaUrn,
    strand_index: int,
) -> "Strand":
    """Realize a single resolved MachineStrand into a Strand, instantiating
    runtime media from source_urn (the concrete media flowing into the
    strand's input anchors).

    strand_index is used only for diagnostics.

    Raises MachineAbstractionError on any failure.
    """
    from capdag.planner.live_cap_fab import ArgSourceRef, CapInput, Strand, StrandStep, StrandStepType

    # Per-node runtime media. A convergence strand fans out from its input
    # and converges at a multi-input cap, so each node carries its own
    # runtime media — there is no single linear thread. Input anchors carry
    # the concrete input media (source_urn); each emitted cap sets its
    # target node's media.
    node_media: Dict[NodeId, MediaUrn] = {}
    for anchor in machine_strand.input_anchor_ids():
        node_media[anchor] = source_urn

    # The step (by stable token_id) that produced each node, for wiring
    # convergence args. Input anchors have no producing step.
    node_producer: Dict[NodeId, str] = {}

    edges = machine_strand.edges()
    emitted = [False] * len(edges)
    steps: List["StrandStep"] = []

    # Emit edges in dependency order: an edge is emittable once every one of
    # its wiring sources has a known runtime media (its producer has been
    # emitted, or it is an input anchor). Fan-in is permitted — the
    # emittability test is over ALL sources, not a single one.
    for _ in range(len(edges)):
        next_idx = None
        for i, e in enumerate(edges):
            if emitted[i]:
                continue
            if all(b.source in node_media for b in e.assignment):
                next_idx = i
                break
        if next_idx is None:
            raise DisconnectedStrandError(strand_index)
        emitted[next_idx] = True
        edge = edges[next_idx]

        cap_urn_str = str(edge.cap_urn)
        cap = registry.get_cached_cap(cap_urn_str)
        if cap is None:
            raise UnknownCapError(cap_urn_str)
        input_is_sequence, output_is_sequence = cap.sequence_shape()

        # The cap's MAIN input is the argument whose Stdin source URN is the
        # cap's `in=` (the one special input tag — a cap has exactly one
        # `in`). Its slot media URN selects the primary binding in the
        # resolver's assignment. Every other stdin-declaring arg is a
        # convergence input. Compared by tagged-URN equivalence, never as
        # strings; never by arg position.
        try:
            in_spec_urn = MediaUrn.from_string(edge.cap_urn.in_spec())
        except Exception as e:
            raise RuntimeMediaInferenceError(
                strand_index,
                cap_urn_str,
                edge.cap_urn.in_spec(),
                f"cap `in=` is not a valid media URN: {e}",
            ) from e

        stdin_arg = None
        for a in cap.args:
            if a.is_main_input(in_spec_urn):
                stdin_arg = a
                break
        if stdin_arg is None:
            raise CapDoesNotDeclareInputError(strand_index, cap_urn_str)
        stdin_arg_str = stdin_arg.media_urn

        try:
            stdin_arg_urn = MediaUrn.from_string(stdin_arg_str)
        except Exception as e:
            raise RuntimeMediaInferenceError(
                strand_index,
                cap_urn_str,
                stdin_arg_str,
                f"stdin arg URN is not a valid media URN: {e}",
            ) from e

        primary = None
        for b in edge.assignment:
            if b.cap_arg_media_urn.is_equivalent(stdin_arg_urn):
                primary = b
                break
        if primary is None:
            raise NoStdinBindingError(strand_index, cap_urn_str, stdin_arg_str)

        primary_media = node_media[primary.source]

        # ForEach synthesis — read the resolver's cardinality decision
        # (is_loop); the media URN is unchanged (a shape transition, not a
        # type transition).
        if edge.is_loop:
            steps.append(StrandStep(
                step_type=StrandStepType.FOR_EACH,
                from_spec=primary_media,
                to_spec=primary_media,
                media_def=primary_media,
            ))

        try:
            runtime_out = edge.cap_urn.infer_runtime_output_media(primary_media)
        except Exception as err:
            raise RuntimeMediaInferenceError(
                strand_index,
                cap_urn_str,
                str(primary_media),
                str(err),
            ) from err

        # Build the full explicit input list. Each binding names its
        # producer: a produced node → the producing step; an input anchor →
        # the strand input. Only the PRIMARY (stdin) input may be fed by an
        # input anchor; a non-main arg fed by a non-producer is an argument
        # VALUE, not a wiring, and is exposed hard (see module invariants).
        inputs: List["CapInput"] = []
        for b in edge.assignment:
            is_primary = b.cap_arg_media_urn.is_equivalent(stdin_arg_urn)
            producer_token = node_producer.get(b.source)
            if producer_token is not None:
                source = ArgSourceRef.step(producer_token)
            elif is_primary:
                source = ArgSourceRef.strand_input()
            else:
                raise NonProducerSecondaryArgError(
                    strand_index,
                    cap_urn_str,
                    str(b.cap_arg_media_urn),
                )
            inputs.append(CapInput(arg_urn=b.cap_arg_media_urn, source=source))

        step = StrandStep(
            step_type=StrandStepType.CAP,
            from_spec=primary_media,
            to_spec=runtime_out,
            cap_urn=edge.cap_urn,
            step_title=cap.title,
            specificity_val=edge.cap_urn.specificity(),
            input_is_sequence=input_is_sequence,
            output_is_sequence=output_is_sequence,
            inputs=inputs,
            # Preserve the resolved edge's stable identity so live updates
            # map back and so convergence args can reference this step as
            # their producer.
            token_id=edge.token_id,
        )
        node_media[edge.target] = runtime_out
        node_producer[edge.target] = edge.token_id
        steps.append(step)

    # The strand's realized target media is its output anchor's runtime
    # media. A well-formed strand has exactly one output anchor, produced by
    # a cap above; a missing anchor or media is a structural bug, exposed
    # hard.
    output_anchors = machine_strand.output_anchor_ids()
    if not output_anchors:
        raise DisconnectedStrandError(strand_index)
    output_anchor = output_anchors[0]
    if output_anchor not in node_media:
        raise DisconnectedStrandError(strand_index)
    target_media_urn = node_media[output_anchor]

    cap_step_count = sum(1 for s in steps if s.is_cap())
    total_steps = len(steps)
    return Strand(
        steps=steps,
        source_media_urn=source_urn,
        target_media_urn=target_media_urn,
        total_steps=total_steps,
        cap_step_count=cap_step_count,
        description=f"realized machine strand {strand_index}",
    )
