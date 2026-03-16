"""Tests for standard caps URN builders - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
from capdag import CapUrn, MediaUrn
from capdag.standard.caps import (
    CAP_DISCARD,
    coercion_urn,
    all_coercion_paths,
    model_availability_urn,
    model_path_urn,
    llm_conversation_urn,
)
from capdag.urn.media_urn import (
    MEDIA_VOID,
    MEDIA_MODEL_SPEC,
    MEDIA_AVAILABILITY_OUTPUT,
    MEDIA_PATH_OUTPUT,
    MEDIA_STRING,
    MEDIA_INTEGER,
    MEDIA_LLM_INFERENCE_OUTPUT,
)


# TEST307: Test model_availability_urn builds valid cap URN with correct op and media specs
def test_307_model_availability_urn():
    urn = model_availability_urn()
    assert urn.has_tag("op", "model-availability"), "URN must have op=model-availability"
    assert urn.in_spec() == MEDIA_MODEL_SPEC, "input must be model-spec"
    assert urn.out_spec() == MEDIA_AVAILABILITY_OUTPUT, "output must be availability output"


# TEST308: Test model_path_urn builds valid cap URN with correct op and media specs
def test_308_model_path_urn():
    urn = model_path_urn()
    assert urn.has_tag("op", "model-path"), "URN must have op=model-path"
    assert urn.in_spec() == MEDIA_MODEL_SPEC, "input must be model-spec"
    assert urn.out_spec() == MEDIA_PATH_OUTPUT, "output must be path output"


# TEST309: Test model_availability_urn and model_path_urn produce distinct URNs
def test_309_model_availability_and_path_are_distinct():
    avail = model_availability_urn()
    path = model_path_urn()
    assert avail.to_string() != path.to_string(), "availability and path must be distinct cap URNs"


# TEST310: Test llm_conversation_urn uses unconstrained tag (not constrained)
def test_310_llm_conversation_urn_unconstrained():
    urn = llm_conversation_urn("en")
    assert urn.get_tag("unconstrained") is not None, "LLM conversation URN must have 'unconstrained' tag"
    assert urn.has_tag("op", "conversation"), "must have op=conversation"
    assert urn.has_tag("language", "en"), "must have language=en"


# TEST311: Test llm_conversation_urn in/out specs match the expected media URNs semantically
def test_311_llm_conversation_urn_specs():
    urn = llm_conversation_urn("fr")

    # Compare semantically via MediaUrn matching (tag order may differ)
    in_spec = MediaUrn.from_string(urn.in_spec())
    expected_in = MediaUrn.from_string(MEDIA_STRING)
    assert in_spec.conforms_to(expected_in), f"in_spec '{urn.in_spec()}' must conform to MEDIA_STRING '{MEDIA_STRING}'"

    out_spec = MediaUrn.from_string(urn.out_spec())
    expected_out = MediaUrn.from_string(MEDIA_LLM_INFERENCE_OUTPUT)
    assert out_spec.conforms_to(expected_out), f"out_spec '{urn.out_spec()}' must conform to '{MEDIA_LLM_INFERENCE_OUTPUT}'"


# TEST312: Test all URN builders produce parseable cap URNs
def test_312_all_urn_builders_produce_valid_urns():
    # Each of these must not raise
    avail = model_availability_urn()
    path = model_path_urn()
    conv = llm_conversation_urn("en")

    # Verify they roundtrip through CapUrn parsing
    avail_str = model_availability_urn().to_string()
    parsed = CapUrn.from_string(avail_str)
    assert parsed is not None, "model_availability_urn must be parseable"

    path_str = model_path_urn().to_string()
    parsed = CapUrn.from_string(path_str)
    assert parsed is not None, "model_path_urn must be parseable"


# TEST473: CAP_DISCARD parses as valid CapUrn with in=media: and out=media:void
def test_473_cap_discard_parses_as_valid_urn():
    urn = CapUrn.from_string(CAP_DISCARD)
    assert urn.in_spec() == "media:", "CAP_DISCARD input must be wildcard media:"
    assert urn.out_spec() == MEDIA_VOID, "CAP_DISCARD output must be media:void"


# TEST474: CAP_DISCARD accepts specific-input/void-output caps
def test_474_cap_discard_accepts_specific_void_cap():
    discard = CapUrn.from_string(CAP_DISCARD)
    specific = CapUrn.from_string('cap:in="media:pdf";op=shred;out="media:void"')

    # discard (pattern) accepts specific (instance) — the specific cap
    # IS more specific (has op=shred and specific input)
    assert discard.accepts(specific), \
        "CAP_DISCARD must accept a more specific cap with void output"

    # But a cap with non-void output must NOT conform to discard
    non_void = CapUrn.from_string('cap:in="media:pdf";op=convert;out="media:string"')
    assert not discard.accepts(non_void), \
        "CAP_DISCARD must NOT accept a cap with non-void output"


# TEST605: all_coercion_paths builds valid URNs with op=coerce and target tag
def test_605_all_coercion_paths_build_valid_urns():
    paths = all_coercion_paths()
    assert len(paths) > 0, "Coercion paths must not be empty"

    for source, target in paths:
        urn = coercion_urn(source, target)
        assert urn.has_tag("op", "coerce"), \
            f"Coercion URN for {source}→{target} must have op=coerce"
        assert urn.has_tag("target", target), \
            f"Coercion URN for {source}→{target} must have target={target}"

        # Verify roundtrip through string parsing
        urn_str = urn.to_string()
        reparsed = CapUrn.from_string(urn_str)
        assert reparsed is not None, \
            f"Coercion URN for {source}→{target} must roundtrip through parsing"


# TEST606: coercion_urn in/out specs match the type's media URN constant
def test_606_coercion_urn_specs():
    urn = coercion_urn("string", "integer")

    # in_spec should conform to MEDIA_STRING
    in_urn = MediaUrn.from_string(urn.in_spec())
    expected_in = MediaUrn.from_string(MEDIA_STRING)
    assert in_urn.conforms_to(expected_in), \
        f"in_spec '{urn.in_spec()}' should conform to '{MEDIA_STRING}'"

    # out_spec should conform to MEDIA_INTEGER
    out_urn = MediaUrn.from_string(urn.out_spec())
    expected_out = MediaUrn.from_string(MEDIA_INTEGER)
    assert out_urn.conforms_to(expected_out), \
        f"out_spec '{urn.out_spec()}' should conform to '{MEDIA_INTEGER}'"
