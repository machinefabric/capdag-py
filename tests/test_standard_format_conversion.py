"""Tests for standard format conversion URN builders."""

from capdag.standard.caps import (
    MEDIA_JSON_CONTENT,
    MEDIA_YAML_CONTENT,
    all_coercion_paths,
    all_format_conversion_paths,
    coercion_urn,
    format_conversion_urn,
)
from capdag.urn.cap_urn import CapEffect, CapUrn
from capdag.urn.media_urn import MEDIA_JSON_RECORD, MEDIA_JSON_VALUE, MEDIA_YAML_VALUE, MediaUrn


# TEST850: all_format_conversion_paths each entry builds a valid parseable CapUrn
def test_850_all_format_conversion_paths_build_valid_urns():
    paths = all_format_conversion_paths()
    assert len(paths) == 12

    for path in paths:
        urn = CapUrn.from_string(format_conversion_urn(path))
        assert urn.has_marker_tag("convert-format")

        urn_str = urn.to_string()
        reparsed = CapUrn.from_string(urn_str)
        assert reparsed.to_string() == urn_str


# TEST851: format_conversion_urn in/out specs match the input constants
def test_851_format_conversion_urn_specs():
    urn = CapUrn.from_string(format_conversion_urn(all_format_conversion_paths()[0]))
    assert urn.effect_kind() == CapEffect.PATCH

    in_urn = MediaUrn.from_string(urn.in_spec())
    expected_in = MediaUrn.from_string(MEDIA_JSON_VALUE)
    assert in_urn.conforms_to(expected_in)

    out_urn = MediaUrn.from_string(urn.out_spec())
    expected_out = MediaUrn.from_string(MEDIA_YAML_VALUE)
    assert out_urn.conforms_to(expected_out)


# TEST7220: converting between JSON and YAML keeps the shape it is given: the
# conversion is a patch, so a JSON list of records gives a YAML list of records,
# content and not a file, and the reverse gives JSON back.
def test_7220_json_yaml_conversion_keeps_the_shape_it_is_given():
    patches = [path for path in all_format_conversion_paths() if path.effect == CapEffect.PATCH]
    assert [(p.in_media, p.out_media) for p in patches] == [
        (MEDIA_JSON_VALUE, MEDIA_YAML_CONTENT),
        (MEDIA_YAML_VALUE, MEDIA_JSON_CONTENT),
    ]

    to_yaml = CapUrn.from_string(format_conversion_urn(patches[0]))
    json_file = MediaUrn.from_string("media:enc=utf8;ext=json;fmt=json;list;record")
    given = to_yaml.infer_runtime_output_media(json_file)
    assert given.is_equivalent(MediaUrn.from_string("media:enc=utf8;fmt=yaml;list;record;!ext")), given

    to_json = CapUrn.from_string(format_conversion_urn(patches[1]))
    back = to_json.infer_runtime_output_media(given)
    assert back.is_equivalent(MediaUrn.from_string("media:enc=utf8;fmt=json;list;record;!ext")), back


# TEST7243: every format conversion's URN is its published cap's: the JSON<->YAML
# patches carry the json-to-yaml and yaml-to-json markers their caps carry, so a
# request for either names a cap that the path's URN serves.
def test_7243_format_conversion_urns_are_the_published_caps():
    published = [
        'cap:convert-format;effect=patch;in="media:enc=utf8;fmt=json";json-to-yaml;out="media:enc=utf8;!ext;fmt=yaml"',
        'cap:convert-format;effect=patch;in="media:enc=utf8;fmt=yaml";out="media:enc=utf8;!ext;fmt=json";yaml-to-json',
        'cap:convert-format;in="media:enc=utf8;fmt=json;list;record";out="media:enc=utf8;fmt=csv;list;record"',
        'cap:convert-format;in="media:enc=utf8;fmt=csv;list;record";out="media:enc=utf8;fmt=json;list;record"',
        'cap:convert-format;in="media:enc=utf8;fmt=yaml;list;record";out="media:enc=utf8;fmt=csv;list;record"',
        'cap:convert-format;in="media:enc=utf8;fmt=csv;list;record";out="media:enc=utf8;fmt=yaml;list;record"',
        'cap:convert-format;in="media:enc=utf8;list";out="media:enc=utf8;fmt=json;list"',
        'cap:convert-format;in="media:enc=utf8;fmt=json;list";out="media:enc=utf8;list"',
        'cap:convert-format;in="media:enc=utf8;list";out="media:enc=utf8;fmt=yaml;list"',
        'cap:convert-format;in="media:enc=utf8;fmt=yaml;list";out="media:enc=utf8;list"',
        'cap:convert-format;in="media:enc=utf8;list";out="media:enc=utf8;fmt=csv;list;record"',
        'cap:convert-format;in="media:enc=utf8;fmt=csv;list;record";out="media:enc=utf8;list"',
    ]
    paths = all_format_conversion_paths()
    assert len(paths) == len(published)
    for path, text in zip(paths, published):
        urn = CapUrn.from_string(format_conversion_urn(path))
        assert urn.is_equivalent(CapUrn.from_string(text)), f"{urn} is not the published {text}"


# TEST7221: a coercion to an object gives a JSON object, not any record.
def test_7221_coercion_to_an_object_gives_a_json_object():
    for source, target in all_coercion_paths():
        if target == "json-object":
            assert coercion_urn(source, target).out_spec() == MEDIA_JSON_RECORD, source
