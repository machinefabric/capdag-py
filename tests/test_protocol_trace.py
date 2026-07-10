"""Tests for the per-segment protocol trace sink.

Covers: bifaci/protocol_trace.py (ProtocolTraceSink.open/record/record_deduped,
trace_fingerprint). Mirrors capdag/src/bifaci/protocol_trace.rs's
`#[cfg(test)] mod tests`.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

from capdag.bifaci.protocol_trace import (
    IoError,
    ProtocolTraceSink,
    trace_fingerprint,
)
from capdag.bifaci.relay_switch import RelaySwitchProtocolStats
from capdag.bifaci.request_state import (
    RequestPhase,
    RequestSnapshot,
    RequestTableSnapshot,
    StreamFlowStats,
    StreamSnapshot,
)
from capdag.bifaci.stats import DropCounters


def _empty_stats(total_registered: int) -> RelaySwitchProtocolStats:
    return RelaySwitchProtocolStats(
        requests=RequestTableSnapshot(
            active=[],
            recent_terminated=[],
            total_registered=total_registered,
            terminated_by_kind={},
        ),
        drops=DropCounters().snapshot(),
        hosts={},
    )


def _active_stats(age_ms: int, idle_ms: int, bytes_in: int) -> RelaySwitchProtocolStats:
    """A snapshot with one active request, so age/idle clocks are present to
    test that the fingerprint ignores them while flow counters are
    significant."""
    return RelaySwitchProtocolStats(
        requests=RequestTableSnapshot(
            active=[
                RequestSnapshot(
                    xid="1",
                    rid="9",
                    phase=RequestPhase.STREAMING,
                    is_peer=False,
                    cap_urn="cap:effect=none",
                    origin_master=None,
                    destination_master=0,
                    age_ms=age_ms,
                    idle_ms=idle_ms,
                    children=0,
                    streams=[
                        StreamSnapshot(
                            stream_id="in",
                            stats=StreamFlowStats(bytes_in=bytes_in),
                        )
                    ],
                )
            ],
            recent_terminated=[],
            total_registered=1,
            terminated_by_kind={},
        ),
        drops=DropCounters().snapshot(),
        hosts={},
    )


def _temp_path(tag: str) -> Path:
    return Path(tempfile.gettempdir()) / (
        f"capdag-protocol-trace-{tag}-{os.getpid()}-{time.time_ns()}.trace"
    )


# TEST1312: Two snapshots recorded to a temp file produce exactly two JSONL lines,
# each carrying ts + segment + a round-tripped stats object (requests/drops).
def test_1312_record_appends_one_json_line_per_snapshot():
    path = _temp_path("roundtrip")
    sink = ProtocolTraceSink.open(path)

    sink.record(_empty_stats(1), "seg-a")
    sink.record(_empty_stats(2), "seg-b")

    contents = path.read_text(encoding="utf-8")
    path.unlink(missing_ok=True)

    lines = contents.splitlines()
    assert len(lines) == 2, "one JSONL line per recorded snapshot"

    first = json.loads(lines[0])
    assert isinstance(first["ts"], int) and first["ts"] >= 0, "ts is a unix-millis integer"
    assert first["segment"] == "seg-a"
    assert first["stats"]["requests"]["total_registered"] == 1
    assert isinstance(first["stats"]["requests"], dict) and isinstance(
        first["stats"]["drops"], dict
    ), "stats carries the requests + drops snapshots"

    second = json.loads(lines[1])
    assert second["segment"] == "seg-b"
    assert second["stats"]["requests"]["total_registered"] == 2


# TEST1313: Dedup: recording identical protocol state twice writes ONE line; a real
# change (a bumped counter, a moved stream byte) writes another. This is what
# keeps a stalled engine's repeated live samples from spamming the trace.
def test_1313_record_deduped_writes_only_on_change():
    path = _temp_path("dedup")
    sink = ProtocolTraceSink.open(path)

    sink.record_deduped(_empty_stats(1), "seg")
    # Identical state -- must NOT write a second line.
    sink.record_deduped(_empty_stats(1), "seg")
    # Changed counter -- must write.
    sink.record_deduped(_empty_stats(2), "seg")
    # A stream flow-counter change is also a transition.
    sink.record_deduped(_active_stats(10, 0, 512), "seg")

    contents = path.read_text(encoding="utf-8")
    path.unlink(missing_ok=True)
    lines = contents.splitlines()
    assert len(lines) == 3, "identical samples dedup to one line; each real change adds one"


# TEST1314: The fingerprint EXCLUDES advancing clocks: two snapshots differing only in
# age_ms/idle_ms are the same transition, while a flow-counter change is a new
# one. If dedup keyed on the whole serialized stats, these clocks would defeat
# it and every sample would write.
def test_1314_fingerprint_ignores_advancing_clocks():
    a = _active_stats(1000, 10, 512)
    b = _active_stats(9000, 8010, 512)  # only age/idle advanced
    assert trace_fingerprint(a) == trace_fingerprint(b), (
        "age/idle advancement alone is not a transition"
    )

    c = _active_stats(9000, 0, 1024)  # bytes moved
    assert trace_fingerprint(a) != trace_fingerprint(c), (
        "a flow-counter change is a transition"
    )


# TEST1315: Requested diagnostics fail HARD, never silently: a write to an unwritable
# sink raises. `/dev/full` opens fine but every write is ENOSPC -- the
# Linux-standard way to exercise a write failure deterministically.
@pytest.mark.skipif(sys.platform != "linux", reason="/dev/full is Linux-specific")
def test_1315_record_to_unwritable_path_is_a_hard_error():
    sink = ProtocolTraceSink.open("/dev/full")
    with pytest.raises(IoError) as exc_info:
        sink.record(_empty_stats(1), "seg")
    assert isinstance(exc_info.value, IoError), (
        f"an unwritable trace surfaces as an I/O error, got {exc_info.value!r}"
    )
