"""The runtime's objects, replayed against the proved model's scripts.

The decisions these objects make are the model's generated code
(``formal/CapDAG/Bifaci``), so this does not test the rules — those are
proved. It tests everything around them: that a ``CreditGate``, a
``CreditWindow``, a ``ReorderBuffer``, the writer's gate, a ``RequestTable``,
the runtime's pools and the switch's admission carry the decisions out as the
model means them — their counters, their containers, the order they do things
in.

``../formal/conformance-bifaci.json`` is written by the model (``lake exe
conformance_bifaci``): for each machine, short scripts of operations and, for
each operation, what the model says happened. The same scripts run in every
mirror.
"""

import functools
import io
import json
import pathlib
import threading
import time

import pytest

from capdag import _formal
from capdag.bifaci.cartridge_runtime import (
    GatedWrite,
    OutputStream,
    PoolHandle,
    RuntimePools,
    SyncFrameWriter,
)
from capdag.bifaci.credit import (
    CreditClosed,
    CreditGate,
    CreditRouter,
    CreditWindow,
    negotiate_initial_credit,
)
from capdag.bifaci.frame import (
    DEFAULT_MAX_CHUNK,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_REORDER_BUFFER,
    AttributionClass,
    CreditDirection,
    Frame,
    FrameType,
    MessageId,
    ReorderBuffer,
    compute_checksum,
)
from capdag.bifaci.io import FrameReader, FrameWriter, HandshakeError, ProtocolError, handshake_accept
from capdag.bifaci.pools import (
    POOL_ALL,
    PoolDeclarations,
    PoolState,
    advertised_capacity,
    effective_capacity,
)
from capdag.bifaci.request_state import (
    AdmissionController,
    AdmissionError,
    AdmissionKey,
    Disposition,
    FrameDirection,
    PoolKey,
    RequestState,
    RequestTable,
    RoutingEntry,
    TerminalKind,
)
from capdag.urn.cap_urn import CapUrn


@functools.lru_cache(maxsize=None)
def _table():
    path = pathlib.Path(__file__).resolve().parents[2] / "formal" / "conformance-bifaci.json"
    return json.loads(path.read_text())


def _rows(section):
    rows = _table()[section]
    assert rows, f"the model's table has no {section} scripts"
    return rows


def _conclude(what, total, wrong):
    assert not wrong, (
        f"{len(wrong)} of {total} {what} scripts disagree with the model; first: {wrong[0]}"
    )


class _Wire:
    """A frame writer that keeps what was written."""

    def __init__(self):
        self.frames = []

    def write(self, frame):
        self.frames.append(frame)

    def set_limits(self, limits):
        pass


# TEST12375: every frame type is the type the model means by its number, part
# of a flow exactly when the model says, and an end exactly when the model
# says. The runtime's own FrameType is mapped onto the model's by hand; a type
# mapped to the wrong one would be numbered, ordered and gated as another.
def test_12375_frame_types_are_the_models():
    rows = _rows("frame_types")
    assert len(rows) == len(FrameType), "the model and the runtime name the same types"
    wrong = []
    for row in rows:
        frame_type = FrameType.from_u8(row["code"])
        if frame_type is None:
            wrong.append(f"wire number {row['code']} names no frame type here")
            continue
        if _formal.code(frame_type.model()) != row["code"]:
            wrong.append(f"{frame_type!r} is mapped to the model's type {_formal.code(frame_type.model())}")
        if frame_type.is_flow() != row["flow"]:
            wrong.append(f"{frame_type!r}: flow is {frame_type.is_flow()}")
        if frame_type.is_terminal() != row["terminal"]:
            wrong.append(f"{frame_type!r}: terminal is {frame_type.is_terminal()}")
        kind = TerminalKind.of_frame(frame_type)
        ends = kind.as_str() if kind is not None else None
        if ends != row["ends"]:
            wrong.append(f"{frame_type!r}: ends its request as {ends}, model {row['ends']}")
        if Frame(frame_type, MessageId(1)).is_flow_frame() != frame_type.is_flow():
            wrong.append(f"{frame_type!r}: a frame and its type disagree on being of a flow")
    _conclude("frame type", len(rows), wrong)


