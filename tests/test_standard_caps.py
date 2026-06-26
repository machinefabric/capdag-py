"""Tests for standard caps URN builders - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
from capdag import CapUrn, MediaUrn
from capdag.standard.caps import (
    CAP_DISCARD,
    CAP_ADAPTER_SELECTION,
    coercion_urn,
    all_coercion_paths,
    model_availability_urn,
    model_path_urn,
    llm_generate_text_urn,
    identity_urn,
    adapter_selection_urn,
    lookup_cap_fabric_cap,
    lookup_media_def_fabric_cap,
)
from capdag.urn.media_urn import (
    MEDIA_VOID,
    MEDIA_MODEL_SPEC,
    MEDIA_AVAILABILITY_OUTPUT,
    MEDIA_PATH_OUTPUT,
    MEDIA_STRING,
    MEDIA_INTEGER,
    MEDIA_ADAPTER_SELECTION,
    MEDIA_FABRIC_DEFVER,
)
from capdag.cap.definition import CliFlagSource


# TEST307: Test model_availability_urn builds valid cap URN with correct marker and media defs
def test_307_model_availability_urn():
    urn = model_availability_urn()
    assert urn.has_marker_tag("model-availability"), "URN must have model-availability marker"
    assert urn.in_spec() == MEDIA_MODEL_SPEC, "input must be model-spec"
    assert urn.out_spec() == MEDIA_AVAILABILITY_OUTPUT, "output must be availability output"


# TEST308: Test model_path_urn builds valid cap URN with correct marker and media defs
def test_308_model_path_urn():
    urn = model_path_urn()
    assert urn.has_marker_tag("model-path"), "URN must have model-path marker"
    assert urn.in_spec() == MEDIA_MODEL_SPEC, "input must be model-spec"
    assert urn.out_spec() == MEDIA_PATH_OUTPUT, "output must be path output"


# TEST309: Test model_availability_urn and model_path_urn produce distinct URNs
def test_309_model_availability_and_path_are_distinct():
    avail = model_availability_urn()
    path = model_path_urn()
    assert avail.to_string() != path.to_string(), "availability and path must be distinct cap URNs"


# TEST310: llm_generate_text_urn() produces a valid cap URN with text (enc=utf-8) in/out specs
def test_310_llm_generate_text_urn_shape():
    urn = CapUrn.from_string(llm_generate_text_urn())
    assert urn is not None, "llm_generate_text_urn must parse as a valid CapUrn"
    assert urn.has_marker_tag("generate_text"), "must have generate_text marker"
    assert MediaUrn.from_string(urn.in_spec()).conforms_to(MediaUrn.from_string(MEDIA_STRING))
    assert MediaUrn.from_string(urn.out_spec()).conforms_to(MediaUrn.from_string(MEDIA_STRING))



# TEST312: Test all URN builders produce parseable cap URNs
def test_312_all_urn_builders_produce_valid_urns():
    # Each of these must not raise
    avail = model_availability_urn()
    path = model_path_urn()
    gen_text = llm_generate_text_urn()

    # Verify they roundtrip through CapUrn parsing
    avail_str = model_availability_urn().to_string()
    parsed = CapUrn.from_string(avail_str)
    assert parsed is not None, "model_availability_urn must be parseable"

    path_str = model_path_urn().to_string()
    parsed = CapUrn.from_string(path_str)
    assert parsed is not None, "model_path_urn must be parseable"

    gen_parsed = CapUrn.from_string(gen_text)
    assert gen_parsed is not None, "llm_generate_text_urn must be parseable"


# TEST473: CAP_DISCARD parses as valid CapUrn with in=media: and out=media:void
def test_473_cap_discard_parses_as_valid_urn():
    urn = CapUrn.from_string(CAP_DISCARD)
    assert urn.in_spec() == "media:", "CAP_DISCARD input must be wildcard media:"
    assert urn.out_spec() == MEDIA_VOID, "CAP_DISCARD output must be media:void"


# TEST474: CAP_DISCARD accepts specific-input/void-output caps
def test_474_cap_discard_accepts_specific_void_cap():
    discard = CapUrn.from_string(CAP_DISCARD)
    specific = CapUrn.from_string('cap:in="media:ext=pdf";shred;out="media:void"')

    # discard (pattern) accepts specific (instance) — the specific cap
    # IS more specific (has shred and specific input)
    assert discard.accepts(specific), \
        "CAP_DISCARD must accept a more specific cap with void output"

    # But a cap with non-void output must NOT conform to discard
    non_void = CapUrn.from_string('cap:in="media:ext=pdf";convert;out="media:string"')
    assert not discard.accepts(non_void), \
        "CAP_DISCARD must NOT accept a cap with non-void output"


# TEST605: all_coercion_paths each entry builds a valid parseable CapUrn
def test_605_all_coercion_paths_build_valid_urns():
    paths = all_coercion_paths()
    assert len(paths) > 0, "Coercion paths must not be empty"

    for source, target in paths:
        urn = coercion_urn(source, target)
        assert urn.has_marker_tag("coerce"), \
            f"Coercion URN for {source}→{target} must have coerce marker"

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


# TEST1272: CAP_ADAPTER_SELECTION constant parses as a valid CapUrn
def test_1272_adapter_cap_constant_parses():
    urn = CapUrn.from_string(CAP_ADAPTER_SELECTION)
    assert urn is not None, \
        f"CAP_ADAPTER_SELECTION must be a valid cap URN: {CAP_ADAPTER_SELECTION}"


# TEST1273: adapter_selection_urn() returns a valid CapUrn with correct in/out specs
def test_1273_adapter_selection_urn_builder():
    urn = adapter_selection_urn()
    # in_spec should be bare "media:" (accepts any)
    assert urn.in_spec() == "media:", \
        f"in_spec must be 'media:', got: {urn.in_spec()}"
    # out_spec should conform to the adapter selection media URN
    out_urn = MediaUrn.from_string(urn.out_spec())
    expected_out = MediaUrn.from_string(MEDIA_ADAPTER_SELECTION)
    assert out_urn.conforms_to(expected_out), \
        f"out_spec '{urn.out_spec()}' should conform to adapter-selection URN"


# TEST1275: A cap whose output is adapter-selection can dispatch adapter-selection requests;
# identity (wildcard output) cannot, because wildcard output cannot satisfy a specific output requirement.
def test_1275_adapter_selection_dispatchable_by_specific_provider():
    adapter_request = adapter_selection_urn()

    # A provider that outputs exactly adapter-selection media can dispatch the request
    specific_provider = CapUrn.from_string(CAP_ADAPTER_SELECTION)
    assert specific_provider.is_dispatchable(adapter_request), \
        "A cap with adapter-selection output must be dispatchable for adapter-selection requests"

    # Identity has wildcard output (media:) — cannot guarantee adapter-selection output
    identity = identity_urn()
    assert not identity.is_dispatchable(adapter_request), \
        "Identity (wildcard output) must NOT dispatch adapter-selection requests: " \
        "wildcard output cannot satisfy a specific output requirement"


# TEST0069: lookup_cap_fabric_cap has a --defver arg with MEDIA_FABRIC_DEFVER and required==False
def test_0069_lookup_cap_fabric_has_defver_arg():
    cap = lookup_cap_fabric_cap()

    defver_args = [
        arg for arg in cap.get_args()
        if arg.media_urn == MEDIA_FABRIC_DEFVER
    ]
    assert len(defver_args) == 1, (
        f"lookup_cap_fabric_cap must have exactly one arg with media_urn==MEDIA_FABRIC_DEFVER, "
        f"got {len(defver_args)}"
    )
    defver_arg = defver_args[0]
    assert defver_arg.required is False, (
        f"--defver arg must be optional (required=False), got required={defver_arg.required}"
    )
    cli_sources = [s for s in defver_arg.sources if isinstance(s, CliFlagSource)]
    assert len(cli_sources) == 1, (
        f"--defver arg must have exactly one CliFlagSource, got {defver_arg.sources}"
    )
    assert cli_sources[0].flag_name() == "--defver", (
        f"CliFlagSource flag name must be '--defver', got {cli_sources[0].flag_name()!r}"
    )


# TEST0070: lookup_media_def_fabric_cap has a --defver arg with MEDIA_FABRIC_DEFVER and required==False
def test_0070_lookup_media_def_fabric_has_defver_arg():
    cap = lookup_media_def_fabric_cap()

    defver_args = [
        arg for arg in cap.get_args()
        if arg.media_urn == MEDIA_FABRIC_DEFVER
    ]
    assert len(defver_args) == 1, (
        f"lookup_media_def_fabric_cap must have exactly one arg with media_urn==MEDIA_FABRIC_DEFVER, "
        f"got {len(defver_args)}"
    )
    defver_arg = defver_args[0]
    assert defver_arg.required is False, (
        f"--defver arg must be optional (required=False), got required={defver_arg.required}"
    )
    cli_sources = [s for s in defver_arg.sources if isinstance(s, CliFlagSource)]
    assert len(cli_sources) == 1, (
        f"--defver arg must have exactly one CliFlagSource, got {defver_arg.sources}"
    )
    assert cli_sources[0].flag_name() == "--defver", (
        f"CliFlagSource flag name must be '--defver', got {cli_sources[0].flag_name()!r}"
    )
