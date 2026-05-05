"""Tests for planner cardinality analysis."""

import json

from capdag.planner.cardinality import (
    InputCardinality,
    CardinalityCompatibility,
    CapShapeInfo,
    CardinalityPattern,
    InputStructure,
    StructureCompatibility,
    MediaShape,
    ShapeCompatibility,
    StrandShapeAnalysis,
)


# TEST688: Tests is_multiple method correctly identifies multi-value cardinalities Verifies Single returns false while Sequence and AtLeastOne return true
def test_688_is_multiple():
    assert not InputCardinality.SINGLE.is_multiple()
    assert InputCardinality.SEQUENCE.is_multiple()
    assert InputCardinality.AT_LEAST_ONE.is_multiple()


# TEST689: Tests accepts_single method identifies cardinalities that accept single values Verifies Single and AtLeastOne accept singles while Sequence does not
def test_689_accepts_single():
    assert InputCardinality.SINGLE.accepts_single()
    assert not InputCardinality.SEQUENCE.accepts_single()
    assert InputCardinality.AT_LEAST_ONE.accepts_single()


# TEST690: Tests cardinality compatibility for single-to-single data flow Verifies Direct compatibility when both input and output are Single
def test_690_compatibility_single_to_single():
    compatibility = InputCardinality.SINGLE.is_compatible_with(InputCardinality.SINGLE)
    assert compatibility == CardinalityCompatibility.DIRECT


# TEST691: Tests cardinality compatibility when wrapping single value into array Verifies WrapInArray compatibility when Sequence expects Single input
def test_691_compatibility_single_to_vector():
    compatibility = InputCardinality.SEQUENCE.is_compatible_with(InputCardinality.SINGLE)
    assert compatibility == CardinalityCompatibility.WRAP_IN_ARRAY


# TEST692: Tests cardinality compatibility when unwrapping array to singles Verifies RequiresFanOut compatibility when Single expects Sequence input
def test_692_compatibility_vector_to_single():
    compatibility = InputCardinality.SINGLE.is_compatible_with(InputCardinality.SEQUENCE)
    assert compatibility == CardinalityCompatibility.REQUIRES_FAN_OUT


# TEST693: Tests cardinality compatibility for sequence-to-sequence data flow Verifies Direct compatibility when both input and output are Sequence
def test_693_compatibility_vector_to_vector():
    compatibility = InputCardinality.SEQUENCE.is_compatible_with(InputCardinality.SEQUENCE)
    assert compatibility == CardinalityCompatibility.DIRECT


# TEST697: Tests CapShapeInfo correctly identifies one-to-one pattern Verifies Single input and Single output result in OneToOne pattern
def test_697_cap_shape_info_one_to_one():
    info = CapShapeInfo.from_cap_specs(
        'cap:in="media:text";echo;out="media:text"',
        "media:text",
        "media:text",
    )
    assert info.cardinality_pattern() == CardinalityPattern.ONE_TO_ONE


# TEST698: CapShapeInfo cardinality is always Single when derived from URN Cardinality comes from context (is_sequence), not from URN tags. The list tag is a semantic type property, not a cardinality indicator.
def test_698_cap_shape_info_cardinality_always_single_from_urn():
    info = CapShapeInfo.from_cap_specs(
        'cap:in="media:file-path;list";test;out="media:file-path;list"',
        "media:file-path;list",
        "media:file-path;list",
    )
    assert info.input.cardinality == InputCardinality.SINGLE
    assert info.output.cardinality == InputCardinality.SINGLE


# TEST699: CapShapeInfo cardinality from URN is always Single; ManyToOne requires is_sequence
def test_699_cap_shape_info_list_urn_still_single_cardinality():
    info = CapShapeInfo.from_cap_specs(
        'cap:in="media:json;list;record";test;out="media:text"',
        "media:json;list;record",
        "media:text",
    )
    assert info.input.cardinality == InputCardinality.SINGLE
    assert info.cardinality_pattern() == CardinalityPattern.ONE_TO_ONE


