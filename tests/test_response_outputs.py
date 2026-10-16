"""Tests for the outputs a request answers on: one stream per output its cap
declares, the main one naming none and every other naming the output it is."""

import queue
import uuid

import cbor2
import pytest
from ops import DryContext, Op, OpMetadata, WetContext

from capdag.bifaci.cartridge_runtime import (
    CartridgeRuntime,
    CliStreamEmitter,
    HandlerError,
    NoPeerInvoker,
    PeerCall,
    PeerInvokerImpl,
    PeerResponseError,
    Request,
    ResponseOutputs,
    StreamError,
    SyncFrameWriter,
    ThreadSafeEmitter,
    UnknownOutputError,
    WET_KEY_REQUEST,
    demux_multi_stream,
    demux_peer_response,
    derive_response_media,
    dispatch_op,
)
from capdag.bifaci.frame import Frame, FrameType, MessageId, compute_checksum
from capdag.bifaci.io import ProtocolError
from capdag.bifaci.manifest import CapManifest, default_group
from capdag.cap.caller import CapArgumentValue
from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.validation import validate_cap_definition
from capdag.standard.caps import identity_cap
from capdag.urn.cap_urn import CapUrn

SERIES = "media:enc=utf-8;series"
FIT = "media:fmt=json;record;regression"
RESIDUALS = "media:fmt=json;list;record;residual"
NOTE = "media:enc=utf-8;note"
REJECTED = "media:enc=utf-8;rejected"



def _full_network():
    """A network handle under `full`, for handlers run directly by tests."""
    from capdag.bifaci.cartridge_runtime import NetworkAccess
    from capdag.bifaci.policy import HostPolicy, LivePolicy, NetworkPolicy

    return NetworkAccess(LivePolicy(HostPolicy(NetworkPolicy.FULL)))

def _regress_cap() -> Cap:
    """A cap with four outputs: the main one, a required sequence, an optional
    one, and an optional one that carries the input's type unchanged."""
    cap = Cap(CapUrn.from_string(f'cap:in="{SERIES}";regress;out="{FIT}"'), "Regress", ["regress"])
    cap.add_arg(CapArg(SERIES, "series", True, [StdinSource(SERIES)]))
    # The main output is not the first declared: it is found by its URN.
    residuals = CapOutput(RESIDUALS, "residuals", "Residuals")
    residuals.is_sequence = True
    cap.add_output(residuals)
    cap.add_output(CapOutput(FIT, "fit", "The fit"))
    cap.add_output(CapOutput(NOTE, "note", "A note").as_optional(True))
    cap.add_output(CapOutput(REJECTED, "rejected", "Rejected input").as_optional(True).carrying_input())
    validate_cap_definition(cap)
    return cap


def _manifest(cap: Cap) -> CapManifest:
    return CapManifest(
        name="Regress",
        version="1.0.0",
        channel="release",
        registry_url=None,
        description="Test",
        cap_groups=[default_group([identity_cap(), cap])],
    )


class _Recorder:
    """A frame writer that keeps every frame it is given."""

    def __init__(self):
        self.frames = []
        self.limits = None

    def write(self, frame):
        self.frames.append(frame)

    def set_limits(self, limits):
        self.limits = limits


def _recorded_outputs(cap_urn: str, manifest):
    """The outputs of `cap_urn` on streams that record every frame they send."""
    recorder = _Recorder()
    writer = SyncFrameWriter(recorder)
    rid = MessageId.new_uuid()
    outputs = ResponseOutputs.for_cap(
        cap_urn, manifest, lambda label: ThreadSafeEmitter(writer, rid, str(uuid.uuid4()), label),
    )
    return outputs, recorder.frames


def _starts(frames):
    """(output named, media label, is_sequence, stream id) of every STREAM_START sent."""
    return [
        (frame.output, frame.media_urn or "", frame.is_sequence, frame.stream_id or "")
        for frame in frames
        if frame.frame_type == FrameType.STREAM_START
    ]


def _empty_input():
    frames: queue.Queue = queue.Queue()
    frames.put(Frame.end(MessageId.new_uuid(), None))
    return demux_multi_stream(frames)


