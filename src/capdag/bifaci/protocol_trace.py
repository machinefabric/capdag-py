"""Per-segment protocol trace sink for the reference runtime.

The engine's dev trace samples a long-lived relay switch every 2s and writes
transition-deduped JSONL. The capdag CLI runtime (orchestrator ``CliRuntime``)
reuses a long-lived switch too, but the trace is scoped PER SEGMENT: the
shared segment runner both SAMPLES the switch live during the segment (a
250ms sampler) and captures a final SNAPSHOT at teardown -- every line
carries the switch's :class:`~capdag.bifaci.relay_switch.RelaySwitchProtocolStats`,
the same information the Protocol Health view shows. Live sampling is what
makes a HANGING segment observable: the last line written before the harness
kills it shows the stalled active request with its per-stream credit/flow
counters.

Line schema (JSONL, one object per line)::

    { "ts": <unix millis>, "segment": <label>, "stats": <RelaySwitchProtocolStats> }

Lines are deduped by a transition fingerprint that EXCLUDES ever-advancing
clocks (ages/idle/lifetime), so an idle or stalled engine does not spam
identical samples -- one line per protocol transition, mirroring the
reference engine's ``trace_fingerprint``.

This is diagnostics the user explicitly asked for (a ``--trace``/env path):
the FINAL snapshot's serialize and I/O errors are HARD errors surfaced to the
caller. A LIVE sample's write failure is logged and ignored by the CALLER (not
this sink) -- a mid-run trace hiccup must never abort execution; this module
only ever raises, it never itself decides to swallow an error.

Mirrors capdag/src/bifaci/protocol_trace.rs. The mirror uses a plain
``threading.Lock`` (not asyncio) guarding a synchronous file handle, matching
this codebase's thread-based concurrency idiom.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional, Union

from capdag.bifaci.relay_switch import RelaySwitchProtocolStats


# =============================================================================
# ERRORS
# =============================================================================

class ProtocolTraceError(Exception):
    """Base error for a failure to write a protocol trace line. Every variant
    is a hard error: the trace was requested, so a write that cannot happen is
    reported, not dropped."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class IoError(ProtocolTraceError):
    """The trace file could not be opened or written."""

    def __init__(self, cause: OSError):
        super().__init__(f"protocol trace I/O error: {cause}")
        self.cause = cause


class SerializeError(ProtocolTraceError):
    """The snapshot could not be serialized to JSON."""

    def __init__(self, cause: Exception):
        super().__init__(f"protocol trace serialize error: {cause}")
        self.cause = cause


class ClockError(ProtocolTraceError):
    """The system clock is before the Unix epoch (cannot timestamp the line)."""

    def __init__(self):
        super().__init__(
            "protocol trace clock error: system time is before the Unix epoch"
        )


# =============================================================================
# TRANSITION FINGERPRINT
# =============================================================================

def trace_fingerprint(stats: RelaySwitchProtocolStats) -> str:
    """Transition fingerprint: everything the snapshot says that MATTERS,
    EXCLUDING the ever-advancing clocks (a request's ``age_ms``/``idle_ms``, a
    termination's ``lifetime_ms``) which change every sample and would defeat
    dedup. Mirrors the reference engine's ``trace_fingerprint`` so both traces
    dedup on the same notion of "a protocol transition".

    Canonicalized with sorted object keys so identical logical state always
    produces an identical string regardless of dict iteration order.
    """
    active = [
        {
            "rid": r.rid,
            "cap": r.cap_urn,
            "phase": r.phase.value,
            "children": r.children,
            "streams": [
                {
                    "id": s.stream_id,
                    "fi": s.stats.frames_in,
                    "fo": s.stats.frames_out,
                    "bi": s.stats.bytes_in,
                    "bo": s.stats.bytes_out,
                    "credit": s.stats.credit_outstanding,
                    "unbounded": s.stats.unbounded,
                    "ended": s.stats.ended,
                }
                for s in r.streams
            ],
        }
        for r in stats.requests.active
    ]
    recent_terminated = stats.requests.recent_terminated
    last_terminated = (
        [recent_terminated[-1].rid, recent_terminated[-1].kind.as_str()]
        if recent_terminated
        else None
    )
    fingerprint_obj: Dict[str, Any] = {
        "total_registered": stats.requests.total_registered,
        "terminated_by_kind": dict(stats.requests.terminated_by_kind),
        "terminated_len": len(recent_terminated),
        "last_terminated": last_terminated,
        "drops": stats.drops.to_dict(),
        "hosts": {k: v.to_dict() for k, v in stats.hosts.items()},
        "active": active,
    }
    return json.dumps(fingerprint_obj, sort_keys=True, separators=(",", ":"))


# =============================================================================
# SINK
# =============================================================================

class ProtocolTraceSink:
    """An append-only JSONL sink for per-segment protocol snapshots. Thread-safe
    (one lock guards the file handle and the dedup fingerprint together) so the
    dedup check and the write are atomic across a concurrent live sampler
    thread and the final snapshot.

    Cheap to share across threads -- construct once per segment (via
    :meth:`open`) and pass the same instance to both the live sampler and the
    final-snapshot call site.
    """

    def __init__(self, file, path: Path):
        self._lock = threading.Lock()
        self._file = file
        self._path = path
        # Fingerprint of the last line actually written; None before the first.
        self._last_fingerprint: Optional[str] = None

    @classmethod
    def open(cls, path: Union[str, os.PathLike]) -> "ProtocolTraceSink":
        """Open ``path`` for append, creating it if absent. A failure to open
        (bad directory, no permission) is a hard error -- the caller asked for
        a trace."""
        p = Path(path)
        try:
            f = open(p, "a", encoding="utf-8")
        except OSError as exc:
            raise IoError(exc) from exc
        return cls(f, p)

    def _write_line_locked(
        self, stats: RelaySwitchProtocolStats, segment_label: str
    ) -> None:
        """Append one JSONL line ``{ ts, segment, stats }``, then flush. The
        trace must be complete on disk even if the process is killed right
        after a failing segment. Caller holds ``self._lock``."""
        ts = time.time()
        if ts < 0:
            raise ClockError()
        ts_ms = int(ts * 1000)
        line = {
            "ts": ts_ms,
            "segment": segment_label,
            "stats": stats.to_dict(),
        }
        try:
            buf = json.dumps(line, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise SerializeError(exc) from exc
        try:
            self._file.write(buf + "\n")
            self._file.flush()
        except OSError as exc:
            raise IoError(exc) from exc

    def record(self, stats: RelaySwitchProtocolStats, segment_label: str) -> None:
        """Append one line unconditionally (no dedup). Serialize, clock, and
        I/O failures are raised to the caller (this is requested diagnostics;
        a silently dropped line would hide the very problem the trace
        exposes)."""
        with self._lock:
            self._write_line_locked(stats, segment_label)
            # Keep the fingerprint coherent so a later `record_deduped` compares
            # against what is actually on disk.
            self._last_fingerprint = trace_fingerprint(stats)

    def record_deduped(
        self, stats: RelaySwitchProtocolStats, segment_label: str
    ) -> None:
        """Append one line ONLY when the protocol state changed since the last
        line written -- so an idle or stalled engine leaves the trace silent
        instead of spamming identical samples. The fingerprint check and the
        write share one lock, so concurrent samplers cannot interleave a
        duplicate."""
        fingerprint = trace_fingerprint(stats)
        with self._lock:
            if self._last_fingerprint == fingerprint:
                return
            self._write_line_locked(stats, segment_label)
            self._last_fingerprint = fingerprint
