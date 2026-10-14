"""Tests of machine notation end to end through the parser and the resolver:
named members, constants, taken outputs, sources and sinks, step policy, the
URN of a node, and the canonical form (capdag/docs/09-machine-notation.md)."""

import json

import pytest

from capdag.machine import (
    FORMAT_LINE_BASED,
    AmbiguousMachineNotationError,
    ArgBoundTwiceError,
    ConstantFailsValidationError,
    Machine,
    MachineAbstractionError,
    MachineParseError,
    MachineReferenceWithoutSourceError,
    MainInputUnboundError,
    NodeMediaConflictError,
    NoMainOutputError,
    OutputTakenTwiceError,
    SourceDoesNotConformToArgError,
    StepPolicy,
    ON_ERROR_ABSENT,
    UndecidedMember,
    UnknownArgNameError,
    UnknownOutputNameError,
    UnmatchedSourceInCapArgsError,
    UntypedMachineInputError,
    parse_machine,
    parse_machine_with_node_names,
)
from capdag.machine.constant import constant_text
from capdag.machine.graph import NodeBijection

from tests.machine_fixtures import (
    canonical,
    definition,
    flag_arg,
    media,
    media_def,
    one_edge_of,
    output_of,
    registry_of,
    stdin_arg,
)

SERIES = "media:fmt=json;list;record;time-series"
BENCHMARK = "media:benchmark;fmt=json;list;record;time-series"
WINDOW = "media:integer;window"
LABEL = "media:enc=utf-8;label"
TAG = "media:enc=utf-8;tag"
COMPARISON = "media:comparison;fmt=json;record"
RESIDUALS = "media:fmt=json;list;record;residual"
NOTE = "media:enc=utf-8;note"
REFERENCE = "media:enc=utf-8;series-ref"


def compare_cap():
    """A main input and a second arg that accepts the same type, two
    constants' worth of options, a sequence arg, and three outputs."""
    return definition(
        f'cap:in="{SERIES}";compare;out="{COMPARISON}"',
        "compare",
        [
            stdin_arg(SERIES, "series"),
            flag_arg(BENCHMARK, "benchmark").accepting(SERIES),
            flag_arg(WINDOW, "window"),
            flag_arg(LABEL, "label"),
            flag_arg(TAG, "tags", is_sequence=True),
        ],
        [
            output_of(RESIDUALS, "residuals", "Residuals", is_sequence=True),
            output_of(COMPARISON, "comparison", "The comparison"),
            output_of(NOTE, "note", "A note").as_optional(True),
        ],
    )


def fetch_cap():
    """A source. Its `in=` is void; it is given a reference and nothing else."""
    return definition(
        f'cap:in=media:void;fetch;out="{SERIES}"',
        "fetch",
        [flag_arg(REFERENCE, "reference")],
        [output_of(SERIES, "series", "The series")],
    )


def publish_cap():
    """A sink. Its `out=` is void."""
    return definition(
        f'cap:in="{COMPARISON}";publish;out=media:void',
        "publish",
        [stdin_arg(COMPARISON, "report")],
        [],
    )


def mean_cap():
    """One value from a sequence of residuals — maps nothing."""
    return definition(
        f'cap:in="{RESIDUALS}";mean;out="media:mean;numeric"',
        "mean",
        [stdin_arg(RESIDUALS, "rows", is_sequence=True)],
        [output_of("media:mean;numeric", "mean", "The mean")],
    )


def score_cap():
    """One value per residual — a sequence of them maps it."""
    return definition(
        f'cap:in="{RESIDUALS}";score;out="media:numeric;score"',
        "score",
        [stdin_arg(RESIDUALS, "row")],
        [output_of("media:numeric;score", "score", "The score")],
    )


def notation_registry():
    """The caps above and the media definitions their constants are held to:
    a window of 1 to 365, a label that is a string of three allowed words,
    tags that are strings, and references of at most twelve bytes."""
    registry = registry_of([compare_cap(), fetch_cap(), publish_cap(), mean_cap(), score_cap()])
    registry.add_spec(media_def(WINDOW, {"min": 1.0, "max": 365.0}, {"type": "integer"}))
    registry.add_spec(
        media_def(LABEL, {"allowed_values": ["mean", "median", "max"]}, {"type": "string"})
    )
    registry.add_spec(media_def(TAG, None, {"type": "string"}))
    registry.add_spec(media_def(REFERENCE, {"max_length": 12}))
    return registry


def titled_registry():
    """The notation registry with a media definition, and so a title, for
    every media a node of the tests' machines holds: what a render payload
    needs."""
    registry = notation_registry()
    for urn in (SERIES, BENCHMARK, COMPARISON, RESIDUALS, NOTE, "media:mean;numeric", "media:numeric;score"):
        registry.add_spec(media_def(urn))
    return registry


