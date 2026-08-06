"""Live-feed transport resolution (13.2 §Reference Media, live family).

A live feed is an input that arrives BY REFERENCE: the wire value is a
small selector record, and the runtime — never the op — resolves it by
opening a capture device through a registered ``LiveFeedProvider`` and
delivering an UNBOUNDED SEQUENCE stream of items labeled with the arg's
stdin content URN. The op is transport-blind.

Backpressure is end-to-end with a defined full-state behavior at every
stage (12.5 §Overrun): a lagging consumer fills the BOUNDED delivery
queue, which blocks the feeder, which fills the capture ring, which
applies the feed's declared overrun policy at the capture edge — the only
place loss can occur, always counted, with an in-band ``gap`` marker on
the next delivered item.

Ships one built-in provider (``media:live;synthetic``): a deterministic
clock source used by the shared test range. Hardware providers are
registered by capture-capable cartridges; sandboxed platforms use
host-mediated capture instead.

(matches Rust src/bifaci/live_feed.rs)
"""

import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from capdag.urn.media_urn import MediaUrn

# Reference-family pattern: any media URN carrying the `live` marker tag is
# a live-feed reference (the live analog of `media:file-path`).
MEDIA_LIVE_FEED = "media:live"

# The built-in deterministic test feed's reference URN.
MEDIA_LIVE_SYNTHETIC = "media:live;synthetic"

# Overrun policies (12.5 §Overrun).
OVERRUN_DROP_OLDEST = "drop-oldest"
OVERRUN_FAIL = "fail"

# Ring capacity when the selector's params don't override it (`ring`).
DEFAULT_RING_CAP = 64
# Bounded delivery-queue capacity — the op-side half of the backpressure
# chain. Small on purpose: the ring is the elastic stage.
DELIVERY_QUEUE_CAP = 8


class LiveFeedError(Exception):
    """A live-feed resolution or capture failure — always hard, never a
    silent empty feed."""


@dataclass
class LiveFeedStop:
    """Stop conditions for a feed (absent = "until stopped")."""

    duration_ms: Optional[int] = None
    max_items: Optional[int] = None


@dataclass
class LiveFeedSelector:
    """The selector record carried as a live-feed reference arg's value
    (JSON). An empty value is the all-defaults selector."""

    device: Optional[str] = None
    params: Dict = field(default_factory=dict)
    stop: LiveFeedStop = field(default_factory=LiveFeedStop)
    on_overrun: str = OVERRUN_DROP_OLDEST

    @classmethod
    def parse(cls, raw: bytes) -> "LiveFeedSelector":
        """Parse a selector from the reference value bytes. Empty bytes are
        the all-defaults selector; anything else must be a valid selector
        record — an unparseable selector is a hard error, never a silent
        default."""
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return cls()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise LiveFeedError(
                f"live-feed selector is not a valid selector record: {e} (value: {text})"
            )
        if not isinstance(obj, dict):
            raise LiveFeedError(
                f"live-feed selector must be a record, got: {type(obj).__name__}"
            )
        known = {"device", "params", "stop", "on_overrun"}
        unknown = set(obj.keys()) - known
        if unknown:
            raise LiveFeedError(
                f"live-feed selector has unknown field(s) {sorted(unknown)} — "
                f"known fields: {sorted(known)}"
            )
        stop_raw = obj.get("stop") or {}
        if not isinstance(stop_raw, dict):
            raise LiveFeedError("live-feed selector 'stop' must be a record")
        # Unknown stop fields are rejected like the selector's own — a
        # misspelled stop condition silently ignored would run an unbounded
        # feed the caller meant to bound.
        stop_known = {"duration_ms", "max_items"}
        stop_unknown = set(stop_raw.keys()) - stop_known
        if stop_unknown:
            raise LiveFeedError(
                f"live-feed selector has unknown stop field(s) "
                f"{sorted(stop_unknown)} — known fields: {sorted(stop_known)}"
            )

        def _stop_count(key: str):
            value = stop_raw.get(key)
            if value is None:
                return None
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LiveFeedError(
                    f"live-feed selector stop.{key} must be a non-negative "
                    f"integer, got: {value!r}"
                )
            return value

        device = obj.get("device")
        if device is not None and not isinstance(device, str):
            raise LiveFeedError(
                f"live-feed selector 'device' must be a string, got: {device!r}"
            )
        params = obj.get("params") or {}
        if not isinstance(params, dict):
            raise LiveFeedError("live-feed selector 'params' must be a record")
        on_overrun = obj.get("on_overrun", OVERRUN_DROP_OLDEST)
        if on_overrun not in (OVERRUN_DROP_OLDEST, OVERRUN_FAIL):
            raise LiveFeedError(
                f"live-feed selector on_overrun must be '{OVERRUN_DROP_OLDEST}' "
                f"or '{OVERRUN_FAIL}', got: {on_overrun!r}"
            )
        return cls(
            device=device,
            params=params,
            stop=LiveFeedStop(
                duration_ms=_stop_count("duration_ms"),
                max_items=_stop_count("max_items"),
            ),
            on_overrun=on_overrun,
        )


