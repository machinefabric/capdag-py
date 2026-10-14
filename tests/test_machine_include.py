"""Tests of machines in step position: a header names another machine, and
its steps are written into the machine that includes it
(capdag/docs/09-machine-notation.md, §Machines in step position)."""

import json
import os

import pytest

from capdag.machine import (
    AmbiguousMachineMembersError,
    ConstantFailsValidationError,
    CyclicMachineReferenceError,
    DuplicateAliasError,
    FileMachineSource,
    InvalidIncludedMachineError,
    MachineAbstractionError,
    MachineInputBindingError,
    MachineOutputTakenTwiceError,
    MachineParseError,
    MachineReferenceWithoutSourceError,
    MachineSourceError,
    MapMachineSource,
    NoEdgesError,
    NoMachineSource,
    PolicyOnMachineError,
    SourceDoesNotConformToMachineInputError,
    StepPolicy,
    ON_ERROR_ABSENT,
    UndecidedMember,
    UndefinedAliasError,
    UnknownMachineInputError,
    UnknownMachineOutputError,
    UnknownMachineReferenceError,
    UnmatchedMachineMemberError,
    UnnamedMachineTargetError,
    UntypedMachineMemberError,
    file_machine_id,
    parse_machine,
    parse_machine_with_node_names,
    parse_machine_with_sources,
)

from tests.machine_fixtures import (
    all_edges,
    canonical,
    definition,
    edges_of,
    media,
    one_edge_of,
    output_of,
    stdin_arg,
)
from tests.test_machine_notation import (
    COMPARISON,
    HEADERS,
    NOTE,
    SERIES,
    binding_named,
    notation_registry,
    titled_registry,
)

# Two inputs of ONE type — `series`, and `bench` — and two outputs: `cmp`, and
# `scores`, one per residual. `res` is a node inside.
ANALYSE = (
    "[(series, benchmark=bench, window=20) -> compare -> (cmp, residuals=res)]"
    "[res -> score -> scores]"
)
# Two inputs of different types, in two strands, and one output.
PUB = "[report -> publish -> ()][res -> mean -> m]"
# An input that feeds an arg a constant can be written for.
WIN = "[(series, window=w) -> compare -> cmp]"
# A machine that includes `analyse`.
OUTER = (
    '[analyse machine "analyse"][(series=x, bench=y) -> analyse -> (cmp=c, scores=s)]'
    "[c -> publish -> ()]"
)

FETCH_TWO = '[(reference="a") -> fetch -> a][(reference="b") -> fetch -> b]'


def with_headers(wirings: str) -> str:
    return HEADERS + wirings


def library() -> MapMachineSource:
    """The machines above, each under its name."""
    source = MapMachineSource()
    for name, wirings in {"analyse": ANALYSE, "pub": PUB, "win": WIN, "outer": OUTER}.items():
        source.insert(name, with_headers(wirings))
    return source


def including(wirings: str):
    return parse_machine_with_sources(with_headers(wirings), notation_registry(), library(), None)


def flat(wirings: str):
    """The same wirings with no machine in them, for what an inclusion must
    equal."""
    return parse_machine(with_headers(wirings), notation_registry())


def refusal(wirings: str, kind) -> MachineAbstractionError:
    with pytest.raises(MachineParseError) as exc_info:
        including(wirings)
    cause = exc_info.value.cause
    assert isinstance(cause, kind), f"{wirings}: {cause!r}"
    return cause


def names_of_nodes(machine, names, ids):
    """Sorted, the names of the nodes `ids` picks out of each strand."""
    picked = []
    for index, strand in enumerate(machine.strands()):
        wanted = set(ids(strand))
        picked.extend(name for name, node_id in names[index].items() if node_id in wanted)
    return sorted(picked)


def output_anchors(strand):
    return strand.output_anchor_ids()


def input_anchors(strand):
    return strand.input_anchor_ids()