HEADERS = (
    '[compare cap:in="media:fmt=json;list;record;time-series";compare;'
    'out="media:comparison;fmt=json;record"]'
    '[fetch cap:in=media:void;fetch;out="media:fmt=json;list;record;time-series"]'
    '[publish cap:in="media:comparison;fmt=json;record";publish;out=media:void]'
    '[mean cap:in="media:fmt=json;list;record;residual";mean;out="media:mean;numeric"]'
    '[score cap:in="media:fmt=json;list;record;residual";score;out="media:numeric;score"]'
)


def machine_of(wirings: str) -> Machine:
    return parse_machine(HEADERS + wirings, notation_registry())


def resolution_error(wirings: str, registry=None, headers: str = HEADERS) -> MachineAbstractionError:
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(headers + wirings, registry or notation_registry())
    cause = exc_info.value.cause
    assert isinstance(cause, MachineAbstractionError), f"{wirings}: expected a resolution error, got {cause!r}"
    return cause


def only_edge(machine: Machine):
    """The one edge of a one-step machine."""
    assert machine.strand_count() == 1
    assert len(machine.strands()[0].edges()) == 1
    return machine.strands()[0].edges()[0]


def bindings_of(machine: Machine, edge):
    """What each arg of an edge is bound to, by the arg's name: a node's URN,
    or a constant."""
    strand = machine.strands()[0]
    bound = []
    for binding in edge.assignment:
        if binding.source.is_constant:
            source = "constant " + constant_text(binding.source.constant)
        else:
            source = f"node {binding.source.node} {strand.node_urn(binding.source.node)}"
        bound.append((binding.arg_name, source))
    return bound


def sources_of(bound, arg: str):
    return [source for name, source in bound if name == arg]


def binding_named(edge, arg: str):
    for binding in edge.assignment:
        if binding.arg_name == arg:
            return binding
    raise AssertionError(f"no binding of arg {arg!r} on {edge!r}")


def equivalent(a: str, b: str) -> bool:
    return machine_of(a).is_equivalent(machine_of(b))


