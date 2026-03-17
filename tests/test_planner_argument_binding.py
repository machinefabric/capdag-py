"""Tests for planner argument binding — mirroring capdag Rust tests.

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import json

import pytest

from capdag.planner.argument_binding import (
    ArgumentBinding,
    ArgumentBindings,
    ArgumentResolutionContext,
    ArgumentSource,
    CapInputFile,
    resolve_binding,
)
from capdag.planner.error import InternalError


def _empty_context(**overrides):
    """Build a minimal ArgumentResolutionContext with no files."""
    defaults = dict(
        input_files=[],
        current_file_index=0,
        previous_outputs={},
        plan_metadata=None,
        cap_settings=None,
        slot_values=None,
    )
    defaults.update(overrides)
    return ArgumentResolutionContext(**defaults)


# ---------------------------------------------------------------------------
# Existing parity tests (test668–test671)
# ---------------------------------------------------------------------------

# TEST668: Resolve slot with populated byte slot_values using step-index key
def test_668_resolve_slot_with_populated_byte_slot_values():
    slot_values = {
        "step_0:media:width;textable;numeric": b"800",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot("media:width;textable;numeric")
    result = resolve_binding(
        binding, ctx,
        'cap:in="media:pdf";op=resize;out="media:pdf"',
        "step_0",
        None, True,
    )
    assert result is not None
    assert result.value == b"800"
    assert result.source == ArgumentSource.SLOT


# TEST669: Resolve slot falls back to default when no slot_value or cap_setting
def test_669_resolve_slot_falls_back_to_default():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:quality;textable;numeric")
    result = resolve_binding(binding, ctx, "cap:op=compress", "step_0", 85, False)
    assert result is not None
    assert result.value == json.dumps(85, separators=(",", ":")).encode("utf-8")
    assert result.source == ArgumentSource.CAP_DEFAULT


# TEST670: Required slot with no value returns error
def test_670_resolve_required_slot_no_value_returns_err():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:question;textable")
    with pytest.raises(InternalError) as exc_info:
        resolve_binding(binding, ctx, "cap:op=generate", "step_0", None, True)
    assert "media:question;textable" in str(exc_info.value)


# TEST671: Optional slot with no value returns None
def test_671_resolve_optional_slot_no_value_returns_none():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:suffix;textable")
    result = resolve_binding(binding, ctx, "cap:op=rename", "step_0", None, False)
    assert result is None


# ---------------------------------------------------------------------------
# New step-index keying tests (test1105–test1109)
# ---------------------------------------------------------------------------

# TEST1105: Two steps with the same cap_urn get distinct slot values via different node_ids.
# This is the core disambiguation scenario that step-index keying was designed to solve.
def test_1105_two_steps_same_cap_urn_different_slot_values():
    cap_urn = 'cap:in="media:pdf";op=make_decision;out="media:bool;textable"'
    slot_name = "media:question;textable;list"
    slot_values = {
        f"step_0:{slot_name}": b"Is this a contract?",
        f"step_2:{slot_name}": b"Is this confidential?",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot(slot_name)

    # step_0 resolves to "Is this a contract?"
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, True)
    assert r0 is not None
    assert r0.value == b"Is this a contract?"
    assert r0.source == ArgumentSource.SLOT

    # step_2 resolves to "Is this confidential?"
    r2 = resolve_binding(binding, ctx, cap_urn, "step_2", None, True)
    assert r2 is not None
    assert r2.value == b"Is this confidential?"
    assert r2.source == ArgumentSource.SLOT

    # Confirm they differ
    assert r0.value != r2.value


# TEST1106: Slot resolution falls through to cap_settings when no slot_value exists.
# cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value.
def test_1106_slot_falls_through_to_cap_settings_shared():
    cap_urn = 'cap:in="media:pdf";op=make_decision;out="media:bool;textable"'
    slot_name = "media:language;textable"
    cap_settings = {
        cap_urn: {slot_name: "en"},
    }
    ctx = _empty_context(cap_settings=cap_settings)
    binding = ArgumentBinding.slot(slot_name)

    # Both steps fall through to cap_settings — same value
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    r1 = resolve_binding(binding, ctx, cap_urn, "step_1", None, False)
    assert r0 is not None and r1 is not None
    assert r0.value == b"en"
    assert r1.value == b"en"
    assert r0.source == ArgumentSource.CAP_SETTING
    assert r1.source == ArgumentSource.CAP_SETTING


# TEST1107: step_0 has a slot_value override, step_1 falls through to cap_settings.
# Proves per-step override works while shared settings remain as fallback.
def test_1107_slot_value_overrides_cap_settings_per_step():
    cap_urn = 'cap:in="media:pdf";op=make_decision;out="media:bool;textable"'
    slot_name = "media:language;textable"
    slot_values = {
        f"step_0:{slot_name}": b"fr",
        # step_1 has no slot_value entry
    }
    cap_settings = {
        cap_urn: {slot_name: "en"},
    }
    ctx = _empty_context(slot_values=slot_values, cap_settings=cap_settings)
    binding = ArgumentBinding.slot(slot_name)

    # step_0: slot_value "fr" (priority 1)
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    assert r0 is not None
    assert r0.value == b"fr"
    assert r0.source == ArgumentSource.SLOT

    # step_1: no slot_value → falls to cap_settings "en" (priority 2)
    r1 = resolve_binding(binding, ctx, cap_urn, "step_1", None, False)
    assert r1 is not None
    assert r1.value == b"en"
    assert r1.source == ArgumentSource.CAP_SETTING


# TEST1108: ResolveAll with node_id threads correctly through to each binding.
def test_1108_resolve_all_passes_node_id():
    slot_values = {
        "step_3:media:width;textable;numeric": b"1024",
        "step_3:media:quality;textable;numeric": b"95",
    }
    ctx = _empty_context(slot_values=slot_values)

    bindings = ArgumentBindings()
    bindings.add("media:width;textable;numeric",
                 ArgumentBinding.slot("media:width;textable;numeric"))
    bindings.add("media:quality;textable;numeric",
                 ArgumentBinding.slot("media:quality;textable;numeric"))

    results = bindings.resolve_all(ctx, "cap:op=resize", "step_3")
    assert len(results) == 2

    by_name = {r.name: r for r in results}
    width = by_name["media:width;textable;numeric"]
    assert width.value == b"1024"
    assert width.source == ArgumentSource.SLOT

    quality = by_name["media:quality;textable;numeric"]
    assert quality.value == b"95"
    assert quality.source == ArgumentSource.SLOT


# TEST1109: Slot key uses node_id, NOT cap_urn — a slot_value keyed by cap_urn must not match.
def test_1109_slot_key_uses_node_id_not_cap_urn():
    cap_urn = 'cap:in="media:pdf";op=resize;out="media:pdf"'
    slot_name = "media:width;textable;numeric"
    # Deliberately key by cap_urn (the OLD format) — should NOT match
    slot_values = {
        f"{cap_urn}:{slot_name}": b"800",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot(slot_name)

    # Should NOT find the value because the key format is wrong (cap_urn instead of node_id)
    result = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    assert result is None, "Old cap_urn-based key must not match node_id-based lookup"