# TEST12803: a machine in step position is written out as its own steps: the
# including machine is the machine one would have written by hand with those
# steps in it. Its inputs are bound by the names its notation wrote — and by
# nothing else: binding the other way round is another machine. A node inside
# it is no input or output of the whole, and each of its steps says which
# machine step it came through.
def test_12803_an_included_machine_is_its_steps_written_in():
    inlined, names = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (cmp=c, scores=s)][c -> publish -> ()]"
    )
    by_hand = flat(
        FETCH_TWO
        + "[(a, benchmark=b, window=20) -> compare -> (c, residuals=r)][r -> score -> s]"
        "[c -> publish -> ()]"
    )
    assert inlined.is_equivalent(by_hand)
    assert len(all_edges(inlined)) == 5

    swapped, _ = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=b, bench=a) -> analyse -> (cmp=c, scores=s)][c -> publish -> ()]"
    )
    assert not swapped.is_equivalent(by_hand), "the names say which input each source is for"

    # What the whole gives and takes is what was written in it.
    assert names_of_nodes(inlined, names, output_anchors) == ["s"]
    assert names_of_nodes(inlined, names, input_anchors) == []
    # The node inside the included machine is a node of the whole, under a
    # name nothing written can bear.
    assert "analyse#1/res" in names[0]
    assert "res" not in names[0]

    for step in ("compare", "score"):
        assert one_edge_of(inlined, step).included_as == ["analyse#1"], step
    for edge in edges_of(inlined, "fetch") + edges_of(inlined, "publish"):
        assert edge.included_as == [], "a step the machine wrote itself"

    # The graph view is told the same.
    payload = json.loads(inlined.to_render_payload_json(titled_registry()))
    came_through = [
        edge for edge in payload["strands"][0]["edges"] if edge["included_as"] == ["analyse#1"]
    ]
    assert len(came_through) == 2


# TEST12804: a machine used twice is written in twice. Each use has nodes of
# its own: nothing of one use is a node of the other.
def test_12804_each_use_of_a_machine_has_nodes_of_its_own():
    inlined, names = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (cmp=c1, scores=s1)]"
        "[(series=b, bench=a) -> analyse -> (cmp=c2, scores=s2)]"
    )
    assert len(all_edges(inlined)) == 6
    first, second = names[0]["analyse#1/res"], names[0]["analyse#2/res"]
    assert first != second
    through = {}
    for edge in all_edges(inlined):
        if len(edge.included_as) == 1:
            through[edge.included_as[0]] = through.get(edge.included_as[0], 0) + 1
    assert through == {"analyse#1": 2, "analyse#2": 2}
    # Each use's scoring step reads its own residuals.
    reads = []
    for edge in edges_of(inlined, "score"):
        assert not edge.assignment[0].source.is_constant
        reads.append(edge.assignment[0].source.node)
    assert sorted(reads) == sorted([first, second])
    assert names_of_nodes(inlined, names, output_anchors) == ["c1", "c2", "s1", "s2"]

    # Two headers may name one machine: reading it for the first does not
    # make the second a circle, and each alias counts its own uses.
    aliased, names = including(
        '[one machine "analyse"][two machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> one -> (cmp=c1, scores=s1)]"
        "[(series=b, bench=a) -> two -> (cmp=c2, scores=s2)]"
    )
    assert aliased.is_equivalent(inlined)
    assert "one#1/res" in names[0] and "two#1/res" in names[0]