# TEST12376: a credit gate answers every acquire, grant and close as the model
# does, and holds what the model says it holds afterwards.
def test_12376_credit_gate_follows_the_model():
    scripts = _rows("gate")
    wrong = []
    for index, script in enumerate(scripts):
        gate = CreditGate(script["window"])
        for at, (op, step) in enumerate(zip(script["ops"], script["steps"])):
            answer = None
            if op["op"] == "acquire":
                try:
                    answer = "acquired" if gate.try_acquire(op["n"]) else "wait"
                except CreditClosed as closed:
                    answer = f"closed:{closed.reason}"
            elif op["op"] == "grant":
                gate.grant(op["n"])
            elif op["op"] == "close":
                gate.close(op["reason"])
            else:
                raise AssertionError(f"unknown gate operation {op['op']!r}")
            if (
                answer != step["answer"]
                or gate.available() != step["available"]
                or gate.is_closed() != (step["closed"] is not None)
            ):
                wrong.append(
                    f"step {at} of script {index}: answered {answer}, available "
                    f"{gate.available()}, closed {gate.is_closed()}"
                )
                break
    _conclude("credit gate", len(scripts), wrong)


# TEST12377: a credit window accepts, refuses and grants as the model does: an
# arriving chunk is a violation exactly when nothing is left of the window, a
# grant is due exactly when a batch has built up, a flush grants what is
# pending, and a continued chunk is granted back at once.
def test_12377_credit_window_follows_the_model():
    scripts = _rows("window")
    wrong = []
    for index, script in enumerate(scripts):
        window = CreditWindow(script["window"])
        for at, (op, step) in enumerate(zip(script["ops"], script["steps"])):
            violation, grant = False, 0
            if op == "arrive":
                violation = not window.arrive()
            elif op == "continuation":
                if window.arrive():
                    grant = window.continued()
                else:
                    violation = True
            elif op == "consume":
                grant = window.consumed()
            elif op == "flush":
                grant = window.flush()
            else:
                raise AssertionError(f"unknown window operation {op!r}")
            if (
                violation != step["violation"]
                or grant != step["grant"]
                or window.remaining() != step["remaining"]
                or window.pending() != step["pending"]
            ):
                wrong.append(
                    f"step {at} of script {index}: violation {violation}, grant {grant}, "
                    f"remaining {window.remaining()}, pending {window.pending()}"
                )
                break
    _conclude("credit window", len(scripts), wrong)


# TEST12378: the window two ends start with is the smaller proposal, and a
# proposal of zero is refused — it would deadlock every stream at its first
# chunk.
def test_12378_a_zero_window_is_refused():
    rows = _rows("negotiate")
    wrong = [
        f"{row}: negotiated {negotiate_initial_credit(row['ours'], row['theirs'])}"
        for row in rows
        if negotiate_initial_credit(row["ours"], row["theirs"]) != row["window"]
    ]
    _conclude("negotiation", len(rows), wrong)


# TEST12379: a grant credits the stream it names, or — naming none — the
# request's only sending stream; a grant that names a stream the request does
# not have, or names none among several, credits nothing.
def test_12379_a_grant_reaches_the_stream_it_is_for():
    rows = _rows("grant_target")
    wrong = []
    for row in rows:
        rid = MessageId(7)
        router = CreditRouter()
        gates = []
        for stream in row["streams"]:
            gate = CreditGate(0)
            router.register(rid, stream, gate)
            gates.append(gate)
        # A gate of ANOTHER request with the same stream id must never be credited.
        stranger = CreditGate(0)
        router.register(MessageId(8), row["named"], stranger)

        matched = router.grant(Frame.credit(rid, row["named"], 3, CreditDirection.RESPONSE))
        credited = [stream for stream, gate in zip(row["streams"], gates) if gate.available() == 3]
        expected = [row["target"]] if row["matched"] else []
        if matched != row["matched"] or credited != expected or stranger.available() != 0:
            wrong.append(f"{row}: matched {matched}, credited {credited}")
    _conclude("grant routing", len(rows), wrong)


# TEST12380: frames arriving out of order are handed on in the order they were
# written — each arrival delivers exactly what the model says, holds what it
# says, and is refused when it says: a number already handed on, one already
# held, or one more than the buffer may hold.
def test_12380_reorder_buffer_follows_the_model():
    refusals = {
        "stale": "stale/duplicate seq: expected",
        "duplicate": "already buffered",
        "overflow": "reorder buffer overflow",
    }
    scripts = _rows("reorder")
    wrong = []
    for index, script in enumerate(scripts):
        buffer = ReorderBuffer(script["limit"])
        for at, (seq, step) in enumerate(zip(script["arrivals"], script["steps"])):
            frame = Frame(FrameType.LOG, MessageId(1))
            frame.seq = seq
            try:
                outcome = [delivered.seq for delivered in buffer.accept(frame)]
            except ProtocolError as refused:
                outcome = str(refused)
            if "deliver" in step:
                agrees = outcome == step["deliver"]
            elif "hold" in step:
                agrees = outcome == []
            else:
                agrees = isinstance(outcome, str) and refusals[step["error"]] in outcome
            if not agrees:
                wrong.append(f"step {at} of script {index} ({script['arrivals']}): {outcome}")
                break
    _conclude("reorder", len(scripts), wrong)


