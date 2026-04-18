"""Tests for standard format conversion URN builders."""

from capdag.standard.caps import all_format_conversion_paths, format_conversion_urn
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MEDIA_JSON_VALUE, MEDIA_YAML_VALUE, MediaUrn


# TEST850: all_format_conversion_paths each entry builds a valid parseable CapUrn
def test_850_all_format_conversion_paths_build_valid_urns():
    paths = all_format_conversion_paths()
    assert len(paths) == 18

    for path in paths:
        urn = CapUrn.from_string(format_conversion_urn(path.in_media, path.out_media))
        assert urn.has_tag("op", "convert_format")

        urn_str = urn.to_string()
        reparsed = CapUrn.from_string(urn_str)
        assert reparsed.to_string() == urn_str


# TEST851: format_conversion_urn in/out specs match the input constants
def test_851_format_conversion_urn_specs():
    urn = CapUrn.from_string(format_conversion_urn(MEDIA_JSON_VALUE, MEDIA_YAML_VALUE))

    in_urn = MediaUrn.from_string(urn.in_spec())
    expected_in = MediaUrn.from_string(MEDIA_JSON_VALUE)
    assert in_urn.conforms_to(expected_in)

    out_urn = MediaUrn.from_string(urn.out_spec())
    expected_out = MediaUrn.from_string(MEDIA_YAML_VALUE)
    assert out_urn.conforms_to(expected_out)