@dataclass
class LiveFeedItem:
    """One captured item as a provider hands it to the sink. ``seq`` and gap
    accounting are assigned by the sink/feeder."""

    payload: bytes
    pts_us: int
    capture_ts_us: int


class _FeedShared:
    def __init__(self, ring_cap: int, policy: str, runtime_overruns: "_Counter"):
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.ring: deque = deque()  # of (LiveFeedItem, seq)
        self.ring_cap = ring_cap
        self.policy = policy
        self.closed = False
        self.producer_done = False
        self.failed: Optional[str] = None
        self.captured = 0
        self.dropped_since_delivery = 0
        self.overruns = 0
        self.runtime_overruns = runtime_overruns

    def close(self) -> None:
        with self.cond:
            self.closed = True
            self.cond.notify_all()


class _Counter:
    """Runtime-wide overrun counter (rides heartbeat meta)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def add(self, n: int) -> None:
        with self._lock:
            self._value += n

    def get(self) -> int:
        with self._lock:
            return self._value


class LiveFeedSink:
    """The provider's write side of a feed. ``push`` applies the overrun
    policy at the capture edge; returning ``False`` means the feed is
    closed — stop capturing and release the device."""

    def __init__(self, shared: _FeedShared, max_items: Optional[int]):
        self._shared = shared
        self._max_items = max_items

    def push(self, item: LiveFeedItem) -> bool:
        s = self._shared
        with s.cond:
            if s.closed:
                return False
            seq = s.captured
            s.captured += 1
            if len(s.ring) >= s.ring_cap:
                if s.policy == OVERRUN_DROP_OLDEST:
                    s.ring.popleft()
                    s.overruns += 1
                    s.dropped_since_delivery += 1
                    s.runtime_overruns.add(1)
                else:  # fail
                    s.failed = (
                        f"FEED_OVERRUN: capture ring full at item seq={seq} — the "
                        f"consumer's window lagged reality and the feed declared "
                        f"on_overrun=fail"
                    )
                    s.closed = True
                    s.cond.notify_all()
                    return False
            s.ring.append((item, seq))
            s.cond.notify_all()
            # max_items counts CAPTURED items; reaching it finishes the
            # producer side (the ring still drains).
            if self._max_items is not None and seq + 1 >= self._max_items:
                s.producer_done = True
                return False
            return not s.closed

    def finish(self) -> None:
        """The producer finished on its own (stop condition, device
        closed). The feeder drains the remaining ring, then the stream
        ends."""
        with self._shared.cond:
            self._shared.producer_done = True
            self._shared.cond.notify_all()

    def is_closed(self) -> bool:
        with self._shared.lock:
            return self._shared.closed


class LiveFeedHandle:
    """A handle to one open feed, held per request so a STOP (non-force
    Cancel on a feed-bearing request) can close the tap and let the run
    drain (15.2 §Runs Stop)."""

    def __init__(self, shared: _FeedShared):
        self._shared = shared

    def close(self) -> None:
        self._shared.close()

    def overruns(self) -> int:
        with self._shared.lock:
            return self._shared.overruns


class LiveFeedProvider:
    """A live-capture backend. ``open`` starts capture pushing into
    ``sink`` from a provider-owned thread and returns the stream-level
    format actuals (dict) for STREAM_START meta, or None."""

    def name(self) -> str:
        raise NotImplementedError

    def open(self, selector: LiveFeedSelector, sink: LiveFeedSink) -> Optional[dict]:
        raise NotImplementedError


class LiveFeedProviders:
    """Registered providers: reference-URN pattern → provider. First
    registered pattern that ACCEPTS the incoming reference URN wins."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: List[Tuple[MediaUrn, LiveFeedProvider]] = []
        self.overruns_counter = _Counter()
        self.register(MEDIA_LIVE_SYNTHETIC, SyntheticFeedProvider())

    def register(self, pattern: str, provider: LiveFeedProvider) -> None:
        pattern_urn = MediaUrn.from_string(pattern)
        family = MediaUrn.from_string(MEDIA_LIVE_FEED)
        if not family.accepts(pattern_urn):
            raise LiveFeedError(
                f"BUG: live-feed provider pattern '{pattern}' is outside the live "
                f"reference family '{MEDIA_LIVE_FEED}' — it would never be resolved"
            )
        with self._lock:
            self._entries.append((pattern_urn, provider))

    def find(self, reference: MediaUrn) -> Optional[LiveFeedProvider]:
        with self._lock:
            for pattern, provider in self._entries:
                if pattern.accepts(reference):
                    return provider
        return None

    def overruns_total(self) -> int:
        """Runtime-wide overrun total (rides heartbeat meta)."""
        return self.overruns_counter.get()


