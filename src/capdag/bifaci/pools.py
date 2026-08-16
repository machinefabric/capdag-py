"""Concurrency pools — the ONE capacity concept of the protocol.

A pool is a named concurrency domain on a cartridge process. Every
registered cap IS a pool of one, named by its canonical cap URN; the
reserved pool ``POOL_ALL`` contains every cap (it is what the deleted
scalar ``handler_capacity`` used to be); the manifest may declare further
named pools over subsets of caps. A cap's POOL CHAIN — its own singleton
pool, every declared pool containing it, then ``all`` — is the set of
domains a dispatch must be admitted through. Queues lead to pools: each
request waits in its cap's singleton-pool queue; shared pools own no queue
of their own.

Three numbers per pool, one effective value:

- ``declared``   — the manifest's shipped default (the cartridge's).
- ``configured`` — the operator's number (starts = declared; persisted by
  the engine's cartridge configuration store).
- ``available``  — OPTIONAL cartridge self-report: what the process can
  serve right now from its OWN state. Absent (``None``) means static: the
  normal, fully-supported case.

``effective = min(configured, available)`` with 0-as-unlimited treated as
infinity inside the min and absent ``available`` treated as infinity.

On the wire the pool-state map rides as JSON bytes in frame meta — exactly
the transport the manifest itself uses — under the ``META_POOLS`` key
(HELLO and every heartbeat reply) and, host→cartridge, the
``META_DESIRED_CAPACITIES`` key on a heartbeat probe. The roster's
``runtime_stats`` carries the same map. (matches Rust bifaci::pools)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from capdag.urn.cap_urn import CapUrn

# The reserved pool containing every cap. Always exists; default capacity 0
# (unlimited). The exact replacement of the deleted scalar handler_capacity.
POOL_ALL = "all"

# Frame-meta key carrying a JSON-encoded pool-state map (HELLO, every
# heartbeat reply, and the roster's runtime stats).
META_POOLS = "pools"

# Frame-meta key on a heartbeat PROBE carrying a JSON-encoded map of pool
# name → desired configured value.
META_DESIRED_CAPACITIES = "desired_capacities"

# Unlimited, as a capacity value. Everywhere a capacity is read, 0 means
# "no limit" — never "zero slots".
CAPACITY_UNLIMITED = 0


def effective_capacity(configured: int, available: Optional[int]) -> int:
    """``min(configured, available)`` under the 0-as-unlimited convention.

    (matches Rust effective_capacity)
    """
    c = float("inf") if configured == CAPACITY_UNLIMITED else configured
    if available is None or available == CAPACITY_UNLIMITED:
        a = float("inf")
    else:
        a = available
    effective = min(c, a)
    if effective == float("inf"):
        return CAPACITY_UNLIMITED
    return int(effective)


@dataclass
class PoolState:
    """One pool's full state. The same shape everywhere: manifest-derived
    declarations, heartbeat replies, roster stats, and the clients'
    cartridge views. (matches Rust PoolState)
    """

    # The manifest's shipped default. 0 = unlimited.
    declared: int = 0
    # The operator's number. Starts equal to ``declared``. 0 = unlimited.
    configured: int = 0
    # The cartridge's self-reported current limit. ``None`` = static (the
    # cartridge never self-adjusts this pool) and is treated as unlimited
    # inside ``effective``.
    available: Optional[int] = None
    # Requests currently being served in this pool.
    active: int = 0
    # Requests currently queued against this pool. For shared pools this
    # counts waiters whose OWN pool has room but this pool does not.
    queued: int = 0
    # Member caps (canonical URNs). Singleton pools omit the list — the
    # pool's name IS its one member.
    caps: List[str] = field(default_factory=list)

    @classmethod
    def declared_at_rest(cls, declared: int, caps: List[str]) -> "PoolState":
        """A declared pool at rest: configured = declared, nothing active,
        no self-report. (matches Rust PoolState::declared)"""
        return cls(declared=declared, configured=declared, caps=caps)

    def effective(self) -> int:
        """The effective admission bound: ``min(configured, available)``
        with 0 meaning unlimited on either input and on the output, and an
        absent ``available`` treated as unlimited."""
        return effective_capacity(self.configured, self.available)

    def to_dict(self) -> Dict:
        result: Dict = {
            "declared": self.declared,
            "configured": self.configured,
            "active": self.active,
            "queued": self.queued,
        }
        if self.available is not None:
            result["available"] = self.available
        if self.caps:
            result["caps"] = list(self.caps)
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "PoolState":
        if not isinstance(data, dict):
            raise ValueError(f"pool state must be an object, got {type(data).__name__}")
        return cls(
            declared=int(data["declared"]),
            configured=int(data["configured"]),
            available=(int(data["available"]) if "available" in data and data["available"] is not None else None),
            active=int(data["active"]),
            queued=int(data["queued"]),
            caps=list(data.get("caps", [])),
        )


# The full pool-state map of one cartridge process, keyed by pool name (a
# canonical cap URN for singletons, a declared pool name, or ``all``).
PoolStates = Dict[str, PoolState]

# The host→cartridge desired-configured map delivered on a heartbeat probe.
DesiredCapacities = Dict[str, int]


@dataclass
class PoolDeclarations:
    """The manifest's pool DECLARATIONS: shared-pool memberships plus a
    capacities map whose keys are pool names uniformly (a canonical cap
    URN, a declared pool name, or ``all``). (matches Rust PoolDeclarations)
    """

    # Declared shared pools: name → member caps (canonical URNs).
    pools: Dict[str, List[str]] = field(default_factory=dict)
    # Declared capacities by pool name. Absent = 0 = unlimited.
    capacities: Dict[str, int] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.pools and not self.capacities

    def to_dict(self) -> Dict:
        result: Dict = {}
        if self.pools:
            result["pools"] = {name: list(members) for name, members in self.pools.items()}
        if self.capacities:
            result["capacities"] = dict(self.capacities)
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "PoolDeclarations":
        return cls(
            pools={name: list(members) for name, members in data.get("pools", {}).items()},
            capacities=dict(data.get("capacities", {})),
        )

    def validated(self, declared_caps: List[CapUrn]) -> "PoolDeclarations":
        """Validate the declarations against the set of declared caps and
        canonicalize every cap reference. Hard errors, never coercion
        (matches Rust PoolDeclarations::validated):

        - a shared pool named ``all`` or parsing as a cap URN;
        - a pool member or capacity key that names no declared cap
          (capacity keys may also name a declared pool or ``all``);
        - a cap listed twice in one pool.
        """
        canonical = [c.to_string() for c in declared_caps]

        def canonicalize(raw: str) -> str:
            try:
                canon = CapUrn.from_string(raw).to_string()
            except Exception as exc:
                raise ValueError(
                    f"pool cap reference '{raw}' is not a valid cap URN: {exc}"
                ) from exc
            if canon not in canonical:
                raise ValueError(
                    f"pool cap reference '{raw}' names no cap declared by this manifest"
                )
            return canon

        pools: Dict[str, List[str]] = {}
        for name in sorted(self.pools):
            members = self.pools[name]
            if name == POOL_ALL:
                raise ValueError(
                    f"pool name '{POOL_ALL}' is reserved for the implicit all-caps pool"
                )
            try:
                CapUrn.from_string(name)
                parses_as_cap = True
            except Exception:
                parses_as_cap = False
            if parses_as_cap:
                raise ValueError(
                    f"pool name '{name}' parses as a cap URN — cap URNs name the "
                    "implicit singleton pools and cannot be redeclared"
                )
            if not members:
                raise ValueError(f"pool '{name}' declares no member caps")
            canon_members: List[str] = []
            for member in members:
                canon = canonicalize(member)
                if canon in canon_members:
                    raise ValueError(f"pool '{name}' lists cap '{canon}' more than once")
                canon_members.append(canon)
            pools[name] = canon_members

        capacities: Dict[str, int] = {}
        for key in sorted(self.capacities):
            value = self.capacities[key]
            if key == POOL_ALL or key in pools:
                canon_key = key
            else:
                try:
                    canon_key = canonicalize(key)
                except ValueError as exc:
                    raise ValueError(
                        f"capacity key '{key}' is neither '{POOL_ALL}', a declared "
                        f"pool, nor a declared cap: {exc}"
                    ) from exc
            if canon_key in capacities:
                raise ValueError(
                    f"capacity for pool '{canon_key}' is declared more than once "
                    "(two spellings of one cap URN?)"
                )
            capacities[canon_key] = value

        return PoolDeclarations(pools=pools, capacities=capacities)

    def declared_states(self, declared_caps: List[CapUrn]) -> PoolStates:
        """Materialize the full declared pool-state map for a cap set: one
        singleton pool per cap, every declared shared pool, and ``all``.
        ``self`` must already be validated against the same cap set.
        (matches Rust PoolDeclarations::declared_states)"""
        states: PoolStates = {}
        all_members = [c.to_string() for c in declared_caps]
        for cap in all_members:
            states[cap] = PoolState.declared_at_rest(
                self.capacities.get(cap, CAPACITY_UNLIMITED), []
            )
        for name, members in self.pools.items():
            states[name] = PoolState.declared_at_rest(
                self.capacities.get(name, CAPACITY_UNLIMITED), list(members)
            )
        states[POOL_ALL] = PoolState.declared_at_rest(
            self.capacities.get(POOL_ALL, CAPACITY_UNLIMITED), all_members
        )
        return states

    def chain_for(self, cap: str) -> List[str]:
        """The pool CHAIN of one cap, in admission order: its singleton
        pool, every declared pool containing it, then ``all``. ``cap`` must
        be the canonical URN string. (matches Rust chain_for)"""
        chain = [cap]
        for name in sorted(self.pools):
            if cap in self.pools[name]:
                chain.append(name)
        chain.append(POOL_ALL)
        return chain


def chain_from_states(states: PoolStates, cap: str) -> List[str]:
    """The chain of one cap over a MATERIALIZED state map (roster /
    heartbeat truth): the singleton pool, every pool listing the cap as a
    member, then ``all``. Order: singleton, declared pools in sorted order,
    ``all``. (matches Rust chain_from_states)"""
    chain: List[str] = []
    if cap in states:
        chain.append(cap)
    for name in sorted(states):
        if name in (POOL_ALL, cap):
            continue
        if cap in states[name].caps:
            chain.append(name)
    if POOL_ALL in states:
        chain.append(POOL_ALL)
    return chain


def encode_pool_states(states: PoolStates) -> bytes:
    """Encode a pool-state map for frame meta (JSON bytes — the manifest's
    own transport). (matches Rust encode_pool_states)"""
    return json.dumps({name: state.to_dict() for name, state in states.items()}).encode("utf-8")


def decode_pool_states(data: bytes) -> PoolStates:
    """Decode a pool-state map from frame meta. A malformed map is a
    protocol error at the caller's boundary — never partially read.
    (matches Rust decode_pool_states)"""
    try:
        raw = json.loads(data.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("pool-state map must be a JSON object")
        return {name: PoolState.from_dict(state) for name, state in raw.items()}
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError(f"malformed pool-state map: {exc}") from exc


def encode_desired(desired: DesiredCapacities) -> bytes:
    """Encode the desired-configured map for a heartbeat probe."""
    return json.dumps(dict(desired)).encode("utf-8")


def decode_desired(data: bytes) -> DesiredCapacities:
    """Decode the desired-configured map from a heartbeat probe."""
    try:
        raw = json.loads(data.decode("utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("desired-capacities map must be a JSON object")
        return {name: int(value) for name, value in raw.items()}
    except (ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError(f"malformed desired-capacities map: {exc}") from exc