def _frame_of(frame_type, rid):
    """A frame of one type for one request, as a writer is handed it."""
    if frame_type == FrameType.CHUNK:
        payload = bytes([1])
        return Frame.chunk(rid, "s", 0, payload, 0, compute_checksum(payload))
    if frame_type == FrameType.LOG:
        return Frame.progress(rid, 0.5, "working")
    if frame_type == FrameType.END:
        return Frame.end_ok_with(rid, None, 1.0, None)
    if frame_type == FrameType.ERR:
        return Frame.err(rid, "FAILED", AttributionClass.INTERNAL, "it failed")
    if frame_type == FrameType.CREDIT:
        return Frame.credit(rid, None, 1, CreditDirection.RESPONSE)
    raise AssertionError(f"the writer scripts hand over no {frame_type!r} frame")


# TEST12381: the writer writes exactly the frames the model says: everything
# until the flow's END or ERR, then nothing of the flow — while credit, which
# is not of the flow, still passes. What reaches the wire has the flow's
# numbers 0, 1, 2, … without a gap.
def test_12381_the_writer_gate_follows_the_model():
    scripts = _rows("writer")
    wrong = []
    for index, script in enumerate(scripts):
        rid = MessageId(1)
        wire = _Wire()
        writer = SyncFrameWriter(wire)
        written = [
            writer.write(_frame_of(FrameType(code), rid)) == GatedWrite.WRITTEN
            for code in script["frames"]
        ]
        if written != script["written"]:
            wrong.append(f"script {index} ({script['frames']}): written {written}")
            continue
        flow_seqs = [frame.seq for frame in wire.frames if frame.is_flow_frame()]
        if flow_seqs != list(range(len(flow_seqs))):
            wrong.append(f"script {index} ({script['frames']}): flow frames numbered {flow_seqs}")
    _conclude("writer", len(scripts), wrong)


_TABLE_IDS = {"x1": 1, "x2": 2, "r1": 101, "r2": 102, "r3": 103}


def _request_state(initial_credit=32):
    return RequestState(
        RoutingEntry(source_master_idx=None, destination_master_idx=0),
        None,
        None,
        False,
        initial_credit,
    )


# TEST12382: a request table registers a request once, ends it once, keeps no
# state for it afterwards, and tells a frame that crossed a request's end from
# a frame for a request nobody knew — step for step as the model's table does,
# including when the ring of ended requests is full and the oldest is
# forgotten.
def test_12382_request_table_follows_the_model():
    from capdag.bifaci.request_state import RequestStateError

    scripts = _rows("table")
    wrong = []
    for index, script in enumerate(scripts):
        table = RequestTable(recent_capacity=script["keep"])
        agreed = True
        for at, (op, step) in enumerate(zip(script["ops"], script["steps"])):
            key = (MessageId(_TABLE_IDS[op["xid"]]), MessageId(_TABLE_IDS[op["rid"]]))
            if op["op"] == "register":
                try:
                    table.register(key, _request_state())
                    ok = True
                except RequestStateError:
                    ok = False
            elif op["op"] == "terminate":
                ok = table.terminate(key, TerminalKind.END) is not None
                if ok and (table.contains(key) or table.xid_for_rid(key[1]) is not None):
                    wrong.append(f"step {at} of script {index}: state remains after the end")
                    agreed = False
                    break
            else:
                raise AssertionError(f"unknown table operation {op['op']!r}")
            frames = [
                table.disposition(MessageId(_TABLE_IDS[rid])).value for rid in ("r1", "r2", "r3")
            ]
            if ok != step["ok"] or frames != step["frames"]:
                wrong.append(f"step {at} of script {index}: ok {ok}, frames {frames}")
                agreed = False
                break
        if agreed and (
            len(table) != script["live"] or table.total_registered() != script["registered"]
        ):
            wrong.append(
                f"script {index}: {len(table)} live, {table.total_registered()} registered"
            )
    _conclude("request table", len(scripts), wrong)

    # The ledger a request keeps of each stream's window moves as the model's
    # does: one less for a chunk, more by a grant, and by nothing else.
    for row in _rows("ledger"):
        rid = MessageId(9)
        frame_type = FrameType(row["frame"])
        if frame_type == FrameType.CREDIT:
            frame = Frame.credit(rid, "s", row["granted"], CreditDirection.RESPONSE)
        else:
            frame = Frame(frame_type, rid)
            frame.stream_id = "s"
        table = RequestTable()
        key = (MessageId(1), rid)
        table.register(key, _request_state(row["remaining"]))
        table.record_frame(key, FrameDirection.INBOUND, frame)
        after = table.get(key).streams["s"].credit_outstanding
        assert after == row["after"], f"the ledger after {row}"