# TEST709: Tests CardinalityPattern correctly identifies patterns that produce vectors Verifies OneToMany and ManyToMany return true, others return false
def test_709_pattern_produces_vector():
    assert not CardinalityPattern.ONE_TO_ONE.produces_vector()
    assert CardinalityPattern.ONE_TO_MANY.produces_vector()
    assert not CardinalityPattern.MANY_TO_ONE.produces_vector()
    assert CardinalityPattern.MANY_TO_MANY.produces_vector()


# TEST710: Tests CardinalityPattern correctly identifies patterns that require vectors Verifies ManyToOne and ManyToMany return true, others return false
def test_710_pattern_requires_vector():
    assert not CardinalityPattern.ONE_TO_ONE.requires_vector()
    assert not CardinalityPattern.ONE_TO_MANY.requires_vector()
    assert CardinalityPattern.MANY_TO_ONE.requires_vector()
    assert CardinalityPattern.MANY_TO_MANY.requires_vector()


# TEST711: Tests shape chain analysis for simple linear one-to-one capability chains Verifies chains with no fan-out are valid and require no transformation
def test_711_strand_shape_analysis_simple_linear():
    infos = [
        CapShapeInfo.from_cap_specs("cap:pdf-to-png", "media:pdf", "media:image;png"),
        CapShapeInfo.from_cap_specs("cap:resize", "media:image;png", "media:image;png"),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert analysis.is_valid
    assert analysis.fan_out_points == []
    assert not analysis.requires_transformation()


# TEST712: Tests shape chain analysis detects fan-out points in capability chains Fan-out requires is_sequence=true on the cap's output, not a "list" URN tag
def test_712_strand_shape_analysis_with_fan_out():
    infos = [
        CapShapeInfo.from_cap_specs_with_sequence(
            "cap:pdf-to-pages",
            "media:pdf",
            "media:image;png",
            False,
            True,
        ),
        CapShapeInfo.from_cap_specs("cap:thumbnail", "media:image;png", "media:image;png"),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert analysis.is_valid
    assert analysis.fan_out_points == [1]
    assert analysis.requires_transformation()


# TEST713: Tests shape chain analysis handles empty capability chains correctly Verifies empty chains are valid and require no transformation
def test_713_strand_shape_analysis_empty():
    analysis = StrandShapeAnalysis.analyze([])
    assert analysis.is_valid
    assert not analysis.requires_transformation()


# TEST714: Tests InputCardinality serializes and deserializes correctly to/from JSON Verifies JSON round-trip preserves cardinality values
def test_714_cardinality_serialization():
    payload = json.dumps(InputCardinality.SINGLE.value)
    assert payload == '"single"'
    assert json.loads(payload) == InputCardinality.SINGLE.value


# TEST715: Tests CardinalityPattern serializes and deserializes correctly to/from JSON Verifies JSON round-trip preserves pattern values with snake_case formatting
def test_715_pattern_serialization():
    payload = json.dumps(CardinalityPattern.ONE_TO_MANY.value)
    assert payload == '"one_to_many"'
    assert json.loads(payload) == CardinalityPattern.ONE_TO_MANY.value


# TEST720: Tests InputStructure correctly identifies opaque media URNs Verifies that URNs without record marker are parsed as Opaque
def test_720_from_media_urn_opaque():
    assert InputStructure.from_media_urn("media:pdf") == InputStructure.OPAQUE
    assert InputStructure.from_media_urn("media:textable") == InputStructure.OPAQUE
    assert InputStructure.from_media_urn("media:integer") == InputStructure.OPAQUE
    assert InputStructure.from_media_urn("media:file-path;list") == InputStructure.OPAQUE


# TEST721: Tests InputStructure correctly identifies record media URNs Verifies that URNs with record marker tag are parsed as Record
def test_721_from_media_urn_record():
    assert InputStructure.from_media_urn("media:json;record") == InputStructure.RECORD
    assert InputStructure.from_media_urn("media:record;textable") == InputStructure.RECORD
    assert (
        InputStructure.from_media_urn("media:file-metadata;record;textable")
        == InputStructure.RECORD
    )
    assert InputStructure.from_media_urn("media:json;list;record") == InputStructure.RECORD


# TEST722: Tests structure compatibility for opaque-to-opaque data flow
def test_722_structure_compatibility_opaque_to_opaque():
    assert (
        InputStructure.OPAQUE.is_compatible_with(InputStructure.OPAQUE)
        == StructureCompatibility.DIRECT
    )


# TEST723: Tests structure compatibility for record-to-record data flow
def test_723_structure_compatibility_record_to_record():
    assert (
        InputStructure.RECORD.is_compatible_with(InputStructure.RECORD)
        == StructureCompatibility.DIRECT
    )


# TEST724: Tests structure incompatibility for opaque-to-record flow
def test_724_structure_incompatibility_opaque_to_record():
    compat = InputStructure.RECORD.is_compatible_with(InputStructure.OPAQUE)
    assert compat.is_error()


# TEST725: Tests structure incompatibility for record-to-opaque flow
def test_725_structure_incompatibility_record_to_opaque():
    compat = InputStructure.OPAQUE.is_compatible_with(InputStructure.RECORD)
    assert compat.is_error()


# TEST726: Tests applying Record structure adds record marker to URN
def test_726_apply_structure_add_record():
    assert "record" in InputStructure.RECORD.apply_to_urn("media:json")


# TEST727: Tests applying Opaque structure removes record marker from URN
def test_727_apply_structure_remove_record():
    assert "record" not in InputStructure.OPAQUE.apply_to_urn("media:json;record")


# TEST730: Tests MediaShape correctly parses all four combinations
def test_730_media_shape_from_urn_all_combinations():
    shape = MediaShape.from_media_urn("media:textable")
    assert shape.cardinality == InputCardinality.SINGLE
    assert shape.structure == InputStructure.OPAQUE

    shape = MediaShape.from_media_urn("media:json;record")
    assert shape.cardinality == InputCardinality.SINGLE
    assert shape.structure == InputStructure.RECORD

    shape = MediaShape.from_media_urn("media:file-path;list")
    assert shape.cardinality == InputCardinality.SINGLE
    assert shape.structure == InputStructure.OPAQUE

    shape = MediaShape.from_media_urn("media:json;list;record")
    assert shape.cardinality == InputCardinality.SINGLE
    assert shape.structure == InputStructure.RECORD


# TEST731: Tests MediaShape compatibility for matching shapes
def test_731_media_shape_compatible_direct():
    scalar_opaque = MediaShape.scalar_opaque()
    scalar_record = MediaShape.scalar_record()
    list_opaque = MediaShape.list_opaque()
    list_record = MediaShape.list_record()

    assert scalar_opaque.is_compatible_with(scalar_opaque) == ShapeCompatibility.DIRECT
    assert scalar_record.is_compatible_with(scalar_record) == ShapeCompatibility.DIRECT
    assert list_opaque.is_compatible_with(list_opaque) == ShapeCompatibility.DIRECT
    assert list_record.is_compatible_with(list_record) == ShapeCompatibility.DIRECT


# TEST732: Tests MediaShape compatibility for cardinality changes with matching structure
def test_732_media_shape_cardinality_changes():
    scalar_opaque = MediaShape.scalar_opaque()
    list_opaque = MediaShape.list_opaque()
    scalar_record = MediaShape.scalar_record()
    list_record = MediaShape.list_record()

    assert list_opaque.is_compatible_with(scalar_opaque) == ShapeCompatibility.WRAP_IN_ARRAY
    assert list_record.is_compatible_with(scalar_record) == ShapeCompatibility.WRAP_IN_ARRAY
    assert (
        scalar_opaque.is_compatible_with(list_opaque)
        == ShapeCompatibility.REQUIRES_FAN_OUT
    )
    assert (
        scalar_record.is_compatible_with(list_record)
        == ShapeCompatibility.REQUIRES_FAN_OUT
    )


# TEST733: Tests MediaShape incompatibility when structures don't match
def test_733_media_shape_structure_mismatch():
    scalar_opaque = MediaShape.scalar_opaque()
    scalar_record = MediaShape.scalar_record()
    list_opaque = MediaShape.list_opaque()
    list_record = MediaShape.list_record()

    assert scalar_record.is_compatible_with(scalar_opaque).is_error()
    assert scalar_opaque.is_compatible_with(scalar_record).is_error()
    assert list_record.is_compatible_with(list_opaque).is_error()
    assert list_opaque.is_compatible_with(list_record).is_error()
    assert list_record.is_compatible_with(scalar_opaque).is_error()
    assert scalar_opaque.is_compatible_with(list_record).is_error()


# TEST740: Tests CapShapeInfo correctly parses cap specs
def test_740_cap_shape_info_from_specs():
    info = CapShapeInfo.from_cap_specs("cap:test", "media:textable", "media:json;record")
    assert info.input.cardinality == InputCardinality.SINGLE
    assert info.input.structure == InputStructure.OPAQUE
    assert info.output.cardinality == InputCardinality.SINGLE
    assert info.output.structure == InputStructure.RECORD


# TEST741: Tests CapShapeInfo pattern detection — OneToMany requires output is_sequence=true
def test_741_cap_shape_info_pattern():
    info = CapShapeInfo.from_cap_specs_with_sequence(
        "cap:disbind",
        "media:pdf",
        "media:disbound-page;textable",
        False,
        True,
    )
    assert info.cardinality_pattern() == CardinalityPattern.ONE_TO_MANY


# TEST750: Tests shape chain analysis for valid chain with matching structures
def test_750_strand_shape_valid():
    infos = [
        CapShapeInfo.from_cap_specs("cap:resize", "media:image;png", "media:image;png"),
        CapShapeInfo.from_cap_specs("cap:compress", "media:image;png", "media:image;png"),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert analysis.is_valid
    assert analysis.error is None


# TEST751: Tests shape chain analysis detects structure mismatch
def test_751_strand_shape_structure_mismatch():
    infos = [
        CapShapeInfo.from_cap_specs("cap:extract", "media:pdf", "media:textable"),
        CapShapeInfo.from_cap_specs("cap:parse", "media:json;record", "media:data;record"),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert not analysis.is_valid
    assert analysis.error is not None
    assert "Shape mismatch" in analysis.error


# TEST752: Tests shape chain analysis with fan-out (matching structures) Fan-out requires output is_sequence=true on the disbind cap
def test_752_strand_shape_with_fanout():
    infos = [
        CapShapeInfo.from_cap_specs_with_sequence(
            "cap:disbind",
            "media:pdf",
            "media:page;textable",
            False,
            True,
        ),
        CapShapeInfo.from_cap_specs("cap:process", "media:textable", "media:result;textable"),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert analysis.is_valid
    assert analysis.requires_transformation()
    assert analysis.fan_out_points == [1]


# TEST753: Tests shape chain analysis correctly handles list-to-list record flow
def test_753_strand_shape_list_record_to_list_record():
    infos = [
        CapShapeInfo.from_cap_specs(
            "cap:parse_csv",
            "media:csv;textable",
            "media:json;list;record",
        ),
        CapShapeInfo.from_cap_specs(
            "cap:transform",
            "media:json;list;record",
            "media:result;list;record",
        ),
    ]
    analysis = StrandShapeAnalysis.analyze(infos)
    assert analysis.is_valid
    assert not analysis.requires_transformation()
