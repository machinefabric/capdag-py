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
    MEDIA_DECISION,
    file_media_urn_for_ext,
    text_media_urn_for_ext,
    image_media_urn_for_ext,
    audio_media_urn_for_ext,
)


# TEST060: Test wrong prefix fails with InvalidPrefix error showing expected and actual prefix
def test_060_wrong_prefix_fails():
    with pytest.raises(MediaUrnError, match="Invalid prefix"):
        MediaUrn.from_string("cap:string")


# TEST061: REMOVED — the binary/text distinction no longer exists in the
# vocabulary (is_binary() was deleted from MediaUrn; everything is bytes).
# Encoding is now expressed by the orthogonal `enc=` tag, exercised by
# test_067 below. No replacement assertion is meaningful here.


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
    assert MediaUrn.from_string("media:enc=utf-8").is_scalar()
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
    assert MediaUrn.from_string("media:enc=utf-8").is_opaque()
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


# TEST067: Text-representability is now carried by the orthogonal `enc=` tag
# (the old `textable` marker and is_text() are gone). A media is "text" iff it
# declares an encoding. enc is orthogonal to format/numeric, so only media that
# actually carry enc= are text.
def test_067_is_text():
    # Has enc= → text-representable
    assert MediaUrn.from_string(MEDIA_STRING).get_tag("enc") is not None  # media:enc=utf-8
    assert MediaUrn.from_string(MEDIA_BOOLEAN).get_tag("enc") is not None  # media:bool;enc=utf-8
    # No enc= → not text-representable
    assert MediaUrn.from_string(MEDIA_INTEGER).get_tag("enc") is None  # media:integer;numeric
    assert MediaUrn.from_string(MEDIA_JSON).get_tag("enc") is None  # media:fmt=json;record
    assert MediaUrn.from_string(MEDIA_IDENTITY).get_tag("enc") is None  # media:
    assert MediaUrn.from_string(MEDIA_PNG).get_tag("enc") is None  # media:ext=png;image
    assert MediaUrn.from_string(MEDIA_OBJECT).get_tag("enc") is None  # media:record


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
    # Bare file with extension — no enc/fmt claim
    file_ext = file_media_urn_for_ext("dat")
    file_urn = MediaUrn.from_string(file_ext)
    assert file_urn.extension() == "dat"
    assert file_urn.get_tag("enc") is None

    # Text file with extension — carries enc=utf-8 + ext
    text_ext = text_media_urn_for_ext("txt")
    text_urn = MediaUrn.from_string(text_ext)
    assert text_urn.extension() == "txt"
    assert text_urn.get_tag("enc") == "utf-8"

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
    # A more-specific URN must conform to a less-specific URN with the
    # same tags-minus-one. media:ext=pdf carries the keyed ext tag plus
    # nothing else, so it conforms to the bare-prefix media: top URN.
    pdf_listing = MediaUrn.from_string(MEDIA_PDF)
    top_requirement = MediaUrn.from_string("media:")
    assert pdf_listing.conforms_to(top_requirement)

    # A keyed-ext text URN conforms to the same URN without the ext tag.
    md_listing = MediaUrn.from_string("media:enc=utf-8;ext=md")
    md_requirement = MediaUrn.from_string("media:enc=utf-8")
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
    # More tags = higher specificity. Use the same enc=utf-8 base and add
    # markers so each URN is a strict superset of the previous — the
    # specificity must be monotonic non-decreasing as tags accrue.
    urn1 = MediaUrn.from_string("media:enc=utf-8")
    urn2 = MediaUrn.from_string("media:enc=utf-8;numeric")
    urn3 = MediaUrn.from_string("media:enc=utf-8;list;numeric")

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
        "MEDIA_OBJECT should NOT conform to MEDIA_STRING (missing enc)"


# TEST304: Test MEDIA_AVAILABILITY_OUTPUT constant parses as valid media URN with correct tags
def test_304_media_availability_output_constant():
    urn = MediaUrn.from_string(MEDIA_AVAILABILITY_OUTPUT)
    assert urn is not None
    assert urn.get_tag("enc") == "utf-8"
    assert urn.is_record()


# TEST305: Test MEDIA_PATH_OUTPUT constant parses as valid media URN with correct tags
def test_305_media_path_output_constant():
    urn = MediaUrn.from_string(MEDIA_PATH_OUTPUT)
    assert urn is not None
    assert urn.get_tag("enc") == "utf-8"
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
    assert MediaUrn.from_string("media:mp4;video").is_video()
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


# TEST551: is_file_path returns true for the single file-path media URN,
# false for everything else. There is no "array" variant — cardinality is
# carried by is_sequence on the wire, not by URN tags.
def test_551_is_file_path():
    assert MediaUrn.from_string(MEDIA_FILE_PATH).is_file_path()
    assert not MediaUrn.from_string(MEDIA_STRING).is_file_path()
    assert not MediaUrn.from_string(MEDIA_IDENTITY).is_file_path()


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
    assert parsed.get_tag("enc") is None, "image helper must produce a non-text URN (no enc)"
    assert parsed.extension() == "jpg"