@dataclass
class OpenedFeed:
    """Everything ``open_feed`` returns: a feeder-driven emit loop into
    ``deliver`` (a bounded queue put callable), the stream-level meta, and
    the handle for stop."""

    stream_meta: Optional[dict]
    handle: LiveFeedHandle


def open_feed(
    providers: LiveFeedProviders,
    reference_urn: str,
    selector: LiveFeedSelector,
    deliver: Callable[[object], None],
) -> OpenedFeed:
    """Resolve a live-feed reference: find the provider, open the device,
    and bridge capture → delivery through the ring + feeder thread.

    ``deliver`` is called with ``(value_bytes, meta_dict)`` tuples, an
    Exception on failure, and ``None`` at feed end — the py InputStream
    item contract. It MUST block when the consumer lags (a bounded
    ``queue.Queue.put``): that blocking IS the op-side backpressure stage.
    """
    reference = MediaUrn.from_string(reference_urn)
    provider = providers.find(reference)
    if provider is None:
        raise LiveFeedError(
            f"no live-feed provider registered for reference '{reference_urn}' — "
            f"the runtime cannot open this feed"
        )

    ring_cap = selector.params.get("ring", DEFAULT_RING_CAP)
    if not isinstance(ring_cap, int) or ring_cap < 1:
        raise LiveFeedError(f"live-feed 'ring' param must be a positive integer, got {ring_cap!r}")

    shared = _FeedShared(ring_cap, selector.on_overrun, providers.overruns_counter)
    sink = LiveFeedSink(shared, selector.stop.max_items)
    stream_meta = provider.open(selector, sink)

    deadline = (
        time.monotonic() + selector.stop.duration_ms / 1000.0
        if selector.stop.duration_ms is not None
        else None
    )

    def _feeder() -> None:
        last_delivered_pts: Optional[int] = None
        while True:
            with shared.cond:
                while True:
                    if deadline is not None and time.monotonic() >= deadline:
                        shared.closed = True
                    # An overrun failure preempts remaining ring items: the
                    # feed declared on_overrun=fail, so the loss IS the
                    # outcome.
                    if shared.failed is not None:
                        msg = shared.failed
                        shared.failed = None
                        deliver(LiveFeedError(msg))
                        deliver(None)
                        return
                    if shared.ring:
                        item, seq = shared.ring.popleft()
                        dropped = shared.dropped_since_delivery
                        shared.dropped_since_delivery = 0
                        break
                    if shared.producer_done or shared.closed:
                        deliver(None)  # drained + done → stream ends
                        return
                    shared.cond.wait(timeout=0.05)

            meta: dict = {
                "seq": seq,
                "pts_us": item.pts_us,
                "capture_ts_us": item.capture_ts_us,
            }
            if dropped > 0:
                duration_us = (
                    item.pts_us - last_delivered_pts
                    if last_delivered_pts is not None and item.pts_us >= last_delivered_pts
                    else 0
                )
                meta["gap"] = {"dropped": dropped, "duration_us": duration_us}
            last_delivered_pts = item.pts_us
            # Bounded delivery: this put blocks when the op lags — the
            # feeder stalls, the ring fills, the capture edge applies the
            # overrun policy. Exactly the chain, in order.
            deliver((item.payload, meta))

    threading.Thread(target=_feeder, daemon=True, name="live-feed-feeder").start()
    return OpenedFeed(stream_meta=stream_meta, handle=LiveFeedHandle(shared))


class SyntheticFeedProvider(LiveFeedProvider):
    """The built-in deterministic feed (``media:live;synthetic``): a
    logical clock emitting ``items`` payloads of ``item_bytes`` bytes every
    ``interval_ms`` (params; defaults 10 × 32B × 10ms). ``pts_us`` is the
    LOGICAL clock (i × interval) so tests are deterministic;
    ``capture_ts_us`` is wall clock. ``interval_ms = 0`` floods — with a
    small ``ring`` and a slow consumer this exercises real overruns
    without hardware."""

    def name(self) -> str:
        return "synthetic"

    def open(self, selector: LiveFeedSelector, sink: LiveFeedSink) -> Optional[dict]:
        items = int(selector.params.get("items", 10))
        interval_ms = int(selector.params.get("interval_ms", 10))
        item_bytes = max(1, int(selector.params.get("item_bytes", 32)))

        def _capture() -> None:
            start = int(time.time() * 1_000_000)
            for i in range(items):
                if sink.is_closed():
                    break
                pushed = sink.push(
                    LiveFeedItem(
                        payload=bytes([i % 256]) * item_bytes,
                        pts_us=i * interval_ms * 1000,
                        capture_ts_us=start + i * interval_ms * 1000,
                    )
                )
                if not pushed:
                    break
                if interval_ms > 0:
                    time.sleep(interval_ms / 1000.0)
            sink.finish()

        threading.Thread(target=_capture, daemon=True, name="synthetic-feed").start()
        return {"feed": "synthetic", "interval_ms": interval_ms}