# TEST12719: a request answers on every output its cap declares. Each has a
# stream of its own, carrying the label of what it holds: the main output the
# label the cap's effect derives, another output its own URN, and one that
# carries the input the cap's declared input. The main output's stream names
# no output — it is the cap's answer — and every other stream names the output
# it is. An output is found by its media URN as a tagged URN; one the cap does
# not declare is UnknownOutput.
def test_12719_a_request_answers_on_every_declared_output():
    cap = _regress_cap()
    outputs, frames = _recorded_outputs(cap.urn_string(), _manifest(cap))
    req = Request.with_outputs(_empty_input(), outputs, NoPeerInvoker(), _full_network())

    # The main output is the one whose URN is `out=`, wherever it is declared.
    assert req.emitter() is req.output_for(FIT)
    assert req.emitter() is req.output_for("media:regression;record;fmt=json")
    # Another output, with its tags in another order, is the same stream.
    residuals = req.output_for(RESIDUALS)
    assert residuals is req.output_for("media:residual;record;list;fmt=json")
    assert residuals is not req.emitter()

    for urn, sequence in [(FIT, False), (RESIDUALS, True), (NOTE, False), (REJECTED, False)]:
        stream = req.output_for(urn)
        assert not stream.is_started()
        stream.start(sequence, None)
        assert stream.is_started()
        stream.close()
    sent = _starts(frames)

    def named(urn: str):
        found = [start for start in sent if start[0] == urn]
        assert len(found) == 1, f"no STREAM_START names {urn}: {sent}"
        return found[0]

    assert len(sent) == 4
    # Exactly one stream names no output: the main one.
    unnamed = [start for start in sent if start[0] is None]
    assert len(unnamed) == 1, sent
    assert unnamed[0][1] == FIT, "the main output carries the label the effect derives"
    assert all(start[0] != FIT for start in sent), f"the main output is not named: {sent}"
    assert named(RESIDUALS)[1] == RESIDUALS, "another output carries its own URN"
    assert named(NOTE)[1] == NOTE
    assert named(REJECTED)[1] == SERIES, "an output that carries the input is labelled with it"
    assert len({start[3] for start in sent}) == 4, "each output has a stream of its own"
    # The stream says which output it is, and the accessor agrees.
    assert req.emitter().output_urn() is None
    assert req.output_for(NOTE).output_urn() == NOTE

    # What the cap does not declare is not an output of it — a tag short or a
    # tag more is another URN.
    for unknown in ["media:enc=utf-8", "media:fmt=json;record", "media:enc=utf-8;note;extra", "not a urn"]:
        with pytest.raises(UnknownOutputError) as refusal:
            req.output_for(unknown)
        assert refusal.value.cap_urn == cap.urn_string()
        assert refusal.value.output == unknown
        assert str(refusal.value) == f"Cap '{cap.urn_string()}' declares no output '{unknown}'"

    # A stream is ended once.
    with pytest.raises(HandlerError):
        req.emitter().close()

    # A request made from a bare stream has the one output that stream is.
    bare, _ = _recorded_outputs('cap:in="media:enc=utf-8";count;out="media:integer"', None)
    lone = Request(_empty_input(), bare.main(), NoPeerInvoker(), _full_network())
    assert lone.emitter() is bare.main()
    assert lone.output_for("media:") is bare.main()
    with pytest.raises(UnknownOutputError) as refusal:
        lone.output_for("media:integer")
    assert refusal.value.cap_urn == "", "nothing is known of the cap such a request is for"


class _ResidualsOnlyOp(Op):
    """An op that writes two residual rows and nothing else, or fails."""

    def __init__(self, fail: bool):
        self.fail = fail

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        residuals = req.output_for(RESIDUALS)
        residuals.start(True, None)
        for row in [1, 2]:
            residuals.emit_list_item(row)
        if self.fail:
            raise HandlerError("no fit")

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("ResidualsOnlyOp").build()


class _Silent(Op):
    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        return None

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("Silent").build()


