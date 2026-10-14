"""Tests of which steps of a machine run once per item, and inside which map
(capdag/docs/09-machine-notation.md §Iteration)."""

import pytest

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


def member(node: int, arg_is_sequence: bool) -> MemberShape:
    return MemberShape(node=node, arg_is_sequence=arg_is_sequence)


def shape(members, *outputs) -> StepShape:
    return StepShape(members=list(members), outputs=list(outputs))


def single(node: int) -> OutputShape:
    return OutputShape(node=node, is_sequence=False)


def sequence(node: int) -> OutputShape:
    return OutputShape(node=node, is_sequence=True)


def placed(steps, *sequences) -> IterationStructure:
    return iteration_of(steps, lambda node: node in sequences)


def once(scope: int) -> StepPlacement:
    """A step that runs once in `scope` and maps nothing."""
    return StepPlacement(placed_in=scope)


def map_of(structure: IterationStructure, step: int) -> int:
    """The map a step runs in; the step must map."""
    placement = structure.steps()[step]
    assert placement.maps, f"step {step} maps"
    assert placement.map != SCOPE_ROOT, "a map is never the machine itself"
    return placement.map


# TEST12746: a step given single values runs once, in the machine; a step
# given a sequence on an arg that takes one value maps over it, and what it
# produces lives in that map. A sequence on an arg that takes a sequence is
# given whole and maps nothing.
def test_12746_a_sequence_on_a_scalar_arg_opens_a_map():
    # 0 -> a -> 1 ; 1 is a declared sequence ; 1 -> b -> 2 ; 1 -> count(seq arg) -> 3
    steps = [
        shape([member(0, False)], sequence(1)),
        shape([member(1, False)], single(2)),
        shape([member(1, True)], single(3)),
    ]
    s = placed(steps)
    assert s.steps()[0] == once(SCOPE_ROOT)
    scope = map_of(s, 1)
    assert s.steps()[1].placed_in == SCOPE_ROOT
    assert s.steps()[1].mapped == [1]
    assert s.steps()[1].scope() == scope
    assert s.parent(scope) == SCOPE_ROOT
    assert s.sources(scope) == [1]
    assert s.opened_by(scope) == 1
    assert s.opened_by(SCOPE_ROOT) is None, "nothing opens the machine itself"
    assert s.node_scope(2) == scope
    assert s.node_scope(1) == SCOPE_ROOT
    assert s.steps()[2] == once(SCOPE_ROOT)
    assert s.steps()[2].scope() == SCOPE_ROOT
    assert not s.steps()[2].maps
    assert s.scope_count() == 2

    # The same machine with a single value where the sequence was: no map.
    steps = [
        shape([member(0, False)], single(1)),
        shape([member(1, False)], single(2)),
    ]
    s = placed(steps)
    assert s.steps() == [once(SCOPE_ROOT), once(SCOPE_ROOT)]
    assert s.scope_count() == 1
    # And a run that binds the machine's input to a sequence maps the first
    # step over it, the second joining that map.
    s = placed(steps, 0)
    scope = map_of(s, 0)
    assert s.steps()[0].mapped == [0]
    assert s.steps()[1] == once(scope)
    assert s.node_scope(2) == scope


# TEST12747: a step given a value a map produces joins that map; a step that
# takes a sequence and is given such a value folds what the map collected, in
# the scope that encloses the map. Where a step lands does not depend on the
# order the steps are given in.
def test_12747_a_step_joins_the_map_its_value_is_produced_in_and_a_fold_closes_it():
    # 0 (sequence) -> ocr -> 1 ; 1 -> summarize -> 2 ; 2 -> join(seq arg) -> 3 ; 3 -> title -> 4
    steps = [
        shape([member(0, False)], single(1)),
        shape([member(1, False)], single(2)),
        shape([member(2, True)], single(3)),
        shape([member(3, False)], single(4)),
    ]
    s = placed(steps, 0)
    scope = map_of(s, 0)
    assert s.steps()[1] == once(scope)
    assert s.steps()[2] == once(SCOPE_ROOT)
    assert s.steps()[3] == once(SCOPE_ROOT)
    assert s.node_scope(3) == SCOPE_ROOT

    reordered = [steps[3], steps[2], steps[1], steps[0]]
    r = placed(reordered, 0)
    scope = map_of(r, 3)
    assert r.steps()[2] == once(scope)
    assert r.steps()[1] == once(SCOPE_ROOT)
    assert r.steps()[0] == once(SCOPE_ROOT)
    assert r.opened_by(scope) == 3


# TEST12748: several sequences on args that take one value are zipped by one
# map; a single value beside them is given whole and does not move the step.
# The same node on two such args is one zipped member.
def test_12748_several_mapped_members_open_one_map():
    # 0, 1 sequences; 2 a single value. (1, b=0, c=2) -> compare -> 3
    steps = [shape([member(1, False), member(0, False), member(2, False)], single(3))]
    s = placed(steps, 0, 1)
    assert s.steps()[0].placed_in == SCOPE_ROOT
    assert s.steps()[0].mapped == [1, 0], "in the order the step lists them"
    assert s.sources(map_of(s, 0)) == [0, 1], "a map's sources have one fixed order"
    assert s.scope_count() == 2

    twice = [shape([member(0, False), member(0, False)], single(1))]
    assert placed(twice, 0).steps()[0].mapped == [0]