# TEST12383: a pool's limit is the smaller of the operator's number and what
# the cartridge reports, with zero meaning no limit in both and in the result;
# and a cartridge that is not running is given one request, through `all`.
def test_12383_pool_limits_are_the_models():
    rows = _rows("effective")
    wrong = []
    for row in rows:
        state = PoolState(
            declared=row["configured"],
            configured=row["configured"],
            available=row["available"],
            active=0,
            queued=0,
            caps=[],
        )
        effective = effective_capacity(row["configured"], row["available"])
        if (
            effective != row["effective"]
            or state.effective() != effective
            or advertised_capacity(True, POOL_ALL, state) != effective
            or advertised_capacity(False, POOL_ALL, state) != row["cold_all"]
            or advertised_capacity(False, "gpu", state) != row["cold_other"]
        ):
            wrong.append(f"{row}: effective {effective}")
    _conclude("pool limit", len(rows), wrong)


def _canon(name):
    """The scripts name caps as they are written; the runtime names their
    pools by the canonical form."""
    return CapUrn.from_string(name).to_string() if name.startswith("cap:") else name


# TEST12384: the runtime's pools admit, queue and release exactly as the
# model's scripts say — who holds a slot in which pool, who is in line, who
# goes next, and how many waiters each pool is holding back — including where
# a pool's limit rose and a request arrives while somebody in line could go:
# it waits behind them rather than taking the slot.
def test_12384_runtime_pools_follow_the_model():
    scripts = _rows("pools")
    wrong = []
    for index, script in enumerate(scripts):
        pools = RuntimePools(
            [_canon(cap) for cap in script["caps"]],
            PoolDeclarations(
                pools={
                    pool["name"]: [_canon(cap) for cap in pool["caps"]]
                    for pool in script["shared"]
                },
                capacities={_canon(c["pool"]): c["capacity"] for c in script["capacities"]},
            ),
        )
        names = [_canon(name) for name in script["pools"]]
        for at, (op, step) in enumerate(zip(script["ops"], script["steps"])):
            if op["op"] == "arrive":
                request = object()
                position = pools.arrive(_canon(op["cap"]), request)
                if position is None:
                    agreed = step["admitted"] is True
                else:
                    ticket = next(t for t, (_, r) in pools.waiting.items() if r is request)
                    agreed = (
                        step["admitted"] is False
                        and ticket == step["ticket"]
                        and position == step["position"]
                    )
            elif op["op"] == "release":
                pools.release(_canon(op["cap"]))
                agreed = True
            elif op["op"] == "admit_next":
                before = dict(pools.waiting)
                went = pools.admit_next()
                if went is None:
                    agreed = step["ticket"] is None
                else:
                    agreed = step["ticket"] is not None and before.get(step["ticket"]) == went
            elif op["op"] == "capacity":
                pools.apply_desired({_canon(op["pool"]): op["capacity"]})
                agreed = True
            elif op["op"] == "leave_oldest":
                # This mirror's runtime has no way for a queued request to
                # leave the line (a CANCEL does not reach a queued request);
                # the rest of such a script cannot be replayed here.
                break
            else:
                raise AssertionError(f"unknown pools operation {op['op']!r}")
            snapshot = pools.snapshot()
            active = [snapshot[name].active for name in names]
            held_back = [snapshot[name].queued for name in names]
            waiting = sorted(pools.waiting)
            if (
                not agreed
                or active != step["active"]
                or held_back != step["held_back"]
                or waiting != step["waiting"]
            ):
                wrong.append(
                    f"step {at} of script {index}: agreed {agreed}, active {active}, "
                    f"held back {held_back}, waiting {waiting}"
                )
                break
    _conclude("pools", len(scripts), wrong)