# TEST12805: an unnamed member of a machine step is matched to an input by
# type alone, and an unnamed target takes the one output the other targets
# leave. Where the types leave more than one answer, or a member has no type
# to be matched by, or fits nothing, the wiring is refused by name.
def test_12805_unnamed_members_of_a_machine_step_are_matched_by_type():
    produce = '[(reference="a") -> fetch -> a][a -> compare -> (c, residuals=r)]'
    unnamed, _ = including('[pub machine "pub"]' + produce + "[(c, r) -> pub -> m]")
    named, _ = including('[pub machine "pub"]' + produce + "[(res=r, report=c) -> pub -> (m=m)]")
    by_hand = flat(produce + "[c -> publish -> ()][r -> mean -> m]")
    assert unnamed.is_equivalent(named)
    assert unnamed.is_equivalent(by_hand)

    # What one machine step makes is typed for the next: the comparison
    # `analyse` gives is matched to the input of `pub` that takes one.
    chained, _ = including(
        '[analyse machine "analyse"][pub machine "pub"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (cmp=c, scores=s)][a -> compare -> (c0, residuals=r)]"
        "[(c, r) -> pub -> m]"
    )
    assert chained.is_equivalent(
        flat(
            FETCH_TWO
            + "[(a, benchmark=b, window=20) -> compare -> (c, residuals=r1)][r1 -> score -> s]"
            "[a -> compare -> (c0, residuals=r)][c -> publish -> ()][r -> mean -> m]"
        )
    )

    # `analyse` has two outputs: an unnamed target beside a named one takes
    # the other.
    one_named, _ = including(
        '[analyse machine "analyse"]' + FETCH_TWO + "[(series=a, bench=b) -> analyse -> (c, scores=s)]"
    )
    both_named, _ = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (cmp=c, scores=s)]"
    )
    assert one_named.is_equivalent(both_named)
    # An input a member named is said: the unnamed member beside it has the
    # other input, though both hold one type.
    one_unnamed, _ = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, b) -> analyse -> (cmp=c, scores=s)]"
    )
    assert one_unnamed.is_equivalent(both_named)
    other_unnamed, _ = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(a, series=b) -> analyse -> (cmp=c, scores=s)]"
    )
    assert not other_unnamed.is_equivalent(both_named)

    # Two sources of the one type its two inputs hold.
    ambiguous = refusal(
        '[analyse machine "analyse"]' + FETCH_TWO + "[(a, b) -> analyse -> (cmp=c, scores=s)]",
        AmbiguousMachineMembersError,
    )
    assert "machine 'analyse'" in str(ambiguous)
    # Which members to name, and the inputs each could be.
    series = canonical(SERIES)
    assert ambiguous.members == [
        UndecidedMember("a", series, ("bench", "series")),
        UndecidedMember("b", series, ("bench", "series")),
    ]
    # An input of the including machine, unnamed: nothing says what it is.
    untyped = refusal(
        '[analyse machine "analyse"]' + FETCH_TWO + "[(x, bench=b) -> analyse -> (cmp=c, scores=s)]",
        UntypedMachineMemberError,
    )
    assert "machine 'analyse'" in str(untyped)
    assert "(x)" in str(untyped)
    # A comparison, where the input left takes a series.
    unmatched = refusal(
        '[analyse machine "analyse"]' + produce + "[(c, bench=a) -> analyse -> (cmp=c2, scores=s)]",
        UnmatchedMachineMemberError,
    )
    assert (
        f"a member of type '{canonical(COMPARISON)}' fits no input left of machine 'analyse'"
        in str(unmatched)
    )
    # The member that fits no input is the one named, wherever it stands.
    second = refusal(
        '[analyse machine "analyse"]' + produce + "[(a, c) -> analyse -> (cmp=c2, scores=s)]",
        UnmatchedMachineMemberError,
    )
    assert f"a member of type '{canonical(COMPARISON)}'" in str(second)
    # Two outputs left for one unnamed target, and none left for it.
    two_left = refusal(
        '[analyse machine "analyse"]' + FETCH_TWO + "[(series=a, bench=b) -> analyse -> c]",
        UnnamedMachineTargetError,
    )
    assert "has 2 output(s) left to take (cmp, scores)" in str(two_left)
    none_left = refusal(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (x, cmp=c, scores=s)]",
        UnnamedMachineTargetError,
    )
    assert "has 0 output(s) left to take ()" in str(none_left)