# TEST12749: a sequence produced inside a map and bound to an arg that takes
# one value opens a map inside that map. A fold of what the inner map produces
# is placed in the outer map: one value per outer item. From the machine the
# inner value is one flat sequence.
def test_12749_a_map_nests_and_a_fold_closes_one_level():
    # 0 docs (sequence) -> split -> 1 pages (declared sequence, per doc)
    # 1 -> ocr -> 2 text ; 2 -> join(seq arg) -> 3 doc text ; 3 -> all(seq arg) -> 4
    steps = [
        shape([member(0, False)], sequence(1)),
        shape([member(1, False)], single(2)),
        shape([member(2, True)], single(3)),
        shape([member(3, True)], single(4)),
    ]
    s = placed(steps, 0)
    outer, inner = map_of(s, 0), map_of(s, 1)
    assert s.steps()[1].placed_in == outer
    assert s.parent(inner) == outer
    assert s.depth(inner) == 2
    assert s.depth(outer) == 1
    assert s.depth(SCOPE_ROOT) == 0
    assert s.steps()[2] == once(outer)
    assert s.steps()[3] == once(SCOPE_ROOT)
    assert s.is_sequence_from(2, SCOPE_ROOT)
    assert s.is_sequence_from(2, outer)
    assert not s.is_sequence_from(2, inner)
    assert s.encloses(outer, inner)
    assert not s.encloses(inner, outer)
    assert s.encloses(SCOPE_ROOT, inner)

    # A step of the inner map that is also given the sequence the OUTER map
    # iterates takes the outer item — the doc its page came from — from inside
    # the inner map, two levels down.
    # (1, source=0) -> stamp -> 5
    steps = steps + [shape([member(1, False), member(0, False)], single(5))]
    s = placed(steps, 0)
    outer, inner = map_of(s, 0), map_of(s, 1)
    assert s.steps()[4].placed_in == outer
    assert map_of(s, 4) == inner, "it maps over the same pages: the same inner map"
    assert s.steps()[4].mapped == [1]
    assert s.item_map(0, inner) == outer, "the outer map's item, seen from the inner one"
    assert s.item_map(1, inner) == inner
    assert s.item_map(1, outer) is None, "from the outer map the pages are a sequence, given whole"


# TEST12750: two steps that map over the same sequence run in one map, so a
# third step given what each produced is given both for the same item — it
# joins the map and zips nothing. A step given a value of the map and the
# sequence the map iterates joins it too, taking the item.
def test_12750_steps_over_one_sequence_share_a_map():
    # 0 docs (sequence). 0 -> text -> 1 ; 0 -> meta -> 2 ; (1, meta=2) -> index -> 3
    # (1, original=0) -> compare -> 4
    steps = [
        shape([member(0, False)], single(1)),
        shape([member(0, False)], single(2)),
        shape([member(1, False), member(2, False)], single(3)),
        shape([member(1, False), member(0, False)], single(4)),
    ]
    s = placed(steps, 0)
    scope = map_of(s, 0)
    assert map_of(s, 1) == scope, "the same map, not a second one over docs"
    assert s.opened_by(scope) == 0
    assert s.scope_count() == 2
    assert s.steps()[2] == once(scope)
    assert s.steps()[3] == once(scope)
    # Inside the map the sequence it iterates is its item; a value the map
    # produces is not an item of anything, and from the machine the sequence
    # is given whole.
    assert s.item_map(0, scope) == scope
    assert s.item_map(1, scope) is None
    assert s.item_map(0, SCOPE_ROOT) is None

    # A step joins the map whichever of its members is listed first: a value
    # of the machine beside a value of the map, in either order.
    # 8 a single value of the machine. (8, text=1) -> annotate -> 9, and swapped.
    for members in ([member(8, False), member(1, False)], [member(1, False), member(8, False)]):
        joined = placed(steps + [shape(members, single(9))], 0)
        assert joined.steps()[4] == once(map_of(joined, 0)), members

    # A map is opened by the first of the steps that map in it, whichever of
    # them was placed first. Step 0 maps over the docs and waits for a value
    # step 2 makes, so step 1 — which maps over the docs too — is placed
    # before it.
    # (0, with=5) -> a -> 1 ; 0 -> b -> 2 ; 7 -> c -> 5
    waiting = [
        shape([member(0, False), member(5, False)], single(1)),
        shape([member(0, False)], single(2)),
        shape([member(7, False)], single(5)),
    ]
    w = placed(waiting, 0)
    assert map_of(w, 0) == map_of(w, 1)
    assert w.opened_by(map_of(w, 0)) == 0

    # A map is what it iterates IN THE SCOPE IT IS OPENED IN: the same
    # sequence mapped from two scopes is two maps.
    # 0 docs, 5 others: sequences. 0 -> split -> 1 (a declared sequence per doc)
    # 1 -> ocr -> 2: over each doc's pages, inside the map over docs.
    # 5 -> b -> 6 (a declared sequence per item of 5)
    # (1, all=6) -> t -> 7: neither map holds the other, so the step is placed
    # in the machine, mapping over every page there is, given 6 whole.
    steps = [
        shape([member(0, False)], sequence(1)),
        shape([member(1, False)], single(2)),
        shape([member(5, False)], sequence(6)),
        shape([member(1, False), member(6, True)], single(7)),
    ]
    s = placed(steps, 0, 5)
    per_doc, flat = map_of(s, 1), map_of(s, 3)
    assert s.sources(per_doc) == [1]
    assert s.sources(flat) == [1]
    assert s.parent(per_doc) == map_of(s, 0)
    assert s.parent(flat) == SCOPE_ROOT
    assert per_doc != flat