# TEST12737: a member that names its arg binds that arg, whatever its type
# could also fit. Two inputs of one type are told apart only so: unnamed they
# are refused, and naming the other one is another machine. A name is the
# definition's label for the arg; the binding records the arg's media URN.
def test_12737_a_named_member_binds_the_arg_it_names():
    text = "[(path, benchmark=bench) -> compare -> result]"
    machine, names = parse_machine_with_node_names(HEADERS + text, notation_registry())
    edge = only_edge(machine)
    assert len(edge.assignment) == 2
    # Both are inputs of the machine and both hold a series: the benchmark arg
    # ACCEPTS a series, and is identified by its own URN.
    series, benchmark = binding_named(edge, "series"), binding_named(edge, "benchmark")
    for each in (series, benchmark):
        assert not each.source.is_constant
        assert machine.strands()[0].node_urn(each.source.node).is_equivalent(media(SERIES)), each.arg_name
    assert series.source.node != benchmark.source.node, "two nodes"
    assert benchmark.cap_arg_media_urn.is_equivalent(media(BENCHMARK))
    assert series.cap_arg_media_urn.is_equivalent(media(SERIES))

    # Which node is the benchmark is what the machine says, and a host
    # addresses the two by the names as written.
    assert names[0]["bench"] == benchmark.source.node
    assert names[0]["path"] == series.source.node
    # Two inputs that hold one type come in the order their nodes were made.
    assert machine.strands()[0].input_anchor_ids() == [names[0]["path"], names[0]["bench"]]

    # Unnamed, nothing says which of the two series is the benchmark.
    untyped = resolution_error("[(path, bench) -> compare -> result]")
    assert isinstance(untyped, UntypedMachineInputError)
    assert "(path, bench)" in str(untyped)

    # The same two, produced by steps: each has a type, and it fits two args.
    produced = '[(reference="a") -> fetch -> a][(reference="b") -> fetch -> b]'
    # The refusal says which members to name, by the names the text gave
    # them, and the args each could be for.
    series_urn = canonical(SERIES)
    ambiguous = resolution_error(produced + "[(a, b) -> compare -> result]")
    assert isinstance(ambiguous, AmbiguousMachineNotationError)
    assert ambiguous.members == [
        UndecidedMember("a", series_urn, ("series", "benchmark")),
        UndecidedMember("b", series_urn, ("series", "benchmark")),
    ]
    assert f"name them: 'a' ({series_urn}) could be series or benchmark; 'b' (" in str(ambiguous)
    # A member is named by the name the text gave it, wherever it stands in
    # its group and whichever node was written first.
    swapped = resolution_error(produced + "[(b, a) -> compare -> result]")
    assert isinstance(swapped, AmbiguousMachineNotationError)
    assert [member.node for member in swapped.members] == ["b", "a"]
    # The args a member could be for are the ones no name took: with the
    # first of three bound by name, the other two are what is left to say.
    mix_urn = f'cap:in="{SERIES}";mix;out="{COMPARISON}"'
    with_mix = notation_registry()
    with_mix.add_caps_to_cache([
        definition(
            mix_urn,
            "mix",
            [
                stdin_arg(SERIES, "first"),
                flag_arg("media:second;fmt=json;list;record;time-series", "second").accepting(SERIES),
                flag_arg("media:third;fmt=json;list;record;time-series", "third").accepting(SERIES),
            ],
            [output_of(COMPARISON, "mixed", "The mix")],
        )
    ])
    mixed = resolution_error(
        produced + '[(reference="c") -> fetch -> c][(first=c, a, b) -> mix -> result]',
        registry=with_mix,
        headers=HEADERS + "[mix " + mix_urn + "]",
    )
    assert mixed.members == [
        UndecidedMember("a", series_urn, ("second", "third")),
        UndecidedMember("b", series_urn, ("second", "third")),
    ]
    said = machine_of(produced + "[(a, benchmark=b) -> compare -> result]")
    assert len(said.strands()[0].edges()) == 3
    # An arg a member named is said: an unnamed member is not matched into it
    # as well. Two unnamed series beside a named benchmark have one arg left
    # between them, and that is what the refusal says — not that they tie.
    third = '[(reference="c") -> fetch -> c]'
    assert isinstance(
        resolution_error(produced + third + "[(a, c, benchmark=b) -> compare -> result]"),
        UnmatchedSourceInCapArgsError,
    )

    # A member that fits no arg at all is the one the refusal names, wherever
    # it stands: here the second, a comparison where a series is taken.
    unfit = resolution_error(produced + "[a -> compare -> made][(b, made) -> compare -> result]")
    assert isinstance(unfit, UnmatchedSourceInCapArgsError)
    assert f"source URN '{canonical(COMPARISON)}'" in str(unfit)

    # A name the cap does not declare, with the names it does.
    unknown = resolution_error("[(path, baseline=bench) -> compare -> result]")
    assert isinstance(unknown, UnknownArgNameError)
    assert "'baseline'" in str(unknown)
    assert "(it declares: series, benchmark, window, label, tags)" in str(unknown)
    # A name is not read out of a URN: `time-series` is a tag of the arg's
    # type, and no arg is called that.
    assert isinstance(
        resolution_error("[(time-series=path) -> compare -> result]"), UnknownArgNameError
    )
    # A produced node of another type, named into an arg that does not accept it.
    mismatch = resolution_error("[path -> compare -> r][(series=p2, benchmark=r) -> compare -> r2]")
    assert isinstance(mismatch, SourceDoesNotConformToArgError)
    assert f"arg 'benchmark' accepts '{canonical(SERIES)}'" in str(mismatch)
    assert f"its source is '{canonical(COMPARISON)}'" in str(mismatch)
    # An arg that takes one value, named twice.
    twice = resolution_error("[(path, benchmark=b1, benchmark=b2) -> compare -> result]")
    assert isinstance(twice, ArgBoundTwiceError)
    assert "arg 'benchmark' takes one value and is named by 2 members" in str(twice)