def _emitted(frame):
    """A frame as the model's recognizer of a flow's order sees it; ``None``
    for a frame that is not of the flow."""
    if not frame.is_flow_frame():
        return None
    if frame.frame_type == FrameType.STREAM_START:
        return _formal.EmittedStreamStart(frame.stream_id)
    if frame.frame_type == FrameType.CHUNK:
        return _formal.EmittedChunk(frame.stream_id, frame.chunk_index)
    if frame.frame_type == FrameType.STREAM_END:
        return _formal.EmittedStreamEnd(frame.stream_id, frame.chunk_count)
    if frame.frame_type == FrameType.END:
        return _formal.EmittedFin()
    if frame.frame_type == FrameType.ERR:
        return _formal.EmittedErr()
    return _formal.EmittedOther()


# TEST12385: what an output stream and the writer put on the wire for one
# request is a flow in order, by the model's own recognizer: the stream is
# started once, its chunks are numbered 0, 1, 2, …, its end says how many
# there were, and nothing of the flow follows END — although a late progress
# frame and a late chunk were handed to the writer after it.
def test_12385_what_reaches_the_wire_is_a_flow_in_order():
    wire = _Wire()
    writer = SyncFrameWriter(wire)
    rid = MessageId.new_uuid()
    stream = OutputStream(
        writer=writer, request_id=rid, stream_id="s1", media_urn="media:enc=utf-8", max_chunk=4
    )
    stream.start(False, None)
    stream.write(bytes([7] * 10))
    writer.write(Frame.progress(rid, 0.5, "halfway"))
    stream.close()

    # The handler's END, then what a detached sender does: frames that lost
    # the race with it.
    late = bytes([9])
    handed_over = [
        Frame.end_ok_with(rid, None, 1.0, None),
        Frame.progress(rid, 1.0, "late keepalive"),
        Frame.chunk(rid, "s1", 0, late, 3, compute_checksum(late)),
    ]
    for frame in handed_over:
        writer.write(frame)

    flow = [emitted for emitted in map(_emitted, wire.frames) if emitted is not None]
    assert _formal.check(flow) is None, f"the wire carries {flow}"
    chunks = [frame for frame in wire.frames if frame.frame_type == FrameType.CHUNK]
    assert len(chunks) == 3, "ten bytes at four a chunk"
    stream_end = next(f for f in wire.frames if f.frame_type == FrameType.STREAM_END)
    assert stream_end.chunk_count == 3, "the stream's end says how many chunks it carried"
    assert wire.frames[-1].frame_type == FrameType.END

    # The recognizer is what found nothing wrong, not a rubber stamp: the flow
    # with the late frames the gate held back is refused for them.
    ungated = flow + [_emitted(frame) for frame in handed_over[1:]]
    assert isinstance(_formal.check(ungated), _formal.ViolationAfterEnd)


# TEST12386: a handler changing what one of its pools can serve starts whoever
# in line can now go. Without that a request in line waited for the host's
# next frame.
def test_12386_a_self_report_wakes_the_runtime():
    class _Runtime:
        def __init__(self):
            self._pools_lock = threading.Lock()
            self._pools = RuntimePools(
                ["cap:pool-a"],
                PoolDeclarations(pools={"gpu": ["cap:pool-a"]}, capacities={"gpu": 2}),
            )
            self.woken = 0
            self._pools_changed = self._wake

        def _wake(self):
            self.woken += 1

    runtime = _Runtime()
    PoolHandle(runtime, "gpu").set(1)
    assert runtime.woken == 1, "a self-report must wake the runtime"
    assert runtime._pools.snapshot()["gpu"].available == 1

    # A refused self-report changed nothing, and wakes nobody.
    with pytest.raises(ValueError, match="cap:ghost"):
        PoolHandle(runtime, "cap:ghost").set(1)
    assert runtime.woken == 1


def _admission_key():
    return AdmissionKey(
        master_idx=0,
        registry_url=None,
        channel="release",
        id="cartridge",
        version="1.0.0",
        sha256="sha",
    )


def _eventually(condition):
    """Wait for a condition that threads are about to make true."""
    deadline = time.monotonic() + 5.0
    while not condition():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.0002)
    return True