# TEST12806: what a machine step may not be given, each refused by name: a
# name that is no input or no output of it, an input given nothing or given
# twice, an output taken twice, a source of the wrong type, and a policy.
def test_12806_a_machine_step_is_held_to_the_machines_inputs_and_outputs():
    def step(wiring: str, kind) -> str:
        return str(
            refusal(
                '[analyse machine "analyse"]' + FETCH_TWO + "[a -> compare -> made]" + wiring, kind
            )
        )

    assert "machine 'analyse' has no input named 'serie' (its inputs: bench, series)" in step(
        "[(serie=a, bench=b) -> analyse -> (cmp=c, scores=s)]", UnknownMachineInputError
    )
    assert "has no output named 'score' (its outputs: cmp, scores)" in step(
        "[(series=a, bench=b) -> analyse -> (cmp=c, score=s)]", UnknownMachineOutputError
    )
    assert "input 'bench' of machine 'analyse' is given 0 members" in step(
        "[(series=a) -> analyse -> (cmp=c, scores=s)]", MachineInputBindingError
    )
    assert "input 'series' of machine 'analyse' is given 2 members" in step(
        "[(series=a, series=b, bench=b) -> analyse -> (cmp=c, scores=s)]", MachineInputBindingError
    )
    assert "output 'cmp' of machine 'analyse' is taken twice" in step(
        "[(series=a, bench=b) -> analyse -> (cmp=c, cmp=d)]", MachineOutputTakenTwiceError
    )
    assert (
        f"input 'series' of machine 'analyse' holds '{canonical(SERIES)}', "
        f"and its source is '{canonical(COMPARISON)}'"
    ) in step(
        "[(series=made, bench=b) -> analyse -> (cmp=c, scores=s)]",
        SourceDoesNotConformToMachineInputError,
    )
    assert "'analyse' is a machine, and a policy is written on it" in step(
        "[(series=a, bench=b) -> analyse{retry=2} -> (cmp=c, scores=s)]", PolicyOnMachineError
    )

    # A cap header and a machine header name steps in one space: one alias is
    # declared once, whichever kind declares it first.
    for headers in ['[fetch machine "analyse"]', '[twice machine "analyse"][twice machine "pub"]']:
        with pytest.raises(MachineParseError) as exc_info:
            including(headers + FETCH_TWO)
        assert isinstance(exc_info.value.cause, DuplicateAliasError), headers
    # A machine header is a declaration like any other: with no wiring after
    # it, the machine has headers and no steps.
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine_with_sources(
            '[analyse machine "analyse"]', notation_registry(), library(), None
        )
    assert isinstance(exc_info.value.cause, NoEdgesError)


# TEST12807: a reference that does not resolve, a machine that is not a valid
# machine, and a circle of inclusions are each refused — a header nothing uses
# included. A circle is one failure of the whole, naming every machine on the
# way round, whichever machine the reading started from.
def test_12807_a_reference_must_resolve_to_a_valid_machine_and_never_to_itself():
    lost = refusal(
        '[lost machine "nowhere"][(reference="a") -> fetch -> a]', UnknownMachineReferenceError
    )
    assert 'machine header \'lost\' refers to "nowhere", which does not resolve: ' in str(lost)
    assert 'no machine is held under "nowhere"' in str(lost)
    # With nothing to resolve against at all, the refusal says that.
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine_with_sources(
            with_headers('[lost machine "nowhere"][(reference="a") -> fetch -> a]'),
            notation_registry(),
            NoMachineSource(),
            None,
        )
    assert isinstance(exc_info.value.cause, MachineReferenceWithoutSourceError)

    source = library()
    source.insert("broken", with_headers("[p -> nothing -> q]"))
    source.insert("a", with_headers('[inner machine "b"][(reference="x") -> fetch -> s]'))
    source.insert("b", with_headers('[back machine "a"][(reference="y") -> fetch -> t]'))

    def parse_from(notation: str, machine_id):
        with pytest.raises(MachineParseError) as exc_info:
            parse_machine_with_sources(notation, notation_registry(), source, machine_id)
        cause = exc_info.value.cause
        assert isinstance(cause, MachineAbstractionError), repr(cause)
        return cause

    invalid = parse_from(
        with_headers('[bad machine "broken"][(reference="a") -> fetch -> a]'), None
    )
    assert isinstance(invalid, InvalidIncludedMachineError)
    assert "machine 'bad' (\"broken\") is not a valid machine: " in str(invalid)
    assert isinstance(invalid.cause, MachineParseError)
    assert isinstance(invalid.cause.cause, UndefinedAliasError)
    assert "'nothing'" in str(invalid.cause)

    a = with_headers('[inner machine "b"][(reference="x") -> fetch -> s]')
    circle = parse_from(a, "a")
    assert isinstance(circle, CyclicMachineReferenceError)
    assert circle.chain == ["a", "b", "a"]
    assert "a -> b -> a" in str(circle)
    # Read as notation the source does not know: the circle is found one step
    # later, and is the same circle.
    circle = parse_from(a, None)
    assert isinstance(circle, CyclicMachineReferenceError)
    assert circle.chain == ["b", "a", "b"]
    # A machine that only leads to the circle is not on it.
    leading = with_headers('[first machine "a"][(reference="z") -> fetch -> u]')
    circle = parse_from(leading, "top")
    assert isinstance(circle, CyclicMachineReferenceError)
    assert circle.chain == ["a", "b", "a"]