# TEST12738: a constant is the arg's value, written in the machine. It is held
# to the validation of the arg's media definition when the machine is
# resolved, and a sequence arg gathers the constants named into it, in order.
def test_12738_a_constant_is_bound_and_validated():
    machine = machine_of('[(path, window=20, label="mean", tags="a", tags="b") -> compare -> result]')
    bound = bindings_of(machine, only_edge(machine))
    assert sources_of(bound, "window") == ["constant 20"]
    assert sources_of(bound, "label") == ['constant "mean"']
    assert sources_of(bound, "tags") == ['constant "a"', 'constant "b"'], "gathered in the order written"
    # A constant is no node: the machine has one input and one output.
    assert len(machine.strands()[0].nodes()) == 2
    assert len(machine.strands()[0].input_anchor_ids()) == 1

    def refused(wiring: str) -> str:
        error = resolution_error(wiring)
        assert isinstance(error, ConstantFailsValidationError), f"{wiring}: {error!r}"
        return str(error)

    # Outside the range the media definition gives.
    low = refused("[(path, window=0) -> compare -> result]")
    assert "arg 'window' refuses the constant 0: " in low
    assert "minimum value 1" in low
    assert "maximum value 365" in refused("[(path, window=366) -> compare -> result]")
    # Inside the range and not the kind of value the schema asks for.
    assert "schema" in refused("[(path, window=2.5) -> compare -> result]")
    assert "schema" in refused('[(path, window="20") -> compare -> result]')
    # A word the definition does not allow.
    assert 'allowed values: ["mean", "median", "max"]' in refused(
        '[(path, label="mode") -> compare -> result]'
    )
    # An arg whose media definition is not at hand cannot be given a constant
    # nobody could check.
    unchecked = refused("[(path, benchmark=[1, 2]) -> compare -> result]")
    assert "arg 'benchmark' refuses the constant [1,2]" in unchecked
    assert "not available" in unchecked

    # The bounds themselves are allowed.
    machine_of("[(path, window=1) -> compare -> result]")
    machine_of("[(path, window=365) -> compare -> result]")

    # A string's length is its UTF-8 bytes: six two-byte characters fill a
    # reference of twelve, and a seventh breaks it.
    machine_of('[(reference="éééééé") -> fetch -> s]')
    assert "maximum length 12" in refused('[(reference="ééééééé") -> fetch -> s]')

    # A schema's required properties are held: a benchmark written as an
    # object says its points.
    with_benchmark_schema = notation_registry()
    with_benchmark_schema.add_spec(
        media_def(
            BENCHMARK,
            None,
            {"type": "object", "required": ["points"], "properties": {"points": {"type": "array"}}},
        )
    )
    parse_machine(HEADERS + '[(path, benchmark={"points": [1, 2]}) -> compare -> r]', with_benchmark_schema)
    missing = resolution_error(
        '[(path, benchmark={"scale": 2}) -> compare -> r]', registry=with_benchmark_schema
    )
    assert isinstance(missing, ConstantFailsValidationError), repr(missing)
    assert "schema" in str(missing)

    # A constant is not a node. One input feeding two args, and the same input
    # feeding one of them beside a constant for the other, have the same nodes
    # and are different machines.
    with_benchmark_def = notation_registry()
    with_benchmark_def.add_spec(media_def(BENCHMARK))

    def in_registry(wirings: str) -> Machine:
        return parse_machine(HEADERS + wirings, with_benchmark_def)

    twice = in_registry("[(series=p, benchmark=p) -> compare -> r]")
    once = in_registry("[(series=p, benchmark=[1, 2]) -> compare -> r]")
    assert len(twice.strands()[0].nodes()) == len(once.strands()[0].nodes())
    assert not twice.is_equivalent(once)
    assert not once.is_equivalent(twice)

    # Two machines that give an arg different constants are different machines.
    assert equivalent("[(path, window=20) -> compare -> r]", "[(p, window=20) -> compare -> out]")
    assert not equivalent("[(path, window=20) -> compare -> r]", "[(path, window=21) -> compare -> r]")
    assert not equivalent("[(path, window=20) -> compare -> r]", "[path -> compare -> r]")


# TEST12739: the outputs a wiring takes. An unnamed target takes the step's
# main output, a named one the output of that name; one that is not taken is
# discarded; a sink takes none and a source is given nothing.
def test_12739_outputs_sources_and_sinks():
    both = machine_of("[path -> compare -> (result, residuals=res)]")
    edge = only_edge(both)
    # Sorted by output URN, each node holding what its output is declared to be.
    assert len(edge.outputs) == 2
    assert [canonical(str(o.output_media_urn)) for o in edge.outputs] == sorted(
        canonical(str(o.output_media_urn)) for o in edge.outputs
    )
    is_sequence = {
        output.output_name: both.strands()[0].node_is_sequence(output.node)
        for output in edge.outputs
    }
    assert is_sequence == {"comparison": False, "residuals": True}
    main = edge.main_target()
    assert main is not None, "the main output is taken"
    assert both.strands()[0].node_urn(main).is_equivalent(media(COMPARISON))
    assert len(both.strands()[0].output_anchor_ids()) == 2

    # The main output need not be taken, and the one that is, is still named.
    residuals_only = machine_of("[path -> compare -> (residuals=res)]")
    assert only_edge(residuals_only).main_target() is None
    assert len(only_edge(residuals_only).outputs) == 1
    assert not residuals_only.is_equivalent(both)
    # Which outputs are taken is not their order in the text.
    assert equivalent(
        "[path -> compare -> (result, residuals=res)]", "[p -> compare -> (residuals=r, out)]"
    )

    unknown = resolution_error("[path -> compare -> (result, errors=e)]")
    assert isinstance(unknown, UnknownOutputNameError)
    assert "'errors'" in str(unknown)
    assert "(it declares: residuals, comparison, note)" in str(unknown)
    assert isinstance(
        resolution_error("[path -> compare -> (residuals=a, residuals=b)]"), OutputTakenTwiceError
    )
    # The main output taken unnamed and by its name is the same output twice.
    assert isinstance(
        resolution_error("[path -> compare -> (a, comparison=b)]"), OutputTakenTwiceError
    )

    # A sink: nothing is taken, and its strand has no output.
    sink = machine_of("[report -> publish -> ()]")
    assert only_edge(sink).outputs == []
    assert sink.strands()[0].output_anchor_ids() == []
    assert len(sink.strands()[0].input_anchor_ids()) == 1
    # A sink has no main output to take.
    assert isinstance(resolution_error("[report -> publish -> done]"), NoMainOutputError)

    # A source: given nothing, or only what its constants say.
    source = machine_of("[() -> fetch -> s]")
    assert only_edge(source).assignment == []
    assert source.strands()[0].input_anchor_ids() == []
    referenced = machine_of('[(reference="fred/UNRATE") -> fetch -> s]')
    assert bindings_of(referenced, only_edge(referenced)) == [
        ("reference", 'constant "fred/UNRATE"')
    ]
    assert not referenced.is_equivalent(source)
    # A source cannot be given an input, and a cap that takes one is given it.
    assert isinstance(resolution_error("[x -> fetch -> s]"), UntypedMachineInputError)
    unbound = resolution_error("[() -> compare -> r]")
    assert isinstance(unbound, MainInputUnboundError)
    assert "('series')" in str(unbound)
    assert isinstance(resolution_error("[(benchmark=b) -> compare -> r]"), MainInputUnboundError)

    # What a sequence output feeds: a step that takes the sequence runs once,
    # one that takes a single value runs once per item.
    folded = machine_of("[path -> compare -> (residuals=res)][res -> mean -> m]")
    mapped = machine_of("[path -> compare -> (residuals=res)][res -> score -> s]")
    assert not one_edge_of(folded, "mean").is_loop
    assert one_edge_of(mapped, "score").is_loop
    assert not one_edge_of(mapped, "compare").is_loop
    # Whether a step maps is part of what the machine is: the same text, read
    # where the residuals are one value, is another machine.
    one_value = notation_registry()
    single = compare_cap()
    single.output_named("residuals").is_sequence = False
    one_value.add_caps_to_cache([single])
    unmapped = parse_machine(
        HEADERS + "[path -> compare -> (residuals=res)][res -> score -> s]", one_value
    )
    assert not one_edge_of(unmapped, "score").is_loop
    assert not unmapped.is_equivalent(mapped)
    assert not mapped.is_equivalent(unmapped)