# TEST557: audio_media_urn_for_ext creates valid audio media URN
def test_557_audio_media_urn_for_ext():
    mp3_urn_str = audio_media_urn_for_ext("mp3")
    parsed = MediaUrn.from_string(mp3_urn_str)
    assert parsed.is_audio(), "audio helper must set audio tag"
    assert parsed.get_tag("enc") is None, "audio helper must produce a non-text URN (no enc)"
    assert parsed.extension() == "mp3"


# TEST558: predicates are consistent with constants — every constant triggers exactly the expected predicates
def test_558_predicate_constant_consistency():
    # MEDIA_INTEGER is numeric, scalar, NOT encoded(text)/bool/image/list.
    # Integers are pure numbers — no enc= tag (encoding is orthogonal).
    int_urn = MediaUrn.from_string(MEDIA_INTEGER)
    assert int_urn.is_numeric()
    assert int_urn.get_tag("enc") is None
    assert int_urn.is_scalar()
    assert not int_urn.is_bool()
    assert not int_urn.is_image()
    assert not int_urn.is_list()

    # MEDIA_BOOLEAN is bool, encoded(text), scalar, NOT numeric
    bool_urn = MediaUrn.from_string(MEDIA_BOOLEAN)
    assert bool_urn.is_bool()
    assert bool_urn.get_tag("enc") == "utf-8"
    assert bool_urn.is_scalar()
    assert not bool_urn.is_numeric()

    # MEDIA_JSON is json, record, scalar (single object), NOT list.
    # JSON declares its format via fmt=json and carries no enc= tag.
    json_urn = MediaUrn.from_string(MEDIA_JSON)
    assert json_urn.is_json()
    assert json_urn.get_tag("enc") is None
    assert json_urn.is_record()
    assert json_urn.is_scalar()  # JSON object is a single value (scalar cardinality)
    assert not json_urn.is_list()

    # MEDIA_VOID is void, NOT anything else
    void_urn = MediaUrn.from_string(MEDIA_VOID)
    assert void_urn.is_void()
    assert void_urn.get_tag("enc") is None
    assert not void_urn.is_numeric()


# TEST852: LUB of identical URNs returns the same URN
def test_852_lub_identical():
    pdf = MediaUrn.from_string("media:pdf")
    lub = MediaUrn.least_upper_bound([pdf, pdf])
    assert lub.is_equivalent(pdf)


# TEST853: LUB of URNs with no common tags returns media: (universal)
def test_853_lub_no_common_tags():
    pdf = MediaUrn.from_string("media:pdf")
    png = MediaUrn.from_string("media:image;png")
    lub = MediaUrn.least_upper_bound([pdf, png])
    universal = MediaUrn.from_string("media:")
    assert lub.is_equivalent(universal), \
        f"LUB of pdf and png should be media: but got {lub.to_string()}"


# TEST854: LUB keeps common tags, drops differing ones. Two text values with
# differing serialization formats share their encoding but not their fmt.
def test_854_lub_partial_overlap():
    json_text = MediaUrn.from_string("media:enc=utf-8;fmt=json")
    csv_text = MediaUrn.from_string("media:enc=utf-8;fmt=csv")
    lub = MediaUrn.least_upper_bound([json_text, csv_text])
    expected = MediaUrn.from_string("media:enc=utf-8")
    assert lub.is_equivalent(expected), \
        f"LUB should be media:enc=utf-8 but got {lub.to_string()}"


# TEST855: LUB of list and non-list drops list tag
def test_855_lub_list_vs_scalar():
    json_list = MediaUrn.from_string("media:fmt=json;list")
    json_scalar = MediaUrn.from_string("media:fmt=json")
    lub = MediaUrn.least_upper_bound([json_list, json_scalar])
    expected = MediaUrn.from_string("media:fmt=json")
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
    a = MediaUrn.from_string("media:fmt=json;list;record")
    b = MediaUrn.from_string("media:fmt=csv;list;record")
    c = MediaUrn.from_string("media:fmt=ndjson;list")
    lub = MediaUrn.least_upper_bound([a, b, c])
    expected = MediaUrn.from_string("media:list")
    assert lub.is_equivalent(expected), \
        f"LUB should be media:list but got {lub.to_string()}"


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
    assert urn.is_json(), \
        f"Must declare fmt=json, got: {urn.to_string()}"
    assert urn.has_marker_tag("record"), \
        f"Must have record tag, got: {urn.to_string()}"


# TEST1810: media:void is atomic — refinements are parse errors.
#
# Mirrored across every language port (Rust, Go, Python, Swift/ObjC,
# JS) under the SAME number. Any divergence is a wire-level
# inconsistency — the unit type's atomicity is part of the protocol's
# deepest layer, not a per-port detail.
def test_1810_media_void_is_atomic():
    # Bare void: must parse successfully.
    bare = MediaUrn.from_string("media:void")
    assert bare.is_void()

    bad_inputs = [
        "media:void;text",
        "media:pdf;void",
        "media:void;audio",
        "media:void;reason=warmup",
        "media:void;heartbeat",
        "media:void;manual",
        # Order must not matter — the parser canonicalizes tags.
        "media:warmup;void",
        "media:reason=foo;void",
    ]
    for s in bad_inputs:
        with pytest.raises(MediaUrnError, match="atomic"):
            MediaUrn.from_string(s)
