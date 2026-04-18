"""Tests for MediaUrn - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
from capdag import (
    MediaUrn,
    MediaUrnError,
    MEDIA_VOID,
    MEDIA_STRING,
    MEDIA_INTEGER,
    MEDIA_NUMBER,
    MEDIA_BOOLEAN,
    MEDIA_OBJECT,
    MEDIA_IDENTITY,
    MEDIA_PNG,
    MEDIA_JSON,
    MEDIA_PDF,
    MEDIA_AVAILABILITY_OUTPUT,
    MEDIA_PATH_OUTPUT,
    MEDIA_STRING_LIST,
    MEDIA_INTEGER_LIST,
    MEDIA_NUMBER_LIST,
    MEDIA_BOOLEAN_LIST,
    MEDIA_AUDIO,
    MEDIA_VIDEO,
    MEDIA_AUDIO_SPEECH,
    MEDIA_FILE_PATH,
    MEDIA_FILE_PATH_ARRAY,
    MEDIA_DECISION,
    binary_media_urn_for_ext,
    text_media_urn_for_ext,
    image_media_urn_for_ext,
    audio_media_urn_for_ext,
)


# TEST060: Test wrong prefix fails with InvalidPrefix error showing expected and actual prefix
def test_060_wrong_prefix_fails():
    with pytest.raises(MediaUrnError, match="Invalid prefix"):
        MediaUrn.from_string("cap:string")


# TEST061: Test is_binary returns true when textable tag is absent (binary = not textable)
def test_061_is_binary():
    assert MediaUrn.from_string(MEDIA_IDENTITY).is_binary()
    assert MediaUrn.from_string(MEDIA_PNG).is_binary()
    assert MediaUrn.from_string(MEDIA_PDF).is_binary()
    assert MediaUrn.from_string("media:video").is_binary()
    assert MediaUrn.from_string("media:epub").is_binary()
    assert not MediaUrn.from_string("media:textable").is_binary()
    assert not MediaUrn.from_string("media:textable;record").is_binary()
    assert not MediaUrn.from_string(MEDIA_STRING).is_binary()
    assert not MediaUrn.from_string(MEDIA_JSON).is_binary()


# TEST062: Test is_record returns true when record marker tag is present indicating key-value structure
def test_062_is_record():
    obj_urn = MediaUrn.from_string(MEDIA_OBJECT)
    assert obj_urn.is_record()

    # JSON is also a record
    json_urn = MediaUrn.from_string(MEDIA_JSON)
    assert json_urn.is_record()

    # String is not a record
    string_urn = MediaUrn.from_string(MEDIA_STRING)
    assert not string_urn.is_record()


# TEST063: Test is_scalar returns true when list marker tag is absent (scalar is default)
def test_063_is_scalar():
    assert MediaUrn.from_string(MEDIA_STRING).is_scalar()
    assert MediaUrn.from_string(MEDIA_INTEGER).is_scalar()
    assert MediaUrn.from_string(MEDIA_NUMBER).is_scalar()
    assert MediaUrn.from_string(MEDIA_BOOLEAN).is_scalar()
    assert MediaUrn.from_string(MEDIA_OBJECT).is_scalar()
    assert MediaUrn.from_string("media:textable").is_scalar()
    assert not MediaUrn.from_string(MEDIA_STRING_LIST).is_scalar()


# TEST064: Test is_list returns true when list marker tag is present indicating ordered collection
def test_064_is_list():
    list_urn = MediaUrn.from_string(MEDIA_STRING_LIST)
    assert list_urn.is_list()

    int_list_urn = MediaUrn.from_string(MEDIA_INTEGER_LIST)
    assert int_list_urn.is_list()

    # Scalar is not a list
    scalar_urn = MediaUrn.from_string(MEDIA_STRING)
    assert not scalar_urn.is_list()


# TEST065: Test is_opaque returns true when record marker is absent (opaque is default)
def test_065_is_opaque():
    assert MediaUrn.from_string(MEDIA_STRING).is_opaque()
    assert MediaUrn.from_string(MEDIA_STRING_LIST).is_opaque()
    assert MediaUrn.from_string(MEDIA_PDF).is_opaque()
    assert MediaUrn.from_string("media:textable").is_opaque()
    assert not MediaUrn.from_string(MEDIA_OBJECT).is_opaque()
    assert not MediaUrn.from_string(MEDIA_JSON).is_opaque()
    assert not MediaUrn.from_string("media:list;record").is_opaque()


# TEST066: Test is_json returns true only when json marker tag is present for JSON representation
def test_066_is_json():
    json_urn = MediaUrn.from_string(MEDIA_JSON)
    assert json_urn.is_json()

    # Object is not necessarily JSON (could be other map formats)
    obj_urn = MediaUrn.from_string(MEDIA_OBJECT)
    assert not obj_urn.is_json()


# TEST067: Test is_text returns true only when textable marker tag is present
def test_067_is_text():
    string_urn = MediaUrn.from_string(MEDIA_STRING)
    assert string_urn.is_text()

    json_urn = MediaUrn.from_string(MEDIA_JSON)
    assert json_urn.is_text()

    # Binary is not textable
    bin_urn = MediaUrn.from_string(MEDIA_IDENTITY)
    assert not bin_urn.is_text()


# TEST068: Test is_void returns true when void flag or type=void tag is present
def test_068_is_void():
    void_urn = MediaUrn.from_string(MEDIA_VOID)
    assert void_urn.is_void()

    # String is not void
    string_urn = MediaUrn.from_string(MEDIA_STRING)
    assert not string_urn.is_void()


# TEST071: Test to_string roundtrip ensures serialization and deserialization preserve URN structure
def test_071_to_string_roundtrip():
    original = "media:application;subtype=json;v=1"
    urn = MediaUrn.from_string(original)
    serialized = urn.to_string()
    reparsed = MediaUrn.from_string(serialized)
    assert urn == reparsed


# TEST072: Test all media URN constants parse successfully as valid media URNs
def test_072_all_constants_parse():
    constants = [
        MEDIA_VOID,
        MEDIA_STRING,
        MEDIA_INTEGER,
        MEDIA_NUMBER,
        MEDIA_BOOLEAN,
        MEDIA_OBJECT,
        MEDIA_IDENTITY,
        MEDIA_PNG,
        MEDIA_JSON,
    ]
    for const in constants:
        urn = MediaUrn.from_string(const)
        assert urn is not None
        # Roundtrip should work
        reparsed = MediaUrn.from_string(urn.to_string())
        assert urn == reparsed


# TEST073: Test extension helper functions create media URNs with ext tag and correct format
def test_073_extension_helpers():
    # Binary with extension
    bin_ext = binary_media_urn_for_ext("dat")
    bin_urn = MediaUrn.from_string(bin_ext)
    assert bin_urn.extension() == "dat"

    # Text with extension
    text_ext = text_media_urn_for_ext("txt")
    text_urn = MediaUrn.from_string(text_ext)
    assert text_urn.extension() == "txt"
    assert text_urn.is_text()

    # Image with extension
    img_ext = image_media_urn_for_ext("jpg")
    img_urn = MediaUrn.from_string(img_ext)
    assert img_urn.extension() == "jpg"

    # Audio with extension
    audio_ext = audio_media_urn_for_ext("mp3")
    audio_urn = MediaUrn.from_string(audio_ext)
    assert audio_urn.extension() == "mp3"


# TEST074: Test media URN conforms_to using tagged URN semantics with specific and generic requirements
def test_074_media_urn_matching():
    pdf_listing = MediaUrn.from_string(MEDIA_PDF)
    pdf_requirement = MediaUrn.from_string("media:pdf")
    assert pdf_listing.conforms_to(pdf_requirement)

    md_listing = MediaUrn.from_string("media:md;textable")
    md_requirement = MediaUrn.from_string("media:md")
    assert md_listing.conforms_to(md_requirement)

    string_urn = MediaUrn.from_string(MEDIA_STRING)
    string_req = MediaUrn.from_string(MEDIA_STRING)
    assert string_urn.conforms_to(string_req)


# TEST075: Test accepts with implicit wildcards where handlers with fewer tags can handle more requests
def test_075_matching():
    handler = MediaUrn.from_string("media:string")
    request = MediaUrn.from_string("media:string")
    assert handler.accepts(request)

    general_handler = MediaUrn.from_string("media:string")
    assert general_handler.accepts(request)

    same = MediaUrn.from_string("media:string")
    assert handler.accepts(same)


# TEST076: Test specificity increases with more tags for ranking conformance
def test_076_specificity():
    urn1 = MediaUrn.from_string("media:string")
    urn2 = MediaUrn.from_string("media:textable")
    urn3 = MediaUrn.from_string("media:textable;numeric")

    s1 = urn1.specificity()
    s2 = urn2.specificity()
    s3 = urn3.specificity()

    assert s2 >= s1
    assert s3 >= s2


# TEST077: Test serde roundtrip serializes to JSON string and deserializes back correctly
def test_077_serde_roundtrip():
    original_str = "media:application;subtype=json;v=1"
    urn = MediaUrn.from_string(original_str)
    serialized = urn.to_string()
    reparsed = MediaUrn.from_string(serialized)
    assert urn == reparsed


# TEST078: conforms_to behavior between MEDIA_OBJECT and MEDIA_STRING
def test_078_object_does_not_conform_to_string():
    str_urn = MediaUrn.from_string(MEDIA_STRING)
    obj_urn = MediaUrn.from_string(MEDIA_OBJECT)

    assert str_urn.conforms_to(str_urn), "string conforms to string"
    assert obj_urn.conforms_to(obj_urn), "object conforms to object"
    assert not obj_urn.conforms_to(str_urn), \
        "MEDIA_OBJECT should NOT conform to MEDIA_STRING (missing textable)"


# TEST304: Test MEDIA_AVAILABILITY_OUTPUT constant parses as valid media URN with correct tags
def test_304_media_availability_output_constant():
    urn = MediaUrn.from_string(MEDIA_AVAILABILITY_OUTPUT)
    assert urn is not None
    assert urn.is_text()
    assert urn.is_record()


# TEST305: Test MEDIA_PATH_OUTPUT constant parses as valid media URN with correct tags
def test_305_media_path_output_constant():
    urn = MediaUrn.from_string(MEDIA_PATH_OUTPUT)
    assert urn is not None
    assert urn.is_text()
    assert urn.is_record()


# TEST306: Test MEDIA_AVAILABILITY_OUTPUT and MEDIA_PATH_OUTPUT are distinct URNs
def test_306_availability_and_path_output_distinct():
    avail_urn = MediaUrn.from_string(MEDIA_AVAILABILITY_OUTPUT)
    path_urn = MediaUrn.from_string(MEDIA_PATH_OUTPUT)
    assert avail_urn != path_urn
    assert avail_urn.to_string() != path_urn.to_string()


# TEST546: is_image returns true only when image marker tag is present
def test_546_is_image():
    assert MediaUrn.from_string(MEDIA_PNG).is_image()
    assert MediaUrn.from_string("media:image;jpg").is_image()
    # Non-image types
    assert not MediaUrn.from_string(MEDIA_PDF).is_image()
    assert not MediaUrn.from_string(MEDIA_STRING).is_image()
    assert not MediaUrn.from_string(MEDIA_AUDIO).is_image()
    assert not MediaUrn.from_string(MEDIA_VIDEO).is_image()


# TEST547: is_audio returns true only when audio marker tag is present
def test_547_is_audio():
    assert MediaUrn.from_string(MEDIA_AUDIO).is_audio()
    assert MediaUrn.from_string(MEDIA_AUDIO_SPEECH).is_audio()
    assert MediaUrn.from_string("media:audio;mp3").is_audio()
    # Non-audio types
    assert not MediaUrn.from_string(MEDIA_VIDEO).is_audio()
    assert not MediaUrn.from_string(MEDIA_PNG).is_audio()
    assert not MediaUrn.from_string(MEDIA_STRING).is_audio()


# TEST548: is_video returns true only when video marker tag is present
def test_548_is_video():
    assert MediaUrn.from_string(MEDIA_VIDEO).is_video()
    assert MediaUrn.from_string("media:video;mp4").is_video()
    # Non-video types
    assert not MediaUrn.from_string(MEDIA_AUDIO).is_video()
    assert not MediaUrn.from_string(MEDIA_PNG).is_video()
    assert not MediaUrn.from_string(MEDIA_STRING).is_video()


# TEST549: is_numeric returns true only when numeric marker tag is present
def test_549_is_numeric():
    assert MediaUrn.from_string(MEDIA_INTEGER).is_numeric()
    assert MediaUrn.from_string(MEDIA_NUMBER).is_numeric()
    assert MediaUrn.from_string(MEDIA_INTEGER_LIST).is_numeric()
    assert MediaUrn.from_string(MEDIA_NUMBER_LIST).is_numeric()
    # Non-numeric types
    assert not MediaUrn.from_string(MEDIA_STRING).is_numeric()
    assert not MediaUrn.from_string(MEDIA_BOOLEAN).is_numeric()
    assert not MediaUrn.from_string(MEDIA_IDENTITY).is_numeric()


# TEST550: is_bool returns true only when bool marker tag is present
def test_550_is_bool():
    assert MediaUrn.from_string(MEDIA_BOOLEAN).is_bool()
    assert MediaUrn.from_string(MEDIA_BOOLEAN_LIST).is_bool()
    # MEDIA_DECISION is now a JSON record, not bool
    assert not MediaUrn.from_string(MEDIA_DECISION).is_bool()
    # Non-bool types
    assert not MediaUrn.from_string(MEDIA_STRING).is_bool()
    assert not MediaUrn.from_string(MEDIA_INTEGER).is_bool()
    assert not MediaUrn.from_string(MEDIA_IDENTITY).is_bool()


# TEST551: is_file_path returns true for scalar file-path, false for array
def test_551_is_file_path():
    assert MediaUrn.from_string(MEDIA_FILE_PATH).is_file_path()
    # Array file-path is NOT is_file_path (it's is_file_path_array)
    assert not MediaUrn.from_string(MEDIA_FILE_PATH_ARRAY).is_file_path()
    # Non-file-path types
    assert not MediaUrn.from_string(MEDIA_STRING).is_file_path()
    assert not MediaUrn.from_string(MEDIA_IDENTITY).is_file_path()


# TEST552: is_file_path_array returns true for list file-path, false for scalar
def test_552_is_file_path_array():
    assert MediaUrn.from_string(MEDIA_FILE_PATH_ARRAY).is_file_path_array()
    # Scalar file-path is NOT is_file_path_array
    assert not MediaUrn.from_string(MEDIA_FILE_PATH).is_file_path_array()
    # Non-file-path types
    assert not MediaUrn.from_string(MEDIA_STRING_LIST).is_file_path_array()


# TEST553: is_any_file_path returns true for both scalar and array file-path
def test_553_is_any_file_path():
    assert MediaUrn.from_string(MEDIA_FILE_PATH).is_any_file_path()
    assert MediaUrn.from_string(MEDIA_FILE_PATH_ARRAY).is_any_file_path()
    # Non-file-path types
    assert not MediaUrn.from_string(MEDIA_STRING).is_any_file_path()
    assert not MediaUrn.from_string(MEDIA_STRING_LIST).is_any_file_path()


# TEST555: with_tag adds a tag and without_tag removes it
def test_555_with_tag_and_without_tag():
    urn = MediaUrn.from_string("media:string")
    with_ext = urn.with_tag("ext", "pdf")
    assert with_ext.extension() == "pdf"
    # Original unchanged
    assert urn.extension() is None

    # Remove the tag
    without_ext = with_ext.without_tag("ext")
    assert without_ext.extension() is None
    # Removing non-existent tag is a no-op
    same = urn.without_tag("nonexistent")
    assert same == urn


# TEST556: image_media_urn_for_ext creates valid image media URN
def test_556_image_media_urn_for_ext():
    jpg_urn_str = image_media_urn_for_ext("jpg")
    parsed = MediaUrn.from_string(jpg_urn_str)
    assert parsed.is_image(), "image helper must set image tag"
    assert parsed.is_binary(), "image helper must produce binary (non-textable) URN"
    assert parsed.extension() == "jpg"


# TEST557: audio_media_urn_for_ext creates valid audio media URN
def test_557_audio_media_urn_for_ext():
    mp3_urn_str = audio_media_urn_for_ext("mp3")
    parsed = MediaUrn.from_string(mp3_urn_str)
    assert parsed.is_audio(), "audio helper must set audio tag"
    assert parsed.is_binary(), "audio helper must produce binary (non-textable) URN"
    assert parsed.extension() == "mp3"


# TEST558: predicates are consistent with constants — every constant triggers exactly the expected predicates
def test_558_predicate_constant_consistency():
    # MEDIA_INTEGER must be numeric, text, scalar, NOT binary/bool/image/audio/video
    int_urn = MediaUrn.from_string(MEDIA_INTEGER)
    assert int_urn.is_numeric()
    assert int_urn.is_text()
    assert int_urn.is_scalar()
    assert not int_urn.is_binary()
    assert not int_urn.is_bool()
    assert not int_urn.is_image()
    assert not int_urn.is_list()

    # MEDIA_BOOLEAN must be bool, text, scalar, NOT numeric
    bool_urn = MediaUrn.from_string(MEDIA_BOOLEAN)
    assert bool_urn.is_bool()
    assert bool_urn.is_text()
    assert bool_urn.is_scalar()
    assert not bool_urn.is_numeric()

    # MEDIA_JSON must be json, text, record, scalar (single object), NOT binary
    json_urn = MediaUrn.from_string(MEDIA_JSON)
    assert json_urn.is_json()
    assert json_urn.is_text()
    assert json_urn.is_record()
    assert json_urn.is_scalar()  # JSON object is a single value (scalar cardinality)
    assert not json_urn.is_binary()
    assert not json_urn.is_list()

    # MEDIA_VOID is void, NOT anything else
    void_urn = MediaUrn.from_string(MEDIA_VOID)
    assert void_urn.is_void()
    assert not void_urn.is_text()
    assert void_urn.is_binary()  # void has no textable tag
    assert not void_urn.is_numeric()


# TEST852: LUB of identical URNs returns the same URN
def test_852_lub_identical():
    pdf = MediaUrn.from_string("media:pdf")
    lub = MediaUrn.least_upper_bound([pdf, pdf])
    assert lub.is_equivalent(pdf)


# TEST853: LUB of URNs with no common tags returns media: (universal)
def test_853_lub_no_common_tags():
    pdf = MediaUrn.from_string("media:pdf")
    png = MediaUrn.from_string("media:png")
    lub = MediaUrn.least_upper_bound([pdf, png])
    universal = MediaUrn.from_string("media:")
    assert lub.is_equivalent(universal), \
        f"LUB of pdf and png should be media: but got {lub.to_string()}"


# TEST854: LUB keeps common tags, drops differing ones
def test_854_lub_partial_overlap():
    json_text = MediaUrn.from_string("media:json;textable")
    csv_text = MediaUrn.from_string("media:csv;textable")
    lub = MediaUrn.least_upper_bound([json_text, csv_text])
    expected = MediaUrn.from_string("media:textable")
    assert lub.is_equivalent(expected), \
        f"LUB should be media:textable but got {lub.to_string()}"


# TEST855: LUB of list and non-list drops list tag
def test_855_lub_list_vs_scalar():
    json_list = MediaUrn.from_string("media:json;list;textable")
    json_scalar = MediaUrn.from_string("media:json;textable")
    lub = MediaUrn.least_upper_bound([json_list, json_scalar])
    expected = MediaUrn.from_string("media:json;textable")
    assert lub.is_equivalent(expected), \
        f"LUB should drop list tag, got {lub.to_string()}"


# TEST856: LUB of empty input returns universal type
def test_856_lub_empty():
    lub = MediaUrn.least_upper_bound([])
    universal = MediaUrn.from_string("media:")
    assert lub.is_equivalent(universal)


# TEST857: LUB of single input returns that input
def test_857_lub_single():
    pdf = MediaUrn.from_string("media:pdf")
    lub = MediaUrn.least_upper_bound([pdf])
    assert lub.is_equivalent(pdf)


# TEST858: LUB with three+ inputs narrows correctly
def test_858_lub_three_inputs():
    a = MediaUrn.from_string("media:json;list;record;textable")
    b = MediaUrn.from_string("media:csv;list;record;textable")
    c = MediaUrn.from_string("media:ndjson;list;textable")
    lub = MediaUrn.least_upper_bound([a, b, c])
    expected = MediaUrn.from_string("media:list;textable")
    assert lub.is_equivalent(expected), \
        f"LUB should be media:list;textable but got {lub.to_string()}"


# TEST859: LUB with valued tags (non-marker) that differ
def test_859_lub_valued_tags():
    v1 = MediaUrn.from_string("media:image;format=png")
    v2 = MediaUrn.from_string("media:image;format=jpeg")
    lub = MediaUrn.least_upper_bound([v1, v2])
    expected = MediaUrn.from_string("media:image")
    assert lub.is_equivalent(expected), \
        f"LUB should drop conflicting format tag, got {lub.to_string()}"


# TEST628: Verify media URN constants all start with "media:" prefix
def test_628_media_urn_constants_format():
    assert MEDIA_STRING.startswith("media:")
    assert MEDIA_INTEGER.startswith("media:")
    assert MEDIA_OBJECT.startswith("media:")
    assert MEDIA_IDENTITY.startswith("media:")


# TEST629: Verify profile URL constants all start with capdag.com schema prefix
def test_629_profile_constants_format():
    from capdag.media.spec import PROFILE_STR, PROFILE_OBJ
    assert PROFILE_STR.startswith("https://capdag.com/schema/")
    assert PROFILE_OBJ.startswith("https://capdag.com/schema/")


# TEST1271: MEDIA_ADAPTER_SELECTION constant parses and has expected tags
def test_1271_media_adapter_selection_constant():
    from capdag.urn.media_urn import MEDIA_ADAPTER_SELECTION
    urn = MediaUrn.from_string(MEDIA_ADAPTER_SELECTION)
    assert urn.has_marker_tag("adapter-selection"), \
        f"Must have adapter-selection tag, got: {urn.to_string()}"
    assert urn.has_marker_tag("json"), \
        f"Must have json tag, got: {urn.to_string()}"
    assert urn.has_marker_tag("record"), \
        f"Must have record tag, got: {urn.to_string()}"