# TEST12740: the media URN of a node comes from the wirings that touch it and
# never from where a member stands or which wiring comes first.
def test_12740_the_urn_of_a_node_is_position_free():
    # Members in either order, wirings in either order: one machine.
    a = "[(path, benchmark=bench, window=20) -> compare -> (r, residuals=res)][res -> score -> s]"
    b = "[res -> score -> s][(window=20, benchmark=bench, path) -> compare -> (residuals=res, r)]"
    assert equivalent(a, b)
    # And one text: the canonical notation names its nodes by what they are
    # for, not by which was written first.
    assert machine_of(a).to_machine_notation() == machine_of(b).to_machine_notation()
    # The two inputs are not interchangeable: a machine that names a DIFFERENT
    # pairing of its nodes to a second step is another machine.
    assert not equivalent(
        "[(path, benchmark=bench) -> compare -> (residuals=r)][(path, benchmark=bench) -> compare -> (note=n)]",
        "[(path, benchmark=bench) -> compare -> (residuals=r)][(bench, benchmark=path) -> compare -> (note=n)]",
    )

    # An input of the machine named into an arg holds what that arg accepts,
    # and the unnamed one beside it holds what the main input accepts.
    machine, names = parse_machine_with_node_names(
        HEADERS + "[(benchmark=bench, path) -> compare -> r]", notation_registry()
    )
    for name in ("bench", "path"):
        assert machine.strands()[0].node_urn(names[0][name]).is_equivalent(media(SERIES)), name

    # Naming the main input is allowed; then an unnamed input beside it has no
    # arg anything decides.
    machine_of("[(series=path, benchmark=bench) -> compare -> r]")
    assert isinstance(
        resolution_error("[(series=path, bench) -> compare -> r]"), UntypedMachineInputError
    )

    # An input of the machine given two types that are not on one chain: it is
    # named into an arg that accepts a series and into one that accepts a
    # comparison.
    conflict = resolution_error("[(series=x) -> compare -> r][(report=x) -> publish -> ()]")
    assert isinstance(conflict, NodeMediaConflictError)
    assert "node 'x'" in str(conflict)
    # A node a step produces has that output's type, and a name does not
    # change it: named into an arg that does not accept it, it is refused there.
    assert isinstance(
        resolution_error("[path -> compare -> r][(series=r) -> compare -> r2]"),
        SourceDoesNotConformToArgError,
    )