# TEST12720: what the runtime sends for outputs the handler did not write to,
# once it has returned. A required output is sent empty in its declared
# cardinality, so its consumers get a value; an optional one is not sent — it
# did not fire. A handler that failed gets nothing sent on its behalf.
def test_12720_unwritten_outputs_when_the_handler_returns():
    cap = _regress_cap()
    manifest = _manifest(cap)

    outputs, frames = _recorded_outputs(cap.urn_string(), manifest)
    dispatch_op(_ResidualsOnlyOp(fail=False), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert len(sent) == 2, f"the written output and the required unwritten one: {sent}"
    assert [start[0] for start in sent if start[0] is not None] == [RESIDUALS], \
        f"the residuals are named; optional outputs did not fire: {sent}"
    # The other stream is the main output's: it names none.
    fit = next(start for start in sent if start[0] is None)
    assert fit[1] == FIT
    assert fit[2] is False, "the fit is declared a single value"
    # The empty stream is a whole stream: STREAM_END promising no chunks.
    fit_frames = [frame for frame in frames if frame.stream_id == fit[3]]
    assert len(fit_frames) == 2, "STREAM_START and STREAM_END only"
    assert fit_frames[1].frame_type == FrameType.STREAM_END
    assert fit_frames[1].chunk_count == 0
    # Every stream that was opened was closed, and the written one after its rows.
    assert sum(1 for frame in frames if frame.frame_type == FrameType.STREAM_END) == 2
    residual_id = next(start[3] for start in sent if start[0] == RESIDUALS)
    residual_frames = [frame.frame_type for frame in frames if frame.stream_id == residual_id]
    assert residual_frames == [
        FrameType.STREAM_START, FrameType.CHUNK, FrameType.CHUNK, FrameType.STREAM_END,
    ]
    # The request's END is not a stream's to send.
    assert all(frame.frame_type != FrameType.END for frame in frames)

    # A required SEQUENCE output nobody wrote to is an empty sequence.
    outputs, frames = _recorded_outputs(cap.urn_string(), manifest)
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert len(sent) == 2, sent
    residuals = next(start for start in sent if start[0] == RESIDUALS)
    assert residuals[2] is True, "the residuals are declared a sequence"

    # A failed handler: only what it wrote itself, and that left open — the
    # request ends with ERR, not with outputs made up for it.
    outputs, frames = _recorded_outputs(cap.urn_string(), manifest)
    with pytest.raises(HandlerError):
        dispatch_op(_ResidualsOnlyOp(fail=True), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert len(sent) == 1, sent
    assert sent[0][0] == RESIDUALS
    assert all(frame.frame_type != FrameType.STREAM_END for frame in frames)

    # A cap whose `out=` is void has no output: nothing is opened for it.
    outputs, frames = _recorded_outputs('cap:in="media:enc=utf-8";sink;out=media:void', None)
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    assert frames == []

    # The main output's label follows the cap's effect, and is not its name:
    # a cap that passes its input through labels the stream with the input's
    # type and names the output its `out=`.
    passing = 'cap:effect=none;in="media:enc=utf-8;line";out="media:enc=utf-8";pass'
    outputs, frames = _recorded_outputs(passing, None)
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert len(sent) == 1
    assert sent[0][0] is None, "the main output's stream names no output"
    assert sent[0][1] == derive_response_media(passing)
    assert sent[0][1] != "media:enc=utf-8", f"the label is the input's type: {sent[0][1]}"

    # A cap served without a definition answers on the one output its URN states.
    outputs, frames = _recorded_outputs('cap:in="media:enc=utf-8";count;out="media:integer"', None)
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert len(sent) == 1
    assert (sent[0][0], sent[0][1]) == (None, "media:integer")

    # A main output declared a sequence, that nobody wrote to, is an empty
    # sequence.
    listing = Cap(
        CapUrn.from_string('cap:in="media:enc=utf-8";list;out="media:enc=utf-8;line"'), "List", ["list"],
    )
    listing.add_arg(CapArg("media:enc=utf-8", "input", True, [StdinSource("media:enc=utf-8")]))
    lines = CapOutput("media:enc=utf-8;line", "lines", "The lines")
    lines.is_sequence = True
    listing.add_output(lines)
    validate_cap_definition(listing)
    outputs, frames = _recorded_outputs(listing.urn_string(), _manifest(listing))
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    sent = _starts(frames)
    assert [(start[0], start[2]) for start in sent] == [(None, True)], sent

    # A request made from a bare stream has an output nothing is known of:
    # nothing is sent for it unless the handler writes.
    bare, frames = _recorded_outputs('cap:in="media:enc=utf-8";count;out="media:integer"', None)
    dispatch_op(_Silent(), _empty_input(), ResponseOutputs.undeclared(bare.main()), NoPeerInvoker(), _full_network())
    assert frames == []

    # A main output its definition declares optional is not sent when nobody
    # wrote to it.
    optional_main = Cap(
        CapUrn.from_string('cap:in="media:enc=utf-8";maybe;out="media:integer"'), "Maybe", ["maybe"],
    )
    optional_main.add_arg(CapArg("media:enc=utf-8", "input", True, [StdinSource("media:enc=utf-8")]))
    optional_main.add_output(CapOutput("media:integer", "count", "A count").as_optional(True))
    validate_cap_definition(optional_main)
    outputs, frames = _recorded_outputs(optional_main.urn_string(), _manifest(optional_main))
    dispatch_op(_Silent(), _empty_input(), outputs, NoPeerInvoker(), _full_network())
    assert frames == []


# TEST12721: a request stream names no output: the argument of a peer call is
# identified by its media URN alone. (That one which does name an output is
# refused where it is read is TEST12731.)
def test_12721_a_request_stream_names_no_output():
    recorder = _Recorder()
    writer = SyncFrameWriter(recorder)
    call = PeerCall(writer=writer, request_id=MessageId.new_uuid())
    arg = call.arg("media:enc=utf-8;prompt")
    arg.start(False, None)
    sent = _starts(recorder.frames)
    assert len(sent) == 1
    assert sent[0][0] is None, "an argument stream does not carry key 21"
    assert sent[0][1] == "media:enc=utf-8;prompt"

    # And the arguments a whole call is made with: one stream each.
    recorder = _Recorder()
    peer = PeerInvokerImpl(SyncFrameWriter(recorder), {})
    peer.invoke(
        'cap:in="media:enc=utf-8;prompt";ask;out="media:enc=utf-8"',
        [
            CapArgumentValue("media:enc=utf-8;prompt", b"why"),
            CapArgumentValue("media:enc=utf-8;model-spec", b"small"),
        ],
    )
    sent = _starts(recorder.frames)
    assert [(start[0], start[1]) for start in sent] == [
        (None, "media:enc=utf-8;prompt"),
        (None, "media:enc=utf-8;model-spec"),
    ]


class _FitAndNotesOp(Op):
    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        req.take_input().collect_streams()
        req.emitter().write(b"the fit")
        note = req.output_for(NOTE)
        note.write(b"a note")
        note.emit_cbor(b"another note")

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("FitAndNotesOp").build()


# TEST12722: a command line has one standard output, and it carries the cap's
# main output. A stream of another output is recognised by the output it is —
# not by what it carries, which may be the same type — and its data is not
# printed.
def test_12722_standard_output_carries_the_main_output(capsysbinary):
    cap = _regress_cap()
    manifest = _manifest(cap)
    outputs = ResponseOutputs.for_cap(cap.urn_string(), manifest, lambda _label: CliStreamEmitter())
    main = outputs.main()
    assert main.output_urn() is None, "the main output is printed"
    for media_urn in [RESIDUALS, NOTE, REJECTED]:
        other = outputs.stream_for(media_urn)
        assert other.output_urn() == media_urn
        # What a handler writes to it is accepted without being read: a value
        # the printed stream refuses is taken here.
        other.emit_cbor(42)
        other.emit_list_item({"no": "value field"})
        other.write(b"raw")
    # The same value on the printed stream is read, and refused.
    with pytest.raises(Exception):
        main.emit_cbor(42)
    # Nothing is owed on a command line for an output nobody wrote to.
    outputs.finish()
    assert capsysbinary.readouterr().out == b""

    # Through the command-line dispatch itself: what the handler writes to the
    # stream it is given reaches standard output, and what it writes to
    # another output does not.
    runtime = CartridgeRuntime.with_manifest(manifest)
    runtime._dispatch_cli_payload(cap, _FitAndNotesOp, b"")
    assert capsysbinary.readouterr().out == b"the fit"


def _value_chunk(rid: MessageId, stream: str, index: int, value) -> Frame:
    payload = cbor2.dumps(value)
    return Frame.chunk(rid, stream, 0, payload, index, compute_checksum(payload))


def _feed(frames, **credit):
    raw: queue.Queue = queue.Queue()
    for frame in frames:
        raw.put(frame)
    raw.put(None)
    return demux_peer_response(raw, **credit)


def _drain(response):
    items = []
    while True:
        item = response.recv()
        if item is None:
            return items
        items.append(item)


REST = "media:enc=utf-8;split-rest"


def _two_output_response(rid: MessageId):
    return [
        # The other output starts first, ends first, and carries the same type
        # as the main one.
        Frame.stream_start(rid, "rest", "media:enc=utf-8", False).for_output(REST),
        _value_chunk(rid, "rest", 0, b"R1"),
        Frame.stream_start(rid, "head", "media:enc=utf-8", False),
        _value_chunk(rid, "head", 0, b"H1"),
        _value_chunk(rid, "rest", 1, b"R2"),
        Frame.stream_end(rid, "rest", 2),
        _value_chunk(rid, "head", 1, b"H2"),
        Frame.stream_end(rid, "head", 2),
        Frame.end_ok(rid, None),
    ]


# TEST12730: a peer call's response has one stream per output the callee
# answers on. The stream that names no output is the callee's main output: its
# items are the response's data. A stream that names an output yields items
# tagged with it, and they are not part of the data a caller collects. The
# response ends at the request's END, not at the first stream's end — it used
# to stop there, and lose whatever came after — and each stream is credited by
# name, since a grant that names no stream reaches a callee with several only
# by guessing.
def test_12730_a_peer_response_has_a_stream_per_output():
    rid = MessageId.new_uuid()

    # Item by item: which output each belongs to, in arrival order.
    seen = [
        (item.output if item.is_output else "main", item.data_value)
        for item in _drain(_feed(_two_output_response(rid)))
    ]
    assert seen == [(REST, b"R1"), ("main", b"H1"), (REST, b"R2"), ("main", b"H2")], \
        "everything up to END, each item under its own output"
    kinds = [(item.is_data, item.is_output) for item in _drain(_feed(_two_output_response(rid)))]
    assert kinds == [(False, True), (True, False), (False, True), (True, False)]

    # A caller that collects the cap's answer gets the main output only.
    assert _feed(_two_output_response(rid)).collect_bytes() == b"H1H2"
    one_answer = [
        Frame.stream_start(rid, "rest", "media:enc=utf-8", False).for_output(REST),
        _value_chunk(rid, "rest", 0, b"R1"),
        Frame.stream_start(rid, "head", "media:enc=utf-8", False),
        _value_chunk(rid, "head", 0, b"H1"),
        _value_chunk(rid, "rest", 1, b"R2"),
        Frame.end_ok(rid, None),
    ]
    assert _feed(one_answer).collect_value() == b"H1"

    # Each stream is credited by name as its items are consumed.
    recorder_frames = []

    class _Grants:
        def write(self, frame):
            recorder_frames.append(frame)

        def set_limits(self, limits):
            pass

    credited = _feed(
        _two_output_response(rid), writer=SyncFrameWriter(_Grants()), request_id=rid, initial_credit=2,
    )
    _drain(credited)
    grants = [
        (frame.stream_id, frame.credit) for frame in recorder_frames if frame.frame_type == FrameType.CREDIT
    ]
    assert grants and all(stream is not None for stream, _ in grants), f"every grant names its stream: {grants}"

    def granted(stream: str) -> int:
        return sum(n for name, n in grants if name == stream)

    assert granted("rest") >= 1 and granted("head") >= 1, grants

    # A chunk for a stream that was never started is not data of any output,
    # and the response ends there: what follows it is not read.
    stray = _drain(_feed([
        _value_chunk(rid, "ghost", 0, b"?"),
        Frame.stream_start(rid, "head", "media:enc=utf-8", False),
        _value_chunk(rid, "head", 0, b"H1"),
        Frame.end_ok(rid, None),
    ]))
    assert len(stray) == 1 and isinstance(stray[0].data_error, ProtocolError), stray
    assert "ghost" in str(stray[0].data_error)
    # So does a second STREAM_START for a stream: which of the two the chunks
    # after it belong to is not something to guess.
    twice = _drain(_feed([
        Frame.stream_start(rid, "head", "media:enc=utf-8", False),
        _value_chunk(rid, "head", 0, b"H1"),
        Frame.stream_start(rid, "head", "media:enc=utf-8", False).for_output(REST),
        _value_chunk(rid, "head", 1, b"H2"),
        Frame.end_ok(rid, None),
    ]))
    assert [item.data_error is None for item in twice] == [True, False], twice
    assert isinstance(twice[1].data_error, ProtocolError)
    assert "a second STREAM_START for stream 'head'" in str(twice[1].data_error)

    # What goes wrong on another output's stream is an error of the response:
    # it is tagged with its output, and a collector does not pass over it.
    damaged = _value_chunk(rid, "rest", 0, b"R1")
    damaged.checksum = (damaged.checksum + 1) & 0xFFFFFFFF
    broken = [
        Frame.stream_start(rid, "rest", "media:enc=utf-8", False).for_output(REST),
        Frame.stream_start(rid, "head", "media:enc=utf-8", False),
        _value_chunk(rid, "head", 0, b"H1"),
        damaged,
        Frame.stream_end(rid, "rest", 1),
        Frame.stream_end(rid, "head", 1),
        Frame.end_ok(rid, None),
    ]
    tagged = [item for item in _drain(_feed(broken)) if item.data_error is not None]
    assert len(tagged) == 1 and tagged[0].output == REST and tagged[0].is_output
    for collect in [
        lambda response: response.collect_bytes(),
        lambda response: response.collect_value(),
        lambda response: response.collect_bytes_forwarding(CliStreamEmitter(), 0.0, 1.0),
    ]:
        with pytest.raises(PeerResponseError, match="Checksum mismatch"):
            collect(_feed(broken))

    # A sequence stream of another output that the request's END cuts inside
    # an item ends with that error, under its output.
    rows = cbor2.dumps([1, 2, 3])
    cut = [
        Frame.stream_start(rid, "rest", "media:enc=utf-8", True).for_output(REST),
        Frame.chunk(rid, "rest", 0, rows[:2], 0, compute_checksum(rows[:2])),
        Frame.end_ok(rid, None),
    ]
    unfinished = _drain(_feed(cut))
    assert len(unfinished) == 1 and unfinished[0].output == REST
    assert "ended mid-item" in str(unfinished[0].data_error)


# TEST12731: a request stream names no output: an argument is identified by
# its media URN alone. A request stream that does name one is refused where it
# is read — the request ends with a protocol error, and nothing of the stream
# is read as an argument.
def test_12731_a_request_stream_that_names_an_output_is_refused():
    rid = MessageId.new_uuid()
    payload = cbor2.dumps(b"x")

    def feed(named):
        frames: queue.Queue = queue.Queue()
        start = Frame.stream_start(rid, "arg0", "media:enc=utf-8")
        if named is not None:
            start.for_output(named)
        frames.put(start)
        frames.put(Frame.chunk(rid, "arg0", 0, payload, 0, compute_checksum(payload)))
        frames.put(Frame.stream_end(rid, "arg0", 1))
        frames.put(Frame.end(rid, None))
        return demux_multi_stream(frames)

    # An argument, as every request stream is.
    plain = feed(None)
    stream = plain.recv()
    assert not isinstance(stream, Exception), "an argument stream"
    assert not isinstance(stream.recv(), Exception)

    # The same stream naming an output: a response stream where an argument
    # belongs.
    named = feed("media:enc=utf-8;kept")
    refusal = named.recv()
    assert isinstance(refusal, StreamError), refusal
    assert "names an output" in str(refusal) and "media:enc=utf-8;kept" in str(refusal), str(refusal)
    assert named.recv() is None, "nothing of the request is read as an argument"