# TEST12751: there is no cross product. A step given a value of a map and a
# sequence the map does not iterate is not run for every pair: it is placed
# where that sequence lives, and the map's values are collected and zipped
# with it. Values of two maps that are not nested are zipped the same way,
# where both are seen.
def test_12751_an_outside_sequence_is_zipped_never_crossed():
    # 0 files, 5 keywords: sequences. 0 -> ocr -> 1 ; (1, k=5) -> tag -> 2
    steps = [
        shape([member(0, False)], single(1)),
        shape([member(1, False), member(5, False)], single(2)),
    ]
    s = placed(steps, 0, 5)
    first = map_of(s, 0)
    zipped = map_of(s, 1)
    assert s.steps()[1].placed_in == SCOPE_ROOT, "not inside the map over files"
    assert s.steps()[1].mapped == [1, 5]
    assert s.parent(zipped) == SCOPE_ROOT
    assert first != zipped

    # 0, 1 sequences. 0 -> a -> 2 ; 1 -> b -> 3 ; (2, other=3) -> compare -> 4
    steps = [
        shape([member(0, False)], single(2)),
        shape([member(1, False)], single(3)),
        shape([member(2, False), member(3, False)], single(4)),
    ]
    s = placed(steps, 0, 1)
    a, b = map_of(s, 0), map_of(s, 1)
    assert a != b
    assert s.steps()[2].placed_in == SCOPE_ROOT
    assert s.steps()[2].mapped == [2, 3]
    assert s.common_scope(a, b) == SCOPE_ROOT
    assert s.common_scope(a, a) == a

    # Inside a nested map the same holds one level down: a page's text and a
    # sequence of the machine are zipped in the machine, not run once per page
    # per item.
    # 0 docs (sequence), 9 stamps (sequence). 0 -> split -> 1 (declared sequence)
    # 1 -> ocr -> 2 ; (2, stamp=9) -> mark -> 3
    steps = [
        shape([member(0, False)], sequence(1)),
        shape([member(1, False)], single(2)),
        shape([member(2, False), member(9, False)], single(3)),
    ]
    s = placed(steps, 0, 9)
    assert s.steps()[2].placed_in == SCOPE_ROOT
    assert s.steps()[2].mapped == [2, 9]


# TEST12793: where a step lands does not depend on the order its members are
# listed in. A value of one map bound to an arg that takes one value, beside a
# sequence of an unrelated map bound to an arg that takes a sequence: neither
# map contains the other, so the step is placed where both are seen — mapping
# over the first, given the second whole — whichever is listed first.
def test_12793_placement_does_not_depend_on_member_order():
    # 0, 1 sequences. 0 -> a -> 2 (one value per item of 0)
    # 1 -> b -> 3 (a declared sequence per item of 1)
    # (2, all=3) -> t -> 4, and the same with its members swapped.
    for members in (
        [member(2, False), member(3, True)],
        [member(3, True), member(2, False)],
    ):
        steps = [
            shape([member(0, False)], single(2)),
            shape([member(1, False)], sequence(3)),
            shape(members, single(4)),
        ]
        s = placed(steps, 0, 1)
        assert s.steps()[2].placed_in == SCOPE_ROOT, members
        assert s.steps()[2].mapped == [2]
        scope = map_of(s, 2)
        assert scope != map_of(s, 0), "not the map the value was produced in"
        assert s.parent(scope) == SCOPE_ROOT


# TEST12752: steps that wait on one another cannot be placed, and the refusal
# names them.
def test_12752_steps_on_a_cycle_are_named():
    steps = [
        shape([member(0, False)], single(1)),
        shape([member(3, False)], single(2)),
        shape([member(2, False)], single(3)),
    ]
    with pytest.raises(CyclicSteps) as exc_info:
        iteration_of(steps, lambda _node: False)
    assert exc_info.value.steps == [1, 2]