# TEST12808: a constant written for an input of a machine step is the value of
# every arg that input feeds inside, and is held to that arg's validation
# there.
def test_12808_a_constant_for_a_machine_input_reaches_the_arg_inside():
    fetch = '[(reference="a") -> fetch -> a]'
    inlined, _ = including('[win machine "win"]' + fetch + "[(series=a, w=30) -> win -> c]")
    assert inlined.is_equivalent(flat(fetch + "[(a, window=30) -> compare -> c]"))
    window = binding_named(one_edge_of(inlined, "compare"), "window")
    assert window.source.is_constant
    assert window.source.constant == 30
    assert isinstance(window.source.constant, int)

    refused = refusal(
        '[win machine "win"]' + fetch + "[(series=a, w=1000) -> win -> c]",
        ConstantFailsValidationError,
    )
    assert "arg 'window' refuses the constant 1000" in str(refused)


# TEST12818: a policy written on a step inside an included machine is that
# step's policy in the whole: the step is attempted again, or its failure
# tolerated, exactly as it would be where it was written.
def test_12818_a_step_keeps_its_policy_where_it_is_included():
    source = library()
    source.insert(
        "careful",
        with_headers("[(series, benchmark=bench) -> compare{retry=2, on_error=absent} -> cmp]"),
    )
    inlined, _ = parse_machine_with_sources(
        with_headers(
            '[careful machine "careful"]' + FETCH_TWO + "[(series=a, bench=b) -> careful -> c]"
        ),
        notation_registry(),
        source,
        None,
    )
    assert one_edge_of(inlined, "compare").policy == StepPolicy(retry=2, on_error=ON_ERROR_ABSENT)
    assert inlined.is_equivalent(
        flat(FETCH_TWO + "[(a, benchmark=b) -> compare{retry=2, on_error=absent} -> c]")
    )
    for fetch in edges_of(inlined, "fetch"):
        assert fetch.policy.is_default()


# TEST12809: a machine that includes a machine that includes a machine is one
# flat machine: a step says every machine step it came through, outermost
# first. An output of an included machine that nothing takes is not an output
# of the whole — the step that makes it still runs.
def test_12809_inclusion_nests_and_an_untaken_output_is_not_the_wholes():
    inlined, names = including(
        '[deep machine "outer"]' + FETCH_TWO + "[(x=a, y=b) -> deep -> (s=out)]"
    )
    by_hand = flat(
        FETCH_TWO
        + "[(a, benchmark=b, window=20) -> compare -> (c, residuals=r)][r -> score -> s]"
        "[c -> publish -> ()]"
    )
    assert inlined.is_equivalent(by_hand)
    assert one_edge_of(inlined, "compare").included_as == ["deep#1", "analyse#1"]
    assert one_edge_of(inlined, "publish").included_as == ["deep#1"]
    assert names_of_nodes(inlined, names, output_anchors) == ["out"]

    partial, names = including(
        '[analyse machine "analyse"]'
        + FETCH_TWO
        + "[(series=a, bench=b) -> analyse -> (cmp=c)][c -> publish -> ()]"
    )
    assert names_of_nodes(partial, names, output_anchors) == []
    assert one_edge_of(partial, "score").outputs == [], "what it makes is taken by nothing"
    assert partial.is_equivalent(
        flat(
            FETCH_TWO
            + "[(a, benchmark=b, window=20) -> compare -> (c, residuals=r)][r -> score -> ()]"
            "[c -> publish -> ()]"
        )
    )


LOOSE = 'cap:in="media:fmt=json;list;record;time-series";loose;out="media:enc=utf-8"'
TIGHT = 'cap:in="media:enc=utf-8;note";tight;out="media:tightened"'


