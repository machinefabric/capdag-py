"""Concurrency-pool model tests (``bifaci.pools``) — shared-range TEST
numbers with the Rust reference (TEST1520–TEST1523)."""

import pytest

from capdag.bifaci.pools import (
    POOL_ALL,
    DesiredCapacities,
    PoolDeclarations,
    PoolState,
    chain_from_states,
    decode_desired,
    decode_pool_states,
    effective_capacity,
    encode_desired,
    encode_pool_states,
)
from capdag.urn.cap_urn import CapUrn


def _caps(*urns):
    return [CapUrn.from_string(u) for u in urns]


# TEST1520: effective capacity is min(configured, available) under the
# 0-as-unlimited convention, with absent available treated as unlimited —
# the one formula every admission decision reduces to.
def test_1520_effective_capacity_min_semantics():
    assert effective_capacity(0, None) == 0, "unlimited stays unlimited"
    assert effective_capacity(4, None) == 4, "absent available is a free pass"
    assert effective_capacity(4, 0) == 4, "available 0 is unlimited, not zero slots"
    assert effective_capacity(0, 2) == 2, "self-limit binds an unlimited configured"
    assert effective_capacity(4, 1) == 1, "the smaller bound wins"
    assert effective_capacity(1, 4) == 1, "in either direction"


# TEST1521: a cap is a pool of one and `all` always exists — the declared
# state map materializes every singleton, every declared pool, and `all`,
# with capacities resolved by pool name uniformly.
def test_1521_declared_states_materialize_every_pool():
    declared_caps = _caps(
        'cap:generate;in="media:enc=utf-8";out="media:enc=utf-8"',
        'cap:embed;in="media:enc=utf-8";out="media:embeddings"',
    )
    generate = declared_caps[0].to_string()
    embed = declared_caps[1].to_string()
    declarations = PoolDeclarations(
        pools={"gpu": [generate, embed]},
        capacities={generate: 1, "gpu": 1, POOL_ALL: 8},
    ).validated(declared_caps)
    states = declarations.declared_states(declared_caps)

    assert len(states) == 4, "two singletons + gpu + all"
    assert states[generate].declared == 1
    assert states[generate].configured == 1, "configured starts at declared"
    assert states[embed].declared == 0, "undeclared singleton is unlimited"
    assert states["gpu"].declared == 1
    assert states["gpu"].caps == [generate, embed]
    assert states[POOL_ALL].declared == 8
    assert len(states[POOL_ALL].caps) == 2, "all contains every cap"

    # The chain: singleton, declared pools containing the cap, all.
    assert declarations.chain_for(generate) == [generate, "gpu", POOL_ALL]
    # And the same chain derived from the materialized states.
    assert chain_from_states(states, generate) == [generate, "gpu", POOL_ALL]


# TEST1522: pool declarations are validated hard — reserved name, a pool
# named like a cap URN, an unknown member, a duplicate member, and an
# unknown capacity key are each refused with the offender named.
def test_1522_pool_declaration_validation_refuses_illegal_shapes():
    declared_caps = _caps('cap:generate;in="media:enc=utf-8";out="media:enc=utf-8"')
    generate = declared_caps[0].to_string()

    with pytest.raises(ValueError, match="reserved"):
        PoolDeclarations(pools={POOL_ALL: [generate]}).validated(declared_caps)

    with pytest.raises(ValueError, match="parses as a cap URN"):
        PoolDeclarations(pools={generate: [generate]}).validated(declared_caps)

    with pytest.raises(ValueError, match="names no cap"):
        PoolDeclarations(
            pools={"gpu": ['cap:absent;in="media:";out="media:"']}
        ).validated(declared_caps)

    with pytest.raises(ValueError, match="more than once"):
        PoolDeclarations(pools={"gpu": [generate, generate]}).validated(declared_caps)

    with pytest.raises(ValueError, match="neither"):
        PoolDeclarations(capacities={"warp": 3}).validated(declared_caps)


# TEST1523: the wire codec round-trips the full map — including the
# absent-vs-present distinction on `available`, which is the
# static-vs-self-limited distinction and must never collapse.
def test_1523_pool_state_wire_round_trip():
    singleton = 'cap:x;in="media:";out="media:"'
    states = {
        singleton: PoolState(
            declared=2, configured=4, available=1, active=1, queued=3
        ),
        POOL_ALL: PoolState.declared_at_rest(0, [singleton]),
    }

    decoded = decode_pool_states(encode_pool_states(states))
    assert decoded == states
    assert decoded[singleton].effective() == 1
    assert decoded[POOL_ALL].available is None, "static stays static"

    with pytest.raises(ValueError):
        decode_pool_states(b"not json")

    desired: DesiredCapacities = {POOL_ALL: 6}
    assert decode_desired(encode_desired(desired)) == desired