# TEST12741: the canonical notation. Every binding and every taken output is
# written under its name, so nothing in it is matched by type; a machine
# written out and read back is the same machine, and the text does not change
# on a second pass. A policy is part of what a machine is.
def test_12741_canonical_notation_round_trips():
    for wirings in [
        "[path -> compare -> result]",
        "[(path, benchmark=bench) -> compare -> result]",
        '[(path, window=20, label="max", tags="b", tags="a") -> compare -> (result, residuals=res, note=n)]',
        '[(reference="fred/UNRATE") -> fetch{retry=3} -> s][s -> compare{retry=1, on_error=absent} -> (residuals=res)][res -> score -> x]',
        "[() -> fetch -> s]",
        "[report -> publish{on_error=absent} -> ()]",
    ]:
        first = machine_of(wirings)
        text = first.to_machine_notation()
        second = Machine.from_string(text, notation_registry())
        assert first.is_equivalent(second), f"{wirings}\n{text}"
        assert second.to_machine_notation() == text, "a fixed point"
        line_based = first.to_machine_notation_formatted(FORMAT_LINE_BASED)
        assert not any(line.startswith("[") for line in line_based.split("\n")), \
            "no statement of the line-based form is bracketed"
        third = Machine.from_string(line_based, notation_registry())
        assert first.is_equivalent(third), line_based
        # The multi-line form is the canonical statements, one to a line.
        multiline = first.to_machine_notation_multiline()
        assert multiline.replace("]\n[", "][") == text
        assert first.is_equivalent(Machine.from_string(multiline, notation_registry()))

    text = machine_of(
        "[(path, benchmark=bench, window=20) -> compare{retry=2} -> (result, residuals=res)]"
    ).to_machine_notation()
    # Named throughout, and the policy on the step.
    for part in ["series=n", "benchmark=n", "window=20", "comparison=n", "residuals=n", "edge_0{retry=2}"]:
        assert part in text
    # A gather keeps the order its members were written in.
    assert 'tags="b", tags="a"' in machine_of(
        '[(path, tags="b", tags="a") -> compare -> r]'
    ).to_machine_notation()

    # The policy is read onto the edge, and two machines that differ in it differ.
    def policy(wirings: str) -> StepPolicy:
        return only_edge(machine_of(wirings)).policy

    assert policy("[p -> compare -> r]").is_default()
    assert policy("[p -> compare{retry=2, on_error=absent} -> r]") == StepPolicy(
        retry=2, on_error=ON_ERROR_ABSENT
    )
    assert not equivalent("[p -> compare{retry=2} -> r]", "[p -> compare -> r]")
    assert not equivalent("[p -> compare{retry=2} -> r]", "[p -> compare{retry=3} -> r]")
    assert not equivalent("[p -> compare{on_error=absent} -> r]", "[p -> compare -> r]")
    assert equivalent("[p -> compare{retry=2} -> r]", "[q -> compare { retry = 2 } -> s]")

    # Two machines of the same nodes, steps and anchors, whose steps take
    # their outputs differently: which step makes the residuals is part of
    # what each is.
    first = "[p -> compare -> r1][(p, window=20) -> compare -> (r2, residuals=x)]"
    second = "[p -> compare -> (r1, residuals=x)][(p, window=20) -> compare -> r2]"
    assert not equivalent(first, second)
    assert not equivalent(second, first)

    # A machine is not the machine it is the first steps of.
    one = "[p -> compare -> (residuals=res)]"
    two = "[p -> compare -> (residuals=res)][res -> score -> s]"
    assert not equivalent(one, two)
    assert not equivalent(two, one)

    # Two steps of one cap that differ only in what feeds an arg have one
    # order in the canonical text, whichever was written first: the one fed
    # by a node, then the one fed by a constant.
    with_benchmark_def = notation_registry()
    with_benchmark_def.add_spec(media_def(BENCHMARK))
    by_node = "[(series=p, benchmark=q) -> compare -> (note=a)]"
    by_constant = "[(series=p, benchmark=[1, 2]) -> compare -> (note=b)]"
    texts = {
        parse_machine(HEADERS + wirings, with_benchmark_def).to_machine_notation()
        for wirings in (by_node + by_constant, by_constant + by_node)
    }
    assert len(texts) == 1
    text = texts.pop()
    assert text.index("benchmark=n") < text.index("benchmark=[1,2]"), text

    # A format nobody writes is refused, not read as one of the two.
    with pytest.raises(ValueError):
        machine_of(one).to_machine_notation_formatted("tabular")


# TEST12742: a machine header names another machine. Read with nothing to
# resolve the reference against, it is refused by name rather than ignored.
def test_12742_a_machine_reference_needs_a_source():
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(
            HEADERS + '[clean machine "lib/clean.machine"][path -> compare -> r]',
            notation_registry(),
        )
    error = exc_info.value
    assert error.is_syntax_error, repr(error.cause)
    assert isinstance(error.cause, MachineReferenceWithoutSourceError)
    assert 'machine header \'clean\' refers to "lib/clean.machine"' in str(error)