class _Arrival:
    """One arriving request: a thread waiting for its permit."""

    def __init__(self, controller, cap, chain):
        self.cap = cap
        self.cancel = threading.Event()
        self.permit = None
        self.done = threading.Event()
        self.held = False
        self.settled = False

        def wait():
            try:
                self.permit = controller.acquire(chain, self.cancel)
            except AdmissionError:
                self.permit = None
            self.done.set()

        self.thread = threading.Thread(target=wait, daemon=True)
        self.thread.start()


# TEST12387: the switch admits as the model's scripts say. Every arrival is a
# waiting thread; after each thing that happens — an arrival, a release, a
# waiter giving up, a limit changing — exactly the requests the model admits
# have been admitted, in the model's order across caps, and each pool holds
# what the model says it holds.
def test_12387_switch_admission_follows_the_model():
    scripts = _rows("admission")
    wrong = []
    for index, script in enumerate(scripts):
        controller = AdmissionController()
        install = _admission_key()
        limits = {c["pool"]: c["capacity"] for c in script["capacities"]}
        names = script["pools"]
        controller.configure_pools(install, {name: limits.get(name, 0) for name in names})

        def chain_of(cap):
            shared = [pool["name"] for pool in script["shared"] if cap in pool["caps"]]
            return [PoolKey(install=install, pool=name) for name in [cap, *shared, POOL_ALL]]

        def state():
            active = controller.active(install)
            return [active[name] for name in names], controller.waiting(install)

        arrivals = []
        for at, (op, step) in enumerate(zip(script["ops"], script["steps"])):
            if op["op"] == "arrive":
                arrivals.append(_Arrival(controller, op["cap"], chain_of(op["cap"])))
            elif op["op"] == "release":
                holder = next(a for a in arrivals if a.held and a.cap == op["cap"])
                holder.permit.release()
                holder.held = False
            elif op["op"] == "leave_oldest":
                oldest = next(a for a in arrivals if not a.settled)
                oldest.cancel.set()
                assert oldest.done.wait(5.0), "a cancelled waiter gives up"
                oldest.settled = True
            elif op["op"] == "capacity":
                controller.configure_pools(install, {op["pool"]: op["capacity"]})
            else:
                raise AssertionError(f"unknown admission operation {op['op']!r}")

            if not _eventually(lambda: state() == (step["active"], step["waiting"])):
                wrong.append(f"step {at} of script {index}: active and waiting {state()}")
                break
            # Exactly the tickets the model admits hold a permit now.
            agreed = True
            for ticket in step["admitted"]:
                waiter = arrivals[ticket]
                agreed = agreed and waiter.done.wait(5.0) and waiter.permit is not None
                waiter.held, waiter.settled = True, True
            early = [t for t, a in enumerate(arrivals) if not a.settled and a.done.is_set()]
            if not agreed or early:
                wrong.append(
                    f"step {at} of script {index}: the model admits {step['admitted']}; "
                    f"admitted besides: {early}"
                )
                break
        for waiter in arrivals:
            waiter.cancel.set()
        if wrong:
            # Every disagreement is waited out before it is one; the first says enough.
            break
    _conclude("admission", len(scripts), wrong)


# TEST12388: a request that joins the line late into an outage is given what
# is left of the outage's window, not a window of its own: the time is the
# outage's.
def test_12388_a_late_arrival_gets_what_is_left_of_the_outage():
    controller = AdmissionController()
    controller.grace = 0.6
    install = _admission_key()
    controller.configure_pools(install, {POOL_ALL: 1})
    controller.disable_master(install.master_idx)
    time.sleep(0.45)

    arrived = time.monotonic()
    with pytest.raises(AdmissionError, match="unavailable for longer than"):
        controller.acquire([PoolKey(install=install, pool=POOL_ALL)])
    waited = time.monotonic() - arrived
    assert 0.05 <= waited < 0.5, (
        f"it waited {waited:.3f}s: what was left of the outage's window was about 0.15s — "
        "not nothing, and not a window of its own"
    )


# TEST12389: a HELLO proposing a credit window of zero fails the handshake,
# naming the window. Under a zero window no chunk may be sent, and with none
# consumed none is ever granted: every stream would stop at its first chunk,
# for good.
def test_12389_handshake_refuses_a_zero_credit_window():
    to_cartridge = io.BytesIO()
    FrameWriter.new(to_cartridge).write(
        Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER, 0)
    )
    to_cartridge.seek(0)
    with pytest.raises(HandshakeError, match="initial_credit"):
        handshake_accept(
            FrameReader.new(to_cartridge), FrameWriter.new(io.BytesIO()), b"{}", {}
        )