def registry_with_a_refinement():
    """The registry of the tests above, with a step whose output is declared
    more loosely than the step after it asks for."""
    registry = notation_registry()
    registry.add_caps_to_cache([
        definition(
            LOOSE,
            "loose",
            [stdin_arg(SERIES, "series")],
            [output_of("media:enc=utf-8", "text", "Some text")],
        ),
        definition(
            TIGHT,
            "tight",
            [stdin_arg(NOTE, "note")],
            [output_of("media:tightened", "tightened", "Tightened")],
        ),
    ])
    return registry


# TEST12810: an included machine is what it is alone. Inside `refine`, the
# second step asks for a tighter type than the first declares, which makes the
# node between them hold the tighter type; written into another machine that
# node holds it still, and the machine resolves as it did alone.
def test_12810_a_node_of_an_included_machine_holds_the_type_it_held_alone():
    registry = registry_with_a_refinement()
    headers = HEADERS + "[loose " + LOOSE + "][tight " + TIGHT + "]"
    refine = headers + "[s -> loose -> t][t -> tight -> u]"
    alone, _ = parse_machine_with_node_names(refine, registry)
    note = media(NOTE)
    assert any(held.is_equivalent(note) for held in alone.strands()[0].nodes()), \
        "the node between the steps holds the tighter type"

    source = MapMachineSource()
    source.insert("refine", refine)
    inlined, names = parse_machine_with_sources(
        headers + '[refine machine "refine"][(reference="a") -> fetch -> a][a -> refine -> u]',
        registry,
        source,
        None,
    )
    assert "refine#1/t" in names[0]
    assert inlined.strands()[0].node_urn(names[0]["refine#1/t"]).is_equivalent(note)
    by_hand = parse_machine(
        headers + '[(reference="a") -> fetch -> a][a -> loose -> t][t -> tight -> u]', registry
    )
    assert inlined.is_equivalent(by_hand)


# TEST12811: machines in files. A reference is a path relative to the file
# that wrote it — not to where the reading started — and a machine is known by
# its file, however the path to it is spelled: a file that reaches itself
# through another spelling is a circle.
def test_12811_file_references_are_relative_to_the_including_file(tmp_path):
    root = tmp_path / "root"
    lib = root / "lib"
    lib.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    top = root / "top.machine"
    top_notation = with_headers(
        '[deep machine "lib/outer.machine"]' + FETCH_TWO + "[(x=a, y=b) -> deep -> (s=out)]"
    )
    top.write_text(top_notation, encoding="utf-8")
    # `outer` names `analyse` beside itself, in `lib/`.
    (lib / "outer.machine").write_text(
        with_headers(OUTER.replace('"analyse"', '"analyse.machine"', 1)), encoding="utf-8"
    )
    (lib / "analyse.machine").write_text(with_headers(ANALYSE), encoding="utf-8")

    source = FileMachineSource(elsewhere)
    inlined, _ = parse_machine_with_sources(
        top_notation, notation_registry(), source, file_machine_id(top)
    )
    assert len(all_edges(inlined)) == 5, "every reference is read relative to the file that wrote it"

    # Notation from no file reads its references relative to the base.
    parse_machine_with_sources(top_notation, notation_registry(), FileMachineSource(root), None)
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine_with_sources(top_notation, notation_registry(), source, None)
    unresolved = exc_info.value.cause
    assert isinstance(unresolved, UnknownMachineReferenceError), repr(unresolved)
    assert 'refers to "lib/outer.machine"' in str(unresolved)
    assert "outer.machine: " in str(unresolved)

    itself = root / "itself.machine"
    itself_notation = with_headers(
        '[again machine "lib/../itself.machine"][(reference="a") -> fetch -> a]'
    )
    itself.write_text(itself_notation, encoding="utf-8")
    machine_id = file_machine_id(itself)
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine_with_sources(itself_notation, notation_registry(), source, machine_id)
    circle = exc_info.value.cause
    assert isinstance(circle, CyclicMachineReferenceError), repr(circle)
    assert circle.chain == [machine_id, machine_id]

    # A file that is not there has no id.
    with pytest.raises(MachineSourceError) as exc_info:
        file_machine_id(root / "absent.machine")
    assert not exc_info.value.no_source
    assert "absent.machine" in str(exc_info.value)
    # A machine's id is its file, however the path to it is spelled.
    assert file_machine_id(os.path.join(str(lib), "..", "top.machine")) == file_machine_id(top)