# TEST12743: the render payload carries what the graph view needs of the new
# forms: each binding's arg name and its node or its constant, each taken
# output with its name, and the step's policy.
def test_12743_render_payload_carries_names_constants_and_outputs():
    machine = machine_of(
        '[(path, window=20, label="max") -> compare{retry=2, on_error=absent} -> (result, residuals=res)]'
    )
    payload = json.loads(machine.to_render_payload_json(titled_registry()))
    assert len(payload["strands"]) == 1
    strand = payload["strands"][0]
    assert len(strand["edges"]) == 1
    edge = strand["edges"][0]
    assert edge["retry"] == 2
    assert edge["on_error"] == "absent"
    assert edge["alias"] == "edge_0"
    assert edge["title"] == "compare", "the cap's title"
    assert edge["is_loop"] is False
    assert edge["included_as"] == [], "a step the machine wrote itself"
    assert "target_node" not in edge, "one target is not the shape any more"

    by_arg = {binding["arg_name"]: binding for binding in edge["assignment"]}
    assert len(by_arg) == 3
    assert by_arg["window"]["constant"] == 20
    assert by_arg["label"]["constant"] == "max"
    assert "source_node" not in by_arg["window"]
    assert by_arg["series"]["source_node"] == strand["input_anchor_nodes"][0], \
        "the series is the machine's one input"
    assert "constant" not in by_arg["series"]
    assert by_arg["window"]["cap_arg_media_urn"] == canonical(WINDOW)

    assert len(edge["outputs"]) == 2
    node_urn = {node["id"]: node["urn"] for node in strand["nodes"]}
    for output in edge["outputs"]:
        # Each output goes to the node that holds its type.
        assert node_urn[output["node"]] == output["output_media_urn"], output["output_name"]
    assert sorted(o["output_name"] for o in edge["outputs"]) == ["comparison", "residuals"]
    assert sorted(strand["output_anchor_nodes"]) == sorted(o["node"] for o in edge["outputs"])
    # An empty machine draws nothing.
    for node in strand["nodes"]:
        assert node["title"] == node["urn"], "the media definition's title"
    assert Machine.from_resolved_strands([]).to_render_payload_json(registry_of([])) == '{"strands":[]}'


# TEST12833: an output that carries the input holds the input's type, not the
# URN that names it: a router's branches are typed by what was routed, so a
# step that takes that type can be wired to one. Which branch a wiring takes
# is part of what the machine is, although both hold one type.
def test_12833_a_carried_output_holds_the_inputs_type():
    verdict = "media:enc=utf-8;verdict"
    kept = "media:kept;marker"
    dropped = "media:dropped;marker"
    route_urn = f'cap:in="{SERIES}";route;out="{verdict}"'
    registry = notation_registry()
    registry.add_caps_to_cache([
        definition(
            route_urn,
            "route",
            [stdin_arg(SERIES, "series")],
            [
                output_of(verdict, "verdict", "The verdict"),
                output_of(kept, "kept", "What was kept").as_optional(True).carrying_input(),
                output_of(dropped, "dropped", "What was dropped").as_optional(True).carrying_input(),
            ],
        )
    ])
    headers = HEADERS + "[route " + route_urn + "]"

    def parse(wirings: str):
        return parse_machine_with_node_names(headers + wirings, registry)

    machine, names = parse("[s -> route -> (v, kept=k, dropped=d)][k -> compare -> r]")

    def held(name: str) -> str:
        return machine.strands()[0].node_urn(names[0][name]).to_string()

    assert held("k") == canonical(SERIES), "the branch holds what was routed"
    assert held("d") == canonical(SERIES)
    assert held("v") == canonical(verdict), "the main output holds its own type"
    # The edge still records which output each is, by the output's own URN.
    route = one_edge_of(machine, "route")
    assert {o.output_name: o.output_media_urn.to_string() for o in route.outputs} == {
        "verdict": canonical(verdict),
        "kept": canonical(kept),
        "dropped": canonical(dropped),
    }

    # An output that carries nothing holds the URN it declares.
    plain, plain_names = parse("[p -> compare -> (note=n)]")
    assert plain.strands()[0].node_urn(plain_names[0]["n"]).to_string() == canonical(NOTE)

    # The two branches hold one type and are two outputs.
    kept_only, _ = parse("[s -> route -> (kept=x)]")
    kept_again, _ = parse("[t -> route -> (kept=y)]")
    dropped_only, _ = parse("[s -> route -> (dropped=x)]")
    assert kept_only.is_equivalent(kept_again)
    assert not kept_only.is_equivalent(dropped_only)
    assert not dropped_only.is_equivalent(kept_only)


# TEST12834: the correspondence between the nodes of two strands is one to
# one in both directions: a pair made once is confirmed, and a node of either
# strand paired with a second node of the other is refused.
def test_12834_a_node_stands_for_one_node():
    nodes = NodeBijection(3, 3)
    assert nodes.bind(0, 2)
    assert nodes.bind(0, 2), "the same pair again"
    assert not nodes.bind(0, 1), "one node of this strand, two of the other"
    assert not nodes.bind(1, 2), "two nodes of this strand, one of the other"
    # A refused pair leaves nothing behind: both nodes it named are still free.
    assert nodes.bind(1, 1)
    assert nodes.bind(2, 0)
    assert nodes.bind(1, 1), "and a pair made stays made"


# TEST12838: what a machine sorts by URN, it sorts by the URN's parts — the
# prefix, then the tags by key and value; for a cap its input, its output, its
# effect and then its tags — and never by the URN's text. The two orders
# differ wherever one tag key is the beginning of another (`file`,
# `file-path`), and the canonical form is the same in every implementation
# only because all of them use the first.
def test_12838_urns_are_ordered_by_their_parts_not_their_text():
    from capdag.urn.cap_urn import CapUrn

    def stands_before(first: str, second: str) -> bool:
        return media(first).ordering_key() < media(second).ordering_key()

    sample, path = "media:file;sample", "media:file-path"
    assert stands_before(sample, path)
    assert not stands_before(path, sample)
    assert canonical(path) < canonical(sample), "the text orders them the other way"
    # A URN that is the beginning of another stands first; a tag with any
    # value before the same tag with one; values in their own order.
    assert stands_before("media:file", "media:file;sample")
    assert stands_before("media:enc", "media:enc=ascii")
    assert stands_before("media:enc=ascii", "media:enc=utf-8")
    assert media("media:sample;file").ordering_key() == media(sample).ordering_key()

    def cap_before(first: str, second: str) -> bool:
        return CapUrn.from_string(first).ordering_key() < CapUrn.from_string(second).ordering_key()

    # A cap's input decides before anything else it says.
    assert cap_before(f'cap:in="{sample}";zz;out="media:x"', f'cap:in="{path}";aa;out="media:x"')
    # Then its output — and only then: an input that stands first wins over
    # an output that stands last.
    assert cap_before(f'cap:in="media:x";zz;out="{sample}"', f'cap:in="media:x";aa;out="{path}"')
    assert cap_before(f'cap:in="{sample}";op;out="{path}"', f'cap:in="{path}";op;out="{sample}"')
    # Then its effect, in the order: declared, none, patch, unspecified.
    effects = [
        'cap:in="media:x";op;out="media:x"',
        'cap:effect=none;in="media:x";op;out="media:x"',
        'cap:effect=patch;in="media:x";op;out="media:x"',
        'cap:effect=?;in="media:x";op;out="media:x"',
    ]
    for earlier, later in zip(effects, effects[1:]):
        assert cap_before(earlier, later), f"{earlier} before {later}"
        assert not cap_before(later, earlier)
    # Then its other tags — after the effect, whatever they say.
    assert cap_before('cap:in="media:x";aa;out="media:x"', 'cap:in="media:x";zz;out="media:x"')
    assert cap_before(
        'cap:in="media:x";zz;out="media:x"', 'cap:effect=patch;in="media:x";aa;out="media:x"'
    )

    # In a machine: the bindings of a step, the outputs it takes, the inputs
    # of the strand and the steps themselves all stand in that order.
    result, where = "media:file;result", "media:file-path;written"
    pair_urn = f'cap:in="{sample}";pair;out="{result}"'
    first_urn = f'cap:in="{sample}";zz-first;out="media:file;a"'
    second_urn = f'cap:in="{sample}";aa-second;out="{path}"'
    registry = registry_of([
        definition(
            pair_urn,
            "pair",
            [stdin_arg(sample, "sample"), flag_arg(path, "path")],
            [output_of(result, "result"), output_of(where, "where")],
        ),
        definition(first_urn, "first", [stdin_arg(sample, "sample")], [output_of("media:file;a", "made")]),
        definition(second_urn, "second", [stdin_arg(sample, "sample")], [output_of(path, "made")]),
    ])

    machine, names = parse_machine_with_node_names(
        f"[pair {pair_urn}][(path=p, s) -> pair -> (where=w, r)]", registry
    )
    edge = only_edge(machine)
    assert [binding.arg_name for binding in edge.assignment] == ["sample", "path"]
    assert [output.output_name for output in edge.outputs] == ["result", "where"]
    assert machine.strands()[0].input_anchor_ids() == [names[0]["s"], names[0]["p"]]
    assert machine.strands()[0].output_anchor_ids() == [names[0]["r"], names[0]["w"]]
    assert "[(sample=n0, path=n1) -> edge_0 -> (result=n2, where=n3)]" in machine.to_machine_notation()

    headers = f"[first {first_urn}][second {second_urn}]"
    for wirings in ("[x -> first -> a][x -> second -> b]", "[x -> second -> b][x -> first -> a]"):
        steps = parse_machine(headers + wirings, registry).strands()[0].edges()
        assert ["zz-first" in step.cap_urn.to_string() for step in steps] == [True, False], wirings
