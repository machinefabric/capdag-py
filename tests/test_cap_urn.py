"""Tests for CapUrn - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import hashlib
from capdag import (
    CapUrn,
    CapUrnError,
    CapUrnBuilder,
    CapMatcher,
    CapKind,
    MediaUrn,
    MEDIA_VOID,
    MEDIA_OBJECT,
    MEDIA_STRING,
    MEDIA_INTEGER,
    MEDIA_IDENTITY,
    CAP_IDENTITY,
)
from capdag.urn.cap_urn import CapEffect


def _test_urn(tags_part: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags_part}'


# TEST1: Test that cap URN is created with tags parsed correctly and direction specs accessible
def test_001_cap_urn_creation():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf;target=thumbnail"))
    assert cap.has_marker_tag("generate")
    assert cap.get_tag("target") == "thumbnail"
    assert cap.get_tag("ext") == "pdf"
    # Direction specs are required and accessible
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == MEDIA_OBJECT


# TEST2: Test that missing 'in' or 'out' defaults to media: wildcard
def test_002_direction_specs_default_to_wildcard():
    # Missing 'in' defaults to media:
    cap = CapUrn.from_string(f'cap:out="{MEDIA_OBJECT}";test')
    assert cap.in_spec() == "media:"
    assert cap.out_spec() == MEDIA_OBJECT

    # Missing 'out' defaults to media:
    cap = CapUrn.from_string(f'cap:in="{MEDIA_VOID}";test')
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == "media:"

    # Both present should succeed
    cap = CapUrn.from_string(f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";test')
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == MEDIA_OBJECT


# TEST3: Test that direction specs must match exactly, different in/out types don't match, wildcard matches any
def test_003_direction_matching():
    in_str = "media:enc=utf-8"  # MEDIA_STRING
    out_obj = "media:record"  # MEDIA_OBJECT
    in_bin = "media:"  # MEDIA_IDENTITY
    out_int = "media:integer;numeric"  # MEDIA_INTEGER

    # Direction specs must match for caps to match
    cap1 = CapUrn.from_string(f'cap:in="{in_str}";test;out="{out_obj}"')
    cap2 = CapUrn.from_string(f'cap:in="{in_str}";test;out="{out_obj}"')
    assert cap1.accepts(cap2)

    # Different in_urn should not match
    cap3 = CapUrn.from_string(f'cap:in="{in_bin}";test;out="{out_obj}"')
    assert not cap1.accepts(cap3)

    # Different out_urn should not match
    cap4 = CapUrn.from_string(f'cap:in="{in_str}";test;out="{out_int}"')
    assert not cap1.accepts(cap4)

    # Wildcard in=* direction: cap5 has media: for in, specific for out
    cap5 = CapUrn.from_string(f'cap:in=*;test;out="{out_obj}"')
    # cap1 (specific in) as pattern rejects cap5 (bare media: in) — specific pattern doesn't accept broad instance
    assert not cap1.accepts(cap5)
    # cap5 (wildcard in) as pattern accepts cap1 (specific in) — wildcard pattern accepts anything
    assert cap5.accepts(cap1)


# TEST4: Test that unquoted keys and values are normalized to lowercase
def test_004_unquoted_values_lowercased():
    # Mixed-case keyed tags + a marker. Both keys and unquoted values
    # are lowercased on parse.
    cap = CapUrn.from_string(_test_urn("Generate;EXT=PDF;Target=Thumbnail"))

    assert cap.has_marker_tag("generate")
    assert cap.get_tag("ext") == "pdf"
    assert cap.get_tag("target") == "thumbnail"

    # Key lookup is case-insensitive: uppercase variants of an
    # existing key resolve to the same keyed tag.
    assert cap.get_tag("EXT") == "pdf"
    assert cap.get_tag("Ext") == "pdf"

    # Both URNs parse to same canonical form (same tags, same values).
    cap2 = CapUrn.from_string(_test_urn("generate;ext=pdf;target=thumbnail"))
    assert cap.to_string() == cap2.to_string()
    assert cap == cap2


# TEST5: Test that quoted values preserve case while unquoted are lowercased
def test_005_quoted_values_preserve_case():
    # Quoted values preserve their case
    cap = CapUrn.from_string(_test_urn(r'key="Value With Spaces"'))
    assert cap.get_tag("key") == "Value With Spaces"

    # Key is still lowercase
    cap2 = CapUrn.from_string(_test_urn(r'KEY="Value With Spaces"'))
    assert cap2.get_tag("key") == "Value With Spaces"

    # Unquoted vs quoted case difference
    unquoted = CapUrn.from_string(_test_urn("key=UPPERCASE"))
    quoted = CapUrn.from_string(_test_urn(r'key="UPPERCASE"'))
    assert unquoted.get_tag("key") == "uppercase"  # lowercase
    assert quoted.get_tag("key") == "UPPERCASE"  # preserved
    assert unquoted != quoted  # NOT equal


# TEST6: Test that quoted values can contain special characters (semicolons, equals, spaces)
def test_006_quoted_value_special_chars():
    # Semicolons in quoted values
    cap = CapUrn.from_string(_test_urn(r'key="value;with;semicolons"'))
    assert cap.get_tag("key") == "value;with;semicolons"

    # Equals in quoted values
    cap2 = CapUrn.from_string(_test_urn(r'key="value=with=equals"'))
    assert cap2.get_tag("key") == "value=with=equals"

    # Spaces in quoted values
    cap3 = CapUrn.from_string(_test_urn(r'key="hello world"'))
    assert cap3.get_tag("key") == "hello world"


# TEST7: Test that escape sequences in quoted values (\" and \\) are parsed correctly
def test_007_quoted_value_escape_sequences():
    # Escaped quotes
    cap = CapUrn.from_string(_test_urn(r'key="value\"quoted\""'))
    assert cap.get_tag("key") == r'value"quoted"'

    # Escaped backslashes
    cap2 = CapUrn.from_string(_test_urn(r'key="path\\file"'))
    assert cap2.get_tag("key") == r'path\file'

    # Mixed escapes
    cap3 = CapUrn.from_string(_test_urn(r'key="say \"hello\\world\""'))
    assert cap3.get_tag("key") == r'say "hello\world"'


# TEST8: Test that mixed quoted and unquoted values in same URN parse correctly
def test_008_mixed_quoted_unquoted():
    cap = CapUrn.from_string(_test_urn(r'a="Quoted";b=simple'))
    assert cap.get_tag("a") == "Quoted"
    assert cap.get_tag("b") == "simple"


# TEST9: Test that unterminated quote produces UnterminatedQuote error
def test_009_unterminated_quote_error():
    with pytest.raises(CapUrnError, match="Unterminated quote"):
        CapUrn.from_string(_test_urn(r'key="unterminated'))


# TEST10: Test that invalid escape sequences (like \n, \x) produce InvalidEscapeSequence error
def test_010_invalid_escape_sequence_error():
    with pytest.raises(CapUrnError, match="Invalid escape sequence"):
        CapUrn.from_string(_test_urn(r'key="bad\n"'))

    # Invalid escape at end
    with pytest.raises(CapUrnError, match="Invalid escape sequence"):
        CapUrn.from_string(_test_urn(r'key="bad\x"'))


# TEST11: Test that serialization uses smart quoting (no quotes for simple lowercase, quotes for special chars/uppercase)
def test_011_serialization_smart_quoting():
    # Simple lowercase value - no quoting needed
    cap = CapUrnBuilder().in_spec(MEDIA_VOID).out_spec(MEDIA_OBJECT).tag("key", "simple").build()
    # The serialized form should contain key=simple (unquoted)
    s = cap.to_string()
    assert "key=simple" in s

    # Value with spaces - needs quoting
    cap2 = CapUrnBuilder().in_spec(MEDIA_VOID).out_spec(MEDIA_OBJECT).tag("key", "has spaces").build()
    s2 = cap2.to_string()
    assert r'key="has spaces"' in s2

    # Value with uppercase - needs quoting to preserve
    cap4 = CapUrnBuilder().in_spec(MEDIA_VOID).out_spec(MEDIA_OBJECT).tag("key", "HasUpper").build()
    s4 = cap4.to_string()
    assert r'key="HasUpper"' in s4


# TEST12: Test that simple cap URN round-trips (parse -> serialize -> parse equals original)
def test_012_round_trip_simple():
    original = _test_urn("generate;ext=pdf")
    cap = CapUrn.from_string(original)
    serialized = cap.to_string()
    reparsed = CapUrn.from_string(serialized)
    assert cap == reparsed


# TEST13: Test that quoted values round-trip preserving case and spaces
def test_013_round_trip_quoted():
    original = _test_urn(r'key="Value With Spaces"')
    cap = CapUrn.from_string(original)
    serialized = cap.to_string()
    reparsed = CapUrn.from_string(serialized)
    assert cap == reparsed
    assert reparsed.get_tag("key") == "Value With Spaces"


# TEST14: Test that escape sequences round-trip correctly
def test_014_round_trip_escapes():
    original = _test_urn(r'key="value\"with\\escapes"')
    cap = CapUrn.from_string(original)
    assert cap.get_tag("key") == r'value"with\escapes'
    serialized = cap.to_string()
    reparsed = CapUrn.from_string(serialized)
    assert cap == reparsed


# TEST15: Test that cap: prefix is required and case-insensitive
def test_015_cap_prefix_required():
    # Missing cap: prefix should fail
    with pytest.raises(CapUrnError):
        CapUrn.from_string(f'in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";generate')

    # Valid cap: prefix should work
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap.has_marker_tag("generate")

    # Case-insensitive prefix
    cap2 = CapUrn.from_string(f'CAP:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";generate')
    assert cap2.has_marker_tag("generate")


# TEST16: Test that trailing semicolon is equivalent (same hash, same string, matches)
def test_016_trailing_semicolon_equivalence():
    # Both with and without trailing semicolon should be equivalent
    cap1 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    cap2 = CapUrn.from_string(_test_urn("generate;ext=pdf") + ";")

    # They should be equal
    assert cap1 == cap2

    # They should have same hash
    assert hash(cap1) == hash(cap2)

    # They should have same string representation (canonical form)
    assert cap1.to_string() == cap2.to_string()

    # They should accept each other
    assert cap1.accepts(cap2)
    assert cap2.accepts(cap1)


# TEST939: The canonical form drops `in=media:` and `out=media:` segments. Every spelling of "the same cap with wildcard in/out" collapses to one byte-identical canonical string. This is the contract that makes registry lookups work: the cap-publisher hashes `<canonical-urn>` to compute the cache key, and every language port (Rust, Go, Python, JS, ObjC) must agree on the canonical form for cross-language lookups to land on the same key. A regression that emitted the wildcard segments would silently move the published cap to a different SHA-256 bucket, 404'ing every reader that hashes the canonical form.
def test_939_cap_urn_canonical_form_drops_wildcard_in_out():
    canonical = "cap:decimate-sequence"
    variants = [
        "cap:decimate-sequence",
        "cap:decimate-sequence;in=media:;out=media:",
        "cap:in=media:;out=media:;decimate-sequence",
        "cap:in=media:;decimate-sequence;out=media:",
    ]
    for v in variants:
        parsed = CapUrn.from_string(v)
        assert parsed.to_string() == canonical, (
            f"input {v!r} canonicalized to {parsed.to_string()!r}, "
            f"expected {canonical!r} — wildcard in/out segments must be "
            f"elided so the registry SHA-256 key is stable across input "
            f"spellings"
        )
    # Explicit identity round-trip.
    identity = CapUrn.from_string("cap:effect=none")
    assert identity.to_string() == "cap:effect=none"


# TEST17: Test tag matching: exact match, subset match, wildcard match, value mismatch
def test_017_tag_matching():
    # Exact match
    cap1 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    cap2 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap1.accepts(cap2)

    # cap1(generate,ext) as pattern rejects cap3(generate) missing ext
    cap3 = CapUrn.from_string(_test_urn("generate"))  # Missing ext tag
    assert not cap1.accepts(cap3), "Pattern rejects instance missing required tag"
    # Routing: cap3(generate) accepts cap1(generate,ext) — instance has the
    # `generate` marker; pattern is silent on `ext` (no constraint) so the
    # extra ext on the instance does not disqualify the match.
    assert cap3.accepts(cap1), "cap3 missing ext is wildcard, accepts cap1 with ext"

    # Pattern with `ext=*` (must-have-any) accepts an instance whose
    # `ext` is exactly `pdf` — any value satisfies must-have-any.
    cap4 = CapUrn.from_string(_test_urn("generate;ext=*"))
    assert cap4.accepts(cap1)

    # Value mismatch on `ext` — pattern requires pdf, instance has docx.
    cap5 = CapUrn.from_string(_test_urn("generate;ext=docx"))
    assert not cap1.accepts(cap5)


# TEST18: Test that quoted values with different case do NOT match (case-sensitive)
def test_018_quoted_values_case_sensitive():
    cap1 = CapUrn.from_string(_test_urn(r'key="CaseSensitive"'))
    cap2 = CapUrn.from_string(_test_urn(r'key="casesensitive"'))
    assert not cap1.accepts(cap2)


# TEST19: Missing tag in instance causes rejection — pattern's tags are constraints
def test_019_missing_tag_handling():
    cap = CapUrn.from_string(_test_urn("generate"))
    request1 = CapUrn.from_string(_test_urn("ext=pdf"))

    # cap(op) as pattern: instance(ext) missing op -> reject
    assert not cap.accepts(request1)
    # request(ext) as pattern: instance(cap) missing ext -> reject
    assert not request1.accepts(cap)

    # Routing: request(op) accepts cap(op,ext) — instance has op -> match
    cap2 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    request2 = CapUrn.from_string(_test_urn("generate"))
    assert request2.accepts(cap2)
    # Reverse: cap(op,ext) as pattern rejects request missing ext
    assert not cap2.accepts(request2)


# TEST020: Specificity is the sum of per-tag truth-table scores
# across in/out/y. Marker tags (bare segments and `key=*`) score 2
# (must-have-any), exact `key=value` tags score 3, missing/`?` score
# 0, `!` scores 1.
def test_020_specificity_calculation():
    # Cap-URN spec is 10000*spec_U(out) + 100*spec_U(in) + spec_U(y),
    # so out-axis differences dominate, then in, then y.
    cap1 = CapUrn.from_string("cap:in=media:string;out=media:object;test")
    cap2 = CapUrn.from_string('cap:in="media:enc=utf-8";out="media:enc=utf-8;record";test')
    # cap1: out=object(2 marker), in=string(2), y=test(2)
    # cap2: out=enc=utf-8(3 exact)+record(2 marker), in=enc=utf-8(3), y=test(2)
    assert cap2.specificity() > cap1.specificity()

    # Tightening `*` to an exact value strictly increases the y-axis
    # score (must-have-any 2 → must-have-this-value 4).
    cap3 = CapUrn.from_string(_test_urn("generate;ext=*"))
    cap4 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap4.specificity() > cap3.specificity()


# TEST21: Test builder creates cap URN with correct tags and direction specs
def test_021_builder_creates_cap_urn():
    cap = (
        CapUrnBuilder()
        .in_spec(MEDIA_VOID)
        .out_spec(MEDIA_OBJECT)
        .marker("generate")
        .tag("ext", "pdf")
        .build()
    )
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == MEDIA_OBJECT
    assert cap.has_marker_tag("generate")
    assert cap.get_tag("ext") == "pdf"


# TEST22: Test builder requires both in_spec and out_spec
def test_022_builder_requires_direction_specs():
    # Missing in_spec
    with pytest.raises(CapUrnError, match="Missing required 'in' spec"):
        CapUrnBuilder().out_spec(MEDIA_OBJECT).tag("op", "test").build()

    # Missing out_spec
    with pytest.raises(CapUrnError, match="Missing required 'out' spec"):
        CapUrnBuilder().in_spec(MEDIA_VOID).tag("op", "test").build()

    # Both present should work
    cap = CapUrnBuilder().in_spec(MEDIA_VOID).out_spec(MEDIA_OBJECT).tag("op", "test").build()
    assert cap is not None


# TEST23: Test builder lowercases keys but preserves value case
def test_023_builder_preserves_case():
    cap = (
        CapUrnBuilder()
        .in_spec(MEDIA_VOID)
        .out_spec(MEDIA_OBJECT)
        .tag("OP", "Generate")  # Key uppercase, quoted value preserves case
        .build()
    )
    # Key is normalized to lowercase; case-insensitive lookup resolves
    # to the same keyed tag.
    assert cap.get_tag("op") == "Generate"
    assert cap.get_tag("OP") == "Generate"
    # Quoted values preserve case exactly.
    assert cap.has_tag("op", "Generate")


# TEST24: Directional accepts — pattern's tags are constraints, instance must satisfy
def test_024_directional_accepts():
    cap1 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    cap2 = CapUrn.from_string(_test_urn("generate;format=*"))
    cap3 = CapUrn.from_string(_test_urn("type=image;extract"))

    # cap1(op,ext) as pattern: cap2 missing ext -> reject
    assert not cap1.accepts(cap2)
    # cap2(op,format) as pattern: cap1 missing format -> reject
    assert not cap2.accepts(cap1)
    # op mismatch: neither direction accepts
    assert not cap1.accepts(cap3)
    assert not cap3.accepts(cap1)

    # Routing: general request(op) accepts specific cap(op,ext) — instance has op
    cap4 = CapUrn.from_string(_test_urn("generate"))
    assert cap4.accepts(cap1)
    # Reverse: specific cap(op,ext) rejects general request missing ext
    assert not cap1.accepts(cap4)

    # Different direction specs: cap1 has in=media:void (specific), cap5 has in=media: (wildcard)
    cap5 = CapUrn.from_string(f'cap:in="media:";generate;out="{MEDIA_OBJECT}"')
    # cap1 (in=media:void) cannot accept cap5 (in=media:) - specific doesn't accept wildcard
    assert not cap1.accepts(cap5)
    # cap5 (in=media:) CAN accept cap1 (in=media:void) - wildcard accepts specific
    assert cap5.accepts(cap1)


# TEST25: Test find_best_match returns most specific matching cap
def test_025_find_best_match():
    # Two patterns of differing specificity. The more general pattern
    # (just `generate`) and the more specific pattern (with `ext=pdf`)
    # both accept a request that has both tags.
    caps = [
        CapUrn.from_string(_test_urn("generate")),               # Generic
        CapUrn.from_string(_test_urn("generate;ext=pdf")),       # Specific
    ]
    request = CapUrn.from_string(_test_urn("generate;ext=pdf"))

    # Both patterns accept; the second is the more specific provider.
    matching = [c for c in caps if c.accepts(request)]
    assert len(matching) == 2
    best = max(matching, key=lambda c: c.specificity())
    assert best == caps[1]


# TEST26: Test merge combines tags from both caps, subset keeps only specified tags
def test_026_merge_and_subset():
    cap1 = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    cap2 = CapUrn.from_string(_test_urn("convert;target=thumbnail"))

    # Merge: cap2 takes precedence on overlapping keys; non-overlapping
    # tags from both sides survive.
    merged = cap1.merge(cap2)
    assert merged.has_marker_tag("convert")
    assert merged.has_marker_tag("generate")
    assert merged.get_tag("ext") == "pdf"
    assert merged.get_tag("target") == "thumbnail"

    # Subset by key list keeps only the named keys.
    subset = cap1.subset(["generate"])
    assert subset.has_marker_tag("generate")
    assert subset.get_tag("ext") is None  # Dropped from subset


# TEST27: Test with_wildcard_tag sets tag to wildcard, including in/out
def test_027_with_wildcard_tag():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf"))

    # Wildcard a regular tag
    cap2 = cap.with_wildcard_tag("ext")
    assert cap2.get_tag("ext") == "*"

    # Wildcard in direction resolves to the top media URN.
    cap3 = cap.with_wildcard_tag("in")
    assert cap3.in_spec() == "media:"

    # Wildcard out direction resolves to the top media URN.
    cap4 = cap.with_wildcard_tag("out")
    assert cap4.out_spec() == "media:"


# TEST28: Test empty cap URN is illegal after effect transition
def test_28_empty_cap_urn_is_illegal():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:")


# TEST29: Test minimal valid cap URN has just in and out, empty tags
def test_029_minimal_valid_cap_urn():
    cap = CapUrn.from_string(f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}"')
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == MEDIA_OBJECT
    assert len(cap.tags) == 0


# TEST30: Test extended characters (forward slashes, colons) in tag values
def test_030_extended_characters_in_values():
    cap = CapUrn.from_string(_test_urn("path=path/to/file;url=http://example.com"))
    assert cap.get_tag("path") == "path/to/file"
    assert cap.get_tag("url") == "http://example.com"


# TEST31: Test wildcard rejected in keys but accepted in values
def test_031_wildcard_in_keys_and_values():
    # Bare key parses as a marker (must-have-any) — value is "*".
    cap = CapUrn.from_string(_test_urn("op"))
    assert cap.has_marker_tag("op")
    assert cap.get_tag("op") == "*"

    # Wildcard in key should fail (handled by tagged-urn)
    with pytest.raises(CapUrnError):
        CapUrn.from_string(_test_urn("*=value"))


# TEST32: Test duplicate keys are rejected with DuplicateKey error
def test_032_duplicate_keys_rejected():
    with pytest.raises(CapUrnError, match="Duplicate"):
        # `op` repeats with a value the second time — duplicate key.
        CapUrn.from_string(_test_urn("op;op=convert"))


# TEST33: Test pure numeric keys rejected, mixed alphanumeric allowed, numeric values allowed
def test_033_numeric_keys():
    # Pure numeric key should fail (handled by tagged-urn)
    with pytest.raises(CapUrnError, match="numeric"):
        CapUrn.from_string(_test_urn("123=value"))

    # Mixed alphanumeric key is allowed
    cap = CapUrn.from_string(_test_urn("key123=value"))
    assert cap.get_tag("key123") == "value"

    # Numeric value is allowed
    cap2 = CapUrn.from_string(_test_urn("key=123"))
    assert cap2.get_tag("key") == "123"


# TEST34: Test empty values are rejected
def test_034_empty_values_rejected():
    # Empty value in builder
    with pytest.raises(CapUrnError, match="Empty value"):
        CapUrnBuilder().in_spec(MEDIA_VOID).out_spec(MEDIA_OBJECT).tag("key", "").build()


# TEST35: Test has_tag is case-sensitive for values, case-insensitive for keys, works for in/out
def test_035_has_tag_behavior():
    cap = CapUrn.from_string(_test_urn(r'key="Value"'))

    # Key is case-insensitive
    assert cap.has_tag("key", "Value")
    assert cap.has_tag("KEY", "Value")
    assert cap.has_tag("Key", "Value")

    # Value is case-sensitive
    assert cap.has_tag("key", "Value")
    assert not cap.has_tag("key", "value")
    assert not cap.has_tag("key", "VALUE")

    # Works for in/out
    assert cap.has_tag("in", MEDIA_VOID)
    assert cap.has_tag("out", MEDIA_OBJECT)


# TEST36: Test with_tag preserves value case
def test_036_with_tag_preserves_case():
    cap = CapUrn.from_string(_test_urn("generate"))
    cap2 = cap.with_tag("key", "MixedCase")
    assert cap2.get_tag("key") == "MixedCase"


# TEST37: Test with_tag rejects empty value
def test_037_with_tag_rejects_empty():
    cap = CapUrn.from_string(_test_urn("generate"))
    with pytest.raises(CapUrnError, match="Empty value"):
        cap.with_tag("key", "")


# TEST38: Test semantic equivalence of unquoted and quoted simple lowercase values
def test_038_semantic_equivalence_quoted_unquoted():
    cap1 = CapUrn.from_string(_test_urn("key=simple"))
    cap2 = CapUrn.from_string(_test_urn(r'key="simple"'))
    # Both should have the same value
    assert cap1.get_tag("key") == cap2.get_tag("key")
    assert cap1 == cap2


# TEST39: Test get_tag returns direction specs (in/out) with case-insensitive lookup
def test_039_get_tag_direction_specs():
    cap = CapUrn.from_string(_test_urn("generate"))

    # get_tag works for in/out
    assert cap.get_tag("in") == MEDIA_VOID
    assert cap.get_tag("out") == MEDIA_OBJECT

    # Case-insensitive
    assert cap.get_tag("IN") == MEDIA_VOID
    assert cap.get_tag("OUT") == MEDIA_OBJECT
    assert cap.get_tag("In") == MEDIA_VOID
    assert cap.get_tag("Out") == MEDIA_OBJECT

    # Also accessible via methods
    assert cap.in_spec() == MEDIA_VOID
    assert cap.out_spec() == MEDIA_OBJECT


# ============================================================================
# Matching Semantics Tests
# ============================================================================


# TEST40: Matching semantics - exact match succeeds
def test_040_matching_semantics_exact_match():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    request = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap.accepts(request), "Test 1: Exact match should succeed"


# TEST41: Matching semantics - cap missing tag matches (implicit wildcard)
def test_041_matching_semantics_cap_missing_tag():
    cap = CapUrn.from_string(_test_urn("generate"))
    request = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap.accepts(request), "Test 2: Cap missing tag should accept (implicit wildcard)"


# TEST42: Pattern rejects instance missing required tags
def test_042_matching_semantics_cap_has_extra_tag():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf;version=2"))
    request = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    # cap(op,ext,version) as pattern rejects request missing version
    assert not cap.accepts(request), "Pattern rejects instance missing required tag"
    # Routing: request(op,ext) accepts cap(op,ext,version) — instance has all request needs
    assert request.accepts(cap), "Request pattern satisfied by more-specific cap"


# TEST43: Matching semantics - request wildcard matches specific cap value
def test_043_matching_semantics_request_has_wildcard():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    request = CapUrn.from_string(_test_urn("generate;ext=*"))
    assert cap.accepts(request), "Test 4: Request wildcard should be accepted"


# TEST44: Matching semantics - cap wildcard matches specific request value
def test_044_matching_semantics_cap_has_wildcard():
    cap = CapUrn.from_string(_test_urn("generate;ext=*"))
    request = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    assert cap.accepts(request), "Test 5: Cap wildcard should accept"


# TEST45: Matching semantics - value mismatch does not match
def test_045_matching_semantics_value_mismatch():
    cap = CapUrn.from_string(_test_urn("generate;ext=pdf"))
    request = CapUrn.from_string(_test_urn("generate;ext=docx"))
    assert not cap.accepts(request), "Test 6: Value mismatch should not accept"


# TEST46: Matching semantics - fallback pattern (cap missing tag = implicit wildcard)
def test_046_matching_semantics_fallback_pattern():
    in_bin = "media:"
    cap = CapUrn.from_string(f'cap:in="{in_bin}";generate-thumbnail;out="{in_bin}"')
    request = CapUrn.from_string(f'cap:ext=wav;in="{in_bin}";generate-thumbnail;out="{in_bin}"')
    assert cap.accepts(request), "Test 7: Fallback pattern should accept (cap missing ext = implicit wildcard)"


# TEST47: Matching semantics - thumbnail fallback with void input
def test_047_matching_semantics_thumbnail_void_input():
    out_bin = "media:"
    cap = CapUrn.from_string(f'cap:in="{MEDIA_VOID}";generate-thumbnail;out="{out_bin}"')
    request = CapUrn.from_string(f'cap:ext=wav;in="{MEDIA_VOID}";generate-thumbnail;out="{out_bin}"')
    assert cap.accepts(request), "Test 7b: Thumbnail fallback with void input should accept"


# TEST6203: Matching semantics - generic legal wildcard cap matches specific caps
def test_6203_matching_semantics_wildcard_direction():
    cap = CapUrn.from_string("cap:generate")
    request = CapUrn.from_string(f'cap:ext=pdf;in="media:enc=utf-8";generate;out="{MEDIA_OBJECT}"')
    assert cap.accepts(request), "Test 8: Wildcard direction should accept any direction"


# TEST49: Non-overlapping tags — neither direction accepts
def test_049_matching_semantics_cross_dimension():
    cap = CapUrn.from_string(_test_urn("generate"))
    request = CapUrn.from_string(_test_urn("ext=pdf"))
    # cap(op) rejects request missing op; request(ext) rejects cap missing ext
    assert not cap.accepts(request), "Pattern rejects instance missing required tag"
    assert not request.accepts(cap), "Reverse also rejects — non-overlapping tags"


# TEST48: Matching semantics - wildcard direction matches anything
def test_048_matching_semantics_direction_mismatch():
    # media:enc=utf-8 (text) has different tags than media: (wildcard)
    # Neither can provide input for the other (completely different marker tags)
    cap = CapUrn.from_string(f'cap:in="media:enc=utf-8";generate;out="{MEDIA_OBJECT}"')
    request = CapUrn.from_string(f'cap:in="media:";generate;out="{MEDIA_OBJECT}"')
    assert not cap.accepts(request), "Test 10: Direction mismatch should not accept"


# TEST50: Matching semantics - direction mismatch prevents matching
def test_050_matching_semantics_test10_direction_mismatch():
    # Test 10: Direction mismatch prevents matching
    # media:string has tags {enc=utf-8, form:scalar}, media: has no tags (wildcard)
    # Neither can provide input for the other (completely different marker tags)
    cap = CapUrn.from_string(f'cap:in=media:string;generate;out="{MEDIA_OBJECT}"')
    request = CapUrn.from_string(f'cap:in=media:;generate;out="{MEDIA_OBJECT}"')
    assert not cap.accepts(request), "Test 10: Direction mismatch should not match"


# =============================================================================
# Tier Tests (TEST559-TEST567)
# =============================================================================


# TEST559: without_tag removes tag, rejects structural keys, case-insensitive for keys
def test_559_without_tag():
    cap = CapUrn.from_string(
        'cap:in="media:void";test;ext=pdf;out="media:void"'
    )
    removed = cap.without_tag("ext")
    assert removed.get_tag("ext") is None
    assert removed.has_marker_tag("test")

    # Case-insensitive removal
    removed2 = cap.without_tag("EXT")
    assert removed2.get_tag("ext") is None

    with pytest.raises(CapUrnError):
        cap.without_tag("in")
    with pytest.raises(CapUrnError):
        cap.without_tag("out")
    with pytest.raises(CapUrnError):
        cap.without_tag("effect")

    # Removing non-existent tag is no-op
    same3 = cap.without_tag("nonexistent")
    assert same3 == cap


# TEST560: with_in_spec and with_out_spec change direction specs
def test_560_with_in_out_spec():
    cap = CapUrn.from_string(
        'cap:in="media:void";test;out="media:void"'
    )

    changed_in = cap.with_in_spec("media:")
    assert changed_in.in_spec() == "media:"
    assert changed_in.out_spec() == MEDIA_VOID
    assert changed_in.has_marker_tag("test")

    changed_out = cap.with_out_spec("media:string")
    assert changed_out.in_spec() == MEDIA_VOID
    assert changed_out.out_spec() == "media:string"

    # Chain both
    changed_both = cap.with_in_spec("media:ext=pdf").with_out_spec("media:enc=utf-8;ext=txt")
    assert changed_both.in_spec() == "media:ext=pdf"
    assert changed_both.out_spec() == "media:enc=utf-8;ext=txt"


# TEST561: in_media_urn and out_media_urn parse direction specs into MediaUrn
def test_561_in_out_media_urn():
    cap = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"'
    )

    in_urn = cap.in_media_urn()
    assert in_urn.get_tag("enc") is None  # pdf file input declares no text encoding
    assert in_urn.has_tag("ext", "pdf")

    out_urn = cap.out_media_urn()
    assert out_urn.get_tag("enc") == "utf-8"  # text output carries enc
    assert out_urn.has_tag("ext", "txt")

    # Generic legal cap still exposes top media on both axes
    wildcard_cap = CapUrn.from_string("cap:raw")
    wildcard_in = wildcard_cap.in_media_urn()
    assert wildcard_in is not None, "generic legal cap should expose a valid top MediaUrn"


# TEST562: canonical_option returns None for None input, canonical string for Some
def test_562_canonical_option():
    # None input -> None
    result = CapUrn.canonical_option(None)
    assert result is None

    # Some valid input -> canonical string
    input_str = 'cap:test;in="media:void";out="media:void"'
    result = CapUrn.canonical_option(input_str)
    assert result is not None
    original = CapUrn.from_string(input_str)
    reparsed = CapUrn.from_string(result)
    assert original == reparsed

    # Some invalid input -> error
    with pytest.raises(Exception):
        CapUrn.canonical_option("invalid")


# TEST568: is_dispatchable with different tag order in output spec
def test_568_dispatch_output_tag_order():
    provider = CapUrn.from_string(
        'cap:in="media:enc=utf-8;model-spec";download-model;out="media:download-result;enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:enc=utf-8;model-spec";download-model;out="media:download-result;enc=utf-8;record"'
    )

    # After parsing, both should be normalized to same canonical form
    assert provider.out_spec() == request.out_spec(), \
        "Output specs should be normalized to same canonical form"

    # And dispatch should work
    assert provider.is_dispatchable(request), \
        "Provider should dispatch request with same tags in different order"


# TEST563: CapMatcher::find_all_matches returns all matching caps sorted by specificity
def test_563_find_all_matches():
    caps = [
        CapUrn.from_string('cap:in="media:void";test;out="media:void"'),
        CapUrn.from_string('cap:in="media:void";test;ext=pdf;out="media:void"'),
        CapUrn.from_string('cap:in="media:void";different;out="media:void"'),
    ]

    request = CapUrn.from_string('cap:in="media:void";test;out="media:void"')
    matches = CapMatcher.find_all_matches(caps, request)

    # Should find 2 matches (test and test;ext=pdf), not different
    assert len(matches) == 2
    # Sorted by specificity descending: ext=pdf first (more specific)
    assert matches[0].specificity() >= matches[1].specificity()
    assert matches[0].get_tag("ext") == "pdf"


# TEST564: CapMatcher::are_compatible detects bidirectional overlap
def test_564_are_compatible():
    caps1 = [
        CapUrn.from_string('cap:in="media:void";test;out="media:void"'),
    ]
    caps2 = [
        CapUrn.from_string('cap:in="media:void";test;ext=pdf;out="media:void"'),
    ]
    caps3 = [
        CapUrn.from_string('cap:in="media:void";different;out="media:void"'),
    ]

    # caps1 (test) accepts caps2 (test;ext=pdf) -> compatible
    assert CapMatcher.are_compatible(caps1, caps2)

    # caps1 (test) vs caps3 (different) -> not compatible
    assert not CapMatcher.are_compatible(caps1, caps3)

    # Empty sets are not compatible
    assert not CapMatcher.are_compatible([], caps1)
    assert not CapMatcher.are_compatible(caps1, [])


# TEST565: tags_to_string returns only tags portion without prefix
def test_565_tags_to_string():
    cap = CapUrn.from_string(
        'cap:in="media:void";test;out="media:void"'
    )
    tags_str = cap.tags_to_string()
    # Should NOT start with "cap:"
    assert not tags_str.startswith("cap:")
    # Should contain in, out, op tags
    assert "test" in tags_str


# TEST566: with_tag rejects structural keys
def test_566_with_tag_ignores_in_out():
    cap = CapUrn.from_string(
        'cap:in="media:void";test;out="media:void"'
    )
    with pytest.raises(CapUrnError):
        cap.with_tag("in", "media:")
    with pytest.raises(CapUrnError):
        cap.with_tag("out", "media:")
    with pytest.raises(CapUrnError):
        cap.with_tag("effect", "none")


# TEST567: conforms_to_str and accepts_str work with string arguments
def test_567_str_variants():
    cap = CapUrn.from_string(
        'cap:in="media:void";test;out="media:void"'
    )

    # accepts_str
    assert cap.accepts_str('cap:in="media:void";test;ext=pdf;out="media:void"')
    assert not cap.accepts_str('cap:in="media:void";different;out="media:void"')

    # conforms_to_str
    assert cap.conforms_to_str('cap:in="media:void";test;out="media:void"')

    # Invalid URN string -> error
    with pytest.raises(Exception):
        cap.accepts_str("invalid")
    with pytest.raises(Exception):
        cap.conforms_to_str("invalid")


# =============================================================================
# Wildcard/Identity Tests (TEST639-TEST653)
# =============================================================================


# TEST6231: cap: (empty) is the illegal bare top form
def test_6231_wildcard_empty_cap_defaults():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:")


# TEST639: bare/default top-to-top declared form is illegal
def test_639_wildcard_001_empty_cap_is_illegal():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:")


# TEST640: cap:in defaults to the same illegal bare top form
def test_640_wildcard_in_only_defaults_out():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in")


# TEST641: cap:out defaults to the same illegal bare top form
def test_641_wildcard_out_only_defaults_in():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:out")


# TEST642: cap:in;out becomes the same illegal bare top form
def test_642_wildcard_in_out_no_values():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in;out")


# TEST643: cap:in=*;out=* is the same illegal bare top form
def test_643_wildcard_explicit_asterisk():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in=*;out=*")


# TEST644: cap:in=media:;out=* is the same illegal bare top form
def test_644_wildcard_specific_in_wildcard_out():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in=media:;out=*")


# TEST645: cap:in=*;out=media:text has wildcard in, specific out
def test_645_wildcard_in_specific_out():
    cap = CapUrn.from_string("cap:in=*;out=media:text")
    assert cap.in_spec() == "media:"
    assert cap.out_spec() == "media:text"


# TEST646: cap:in=foo fails (invalid media URN)
def test_646_wildcard_invalid_in_spec():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in=foo;out=media:")


# TEST647: cap:in=media:;out=bar fails (invalid media URN)
def test_647_wildcard_invalid_out_spec():
    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:in=media:;out=bar")


# TEST648: Wildcard in/out match specific caps
def test_648_wildcard_010_wildcard_accepts_specific():
    wildcard = CapUrn.from_string("cap:raw")
    specific = CapUrn.from_string("cap:out=media:text;raw")

    assert wildcard.accepts(specific), "Wildcard should accept specific cap"
    assert specific.conforms_to(wildcard), "Specific should conform to wildcard"


# TEST649: Specificity - wildcard has 0, specific has tag count
def test_649_wildcard_011_specificity_scoring():
    wildcard = CapUrn.from_string("cap:raw")
    specific = CapUrn.from_string("cap:out=media:text;raw")

    assert wildcard.specificity() == 2, "Marker-only wildcard cap should have y-axis specificity only"
    assert specific.specificity() > 0, "Specific cap should have non-zero specificity"


# TEST650: cap:in=media:;out=media:;test preserves other tags
def test_650_wildcard_012_preserve_other_tags():
    cap = CapUrn.from_string("cap:in=media:;out=media:;test")
    assert cap.in_spec() == "media:"
    assert cap.out_spec() == "media:"
    assert cap.has_marker_tag("test")


# TEST6614: Legal generic cap with top directions matches specific caps
def test_6614_wildcard_accepts_specific():
    wildcard = CapUrn.from_string("cap:raw")
    specific = CapUrn.from_string("cap:out=media:text;raw")

    assert wildcard.accepts(specific), "Wildcard should accept specific"
    assert specific.conforms_to(wildcard), "Specific should conform to wildcard"


# TEST6616: Specificity - generic marker-only cap has y-axis specificity only
def test_6616_wildcard_specificity_scoring():
    wildcard = CapUrn.from_string("cap:raw")
    specific = CapUrn.from_string("cap:out=media:text;raw")

    assert wildcard.specificity() == 2, "Marker-only wildcard cap should have y-axis specificity only"
    assert specific.specificity() > 0, "Specific cap should have non-zero specificity"


# TEST6617: legal top-to-top generic transform preserves other tags
def test_6617_wildcard_preserve_other_tags():
    cap = CapUrn.from_string("cap:in=media:;out=media:;test")
    assert cap.in_spec() == "media:"
    assert cap.out_spec() == "media:"
    assert cap.effect_kind() == CapEffect.DECLARED
    assert cap.has_marker_tag("test")


# TEST6619: Explicit identity forms produce the same CapUrn
def test_6619_wildcard_identity_forms_equivalent():
    forms = [
        "cap:effect=none",
        "cap:in=media:;out=media:;effect=none",
    ]

    caps = [CapUrn.from_string(f) for f in forms]
    for i in range(len(caps)):
        for j in range(i + 1, len(caps)):
            assert caps[i].in_spec() == caps[j].in_spec(), f"in_spec mismatch: {forms[i]} vs {forms[j]}"
            assert caps[i].out_spec() == caps[j].out_spec(), f"out_spec mismatch: {forms[i]} vs {forms[j]}"
            assert caps[i].accepts(caps[j]), f"{forms[i]} should accept {forms[j]}"
            assert caps[j].accepts(caps[i]), f"{forms[j]} should accept {forms[i]}"


# TEST652: CAP_IDENTITY constant matches identity caps regardless of string form
def test_652_wildcard_cap_identity_constant():
    identity = CapUrn.from_string(CAP_IDENTITY)

    assert identity.to_string() == "cap:effect=none"
    assert identity.kind() == CapKind.IDENTITY

    long_form = CapUrn.from_string("cap:in=media:;out=media:;effect=none")
    assert identity.accepts(long_form)
    assert long_form.accepts(identity)

    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:")


# TEST127: invalid effect=none declarations fail hard
def test_127_wildcard_identity_routing_isolation():
    with pytest.raises(CapUrnError):
        CapUrn.from_string('cap:in="media:ext=pdf";out="media:enc=utf-8";effect=none')


# TEST653: invalid effect=none declarations fail at construction
def test_653_effect_none_illegal_declaration_rejected():
    with pytest.raises(CapUrnError):
        CapUrn.from_string('cap:in="media:ext=pdf";out="media:enc=utf-8";effect=none')


# TEST0125: effect=none preserves runtime media identity
def test_0125_effect_none_preserves_runtime_media():
    decimate = CapUrn.from_string("cap:decimate-sequence;effect=none")
    png = MediaUrn.from_string("media:ext=png;image")
    pdf = MediaUrn.from_string("media:ext=pdf")
    assert decimate.infer_runtime_output_media(png).to_string() == png.to_string()
    assert decimate.infer_runtime_output_media(pdf).to_string() == pdf.to_string()


# TEST0126: default effect=declared uses the declared output
def test_0126_effect_declared_uses_declared_output():
    resize = CapUrn.from_string("cap:in=media:image;out=media:image;resize")
    png = MediaUrn.from_string("media:ext=png;image;width=4000")
    assert resize.infer_runtime_output_media(png).to_string() == "media:image"


# TEST0128: omitted effect means declared; unconstrained effect must be explicit
def test_0128_effect_dispatch_requires_explicit_wildcard():
    none_provider = CapUrn.from_string("cap:effect=none")
    declared_request = CapUrn.from_string("cap:raw")
    any_request = CapUrn.from_string("cap:?effect")
    assert not none_provider.is_dispatchable(declared_request)
    assert none_provider.is_dispatchable(any_request)


# TEST823: is_dispatchable — exact match provider dispatches request
def test_823_dispatch_exact_match():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    assert provider.is_dispatchable(request)


# TEST824: is_dispatchable — provider with broader input handles specific request (contravariance)
def test_824_dispatch_contravariant_input():
    provider = CapUrn.from_string(
        'cap:in="media:";analyze;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";analyze;out="media:enc=utf-8;record"'
    )
    assert provider.is_dispatchable(request)


# TEST825: is_dispatchable — request with unconstrained input dispatches to specific provider media: on the request input axis means "unconstrained" — vacuously true
def test_825_dispatch_request_unconstrained_input():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";analyze;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:";analyze;out="media:enc=utf-8;record"'
    )
    assert provider.is_dispatchable(request), \
        "Request in=media: is unconstrained — axis is vacuously true"


# TEST826: is_dispatchable — provider output must satisfy request output (covariance)
def test_826_dispatch_covariant_output():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8"'
    )
    assert provider.is_dispatchable(request), \
        "Provider output enc=utf-8;record conforms to request output enc=utf-8"


# TEST827: is_dispatchable — provider with generic output cannot satisfy specific request
def test_827_dispatch_generic_output_fails():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    assert not provider.is_dispatchable(request), \
        "Provider out=media: cannot guarantee specific output"


# TEST828: is_dispatchable — wildcard * tag in request, provider missing tag → reject
def test_828_dispatch_wildcard_requires_tag_presence():
    provider = CapUrn.from_string(
        'cap:in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:candle=*;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    assert not provider.is_dispatchable(request), \
        "Wildcard * means tag must be present — provider has no candle tag"


# TEST829: is_dispatchable — wildcard * tag in request, provider has tag → accept
def test_829_dispatch_wildcard_with_tag_present():
    provider = CapUrn.from_string(
        'cap:candle=metal;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:candle=*;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    assert provider.is_dispatchable(request), \
        "Provider has candle=metal, request has candle=* — tag present, any value OK"


# TEST830: is_dispatchable — provider extra tags are refinement, always OK
def test_830_dispatch_provider_extra_tags():
    provider = CapUrn.from_string(
        'cap:candle=metal;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    assert provider.is_dispatchable(request), \
        "Provider extra tag candle=metal is refinement — always OK"


# TEST831: is_dispatchable — cross-backend mismatch prevented
def test_831_dispatch_cross_backend_mismatch():
    gguf_provider = CapUrn.from_string(
        'cap:gguf=q4_k_m;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    candle_request = CapUrn.from_string(
        'cap:candle=*;in="media:model-spec";run-inference;out="media:enc=utf-8;record"'
    )
    assert not gguf_provider.is_dispatchable(candle_request), \
        "GGUF provider has no candle tag — cross-backend mismatch"


# TEST832: is_dispatchable is NOT symmetric
def test_832_dispatch_asymmetric():
    broad = CapUrn.from_string(
        'cap:in="media:";process;out="media:enc=utf-8;record"'
    )
    narrow = CapUrn.from_string(
        'cap:in="media:ext=pdf";process;out="media:enc=utf-8"'
    )
    # broad provider CAN dispatch narrow request:
    #   input: provider in=media: accepts anything -> OK
    #   output: provider out=media:enc=utf-8;record conforms to request out=media:enc=utf-8 -> OK
    assert broad.is_dispatchable(narrow)
    # narrow provider CANNOT dispatch broad request:
    #   input: request in=media: unconstrained -> OK
    #   output: provider out=media:enc=utf-8, request out=media:enc=utf-8;record
    #           enc=utf-8 does NOT conform to enc=utf-8;record -> FAIL
    assert not narrow.is_dispatchable(broad)


# TEST833: is_comparable — both directions checked
def test_833_comparable_symmetric():
    a = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8"'
    )
    b = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    assert a.is_comparable(b)
    assert b.is_comparable(a)


# TEST834: is_comparable — unrelated caps are NOT comparable
def test_834_comparable_unrelated():
    a = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8"'
    )
    b = CapUrn.from_string(
        'cap:in="media:audio";transcribe;out="media:enc=utf-8;record"'
    )
    assert not a.is_comparable(b)
    assert not b.is_comparable(a)


# TEST835: is_equivalent — identical caps
def test_835_equivalent_identical():
    a = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    b = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    assert a.is_equivalent(b)
    assert b.is_equivalent(a)


# TEST836: is_equivalent — non-equivalent comparable caps
def test_836_equivalent_non_equivalent():
    a = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8"'
    )
    b = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    assert a.is_comparable(b)
    assert not a.is_equivalent(b)


# TEST837: is_dispatchable — op tag mismatch rejects
def test_837_dispatch_op_mismatch():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";summarize;out="media:enc=utf-8;record"'
    )
    assert not provider.is_dispatchable(request)


# TEST838: is_dispatchable — request with wildcard output accepts any provider output
def test_838_dispatch_request_wildcard_output():
    provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:enc=utf-8;record"'
    )
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out="media:"'
    )
    assert provider.is_dispatchable(request), \
        "Request out=media: is unconstrained — any provider output accepted"


# TEST890: Semantic direction matching - generic provider matches specific request
def test_890_direction_semantic_matching():
    generic_cap = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    pdf_request = CapUrn.from_string(
        'cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    assert generic_cap.accepts(pdf_request)

    epub_request = CapUrn.from_string(
        'cap:in="media:ext=epub";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    assert generic_cap.accepts(epub_request)

    pdf_cap = CapUrn.from_string(
        'cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    generic_request = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    assert not pdf_cap.accepts(generic_request)
    assert not pdf_cap.accepts(epub_request)

    specific_out_cap = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    generic_out_request = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:image"'
    )
    assert specific_out_cap.accepts(generic_out_request)

    generic_out_cap = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:image"'
    )
    specific_out_request = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    assert not generic_out_cap.accepts(specific_out_request)


# TEST1100: Tests that CapUrn normalizes media URN tags to canonical order This is the root cause fix for caps not matching when cartridges report URNs with different tag ordering than the registry (e.g., "record;enc=utf-8" vs "enc=utf-8;record")
def test_1100_cap_urn_normalizes_media_urn_tag_order():
    urn1 = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract-metadata;out="media:enc=utf-8;file-metadata;record"'
    )
    urn2 = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract-metadata;out="media:enc=utf-8;file-metadata;record"'
    )

    assert urn1.to_string() == urn2.to_string()
    canonical = urn1.to_string()
    assert "enc=utf-8;file-metadata;record" in canonical


# TEST1103: Tests that is_dispatchable has correct directionality The available cap (provider) must be dispatchable for the requested cap (request). This tests the directionality: provider.is_dispatchable(&request) NOTE: This now tests CapUrn::is_dispatchable directly, not via MachinePlanBuilder
def test_1103_is_dispatchable_uses_correct_directionality():
    general_request = CapUrn.from_string('cap:in="media:ext=pdf";extract;out=media:text')
    specific_provider = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out=media:text;version=2'
    )

    assert specific_provider.is_dispatchable(general_request)
    assert not general_request.is_dispatchable(specific_provider)


# TEST1104: Tests that is_dispatchable rejects when provider cannot dispatch request
def test_1104_is_dispatchable_rejects_non_dispatchable():
    request = CapUrn.from_string(
        'cap:in="media:ext=pdf";extract;out=media:text;required=yes'
    )
    provider = CapUrn.from_string('cap:in="media:ext=pdf";extract;out=media:text')

    assert not provider.is_dispatchable(request)


# TEST891: Semantic direction specificity — more constraints in either axis means a higher score under the truth-table-driven sum. media: (top, no tags) scores 0; each marker tag scores 2; each exact tag scores 3.
def test_891_direction_semantic_specificity():
    generic_cap = CapUrn.from_string(
        'cap:in="media:";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    specific_cap = CapUrn.from_string(
        'cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )

    # generic:
    #   out=media:ext=png;image;thumbnail -> 4 (ext=png exact-value) + 2 + 2 = 8
    #   in=media:                     -> 0
    #   y: generate-thumbnail marker  -> 2
    #   spec_C = 10000*8 + 100*0 + 2 = 80002
    assert generic_cap.specificity() == 10000*8 + 100*0 + 2
    # specific:
    #   out=media:ext=png;image;thumbnail -> 8
    #   in=media:ext=pdf              -> 4 (ext=pdf is an exact-value tag, not a bare marker)
    #   y: generate-thumbnail marker  -> 2
    #   spec_C = 10000*8 + 100*4 + 2 = 80402
    assert specific_cap.specificity() == 10000*8 + 100*4 + 2

    assert specific_cap.specificity() > generic_cap.specificity()

    pdf_request = CapUrn.from_string(
        'cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"'
    )
    caps = [generic_cap, specific_cap]
    best = CapMatcher.find_best_match(caps, pdf_request)
    assert best is not None
    assert best.in_spec() == "media:ext=pdf"


# TEST920: Tests creation of a simple execution plan with a single capability Verifies that single_cap() generates a valid plan with input_slot, cap node, and output node
def test_920_cap_urn_total_order_basic():
    a = CapUrn.from_string('cap:in="media:";a;out="media:"')
    b = CapUrn.from_string('cap:in="media:";b;out="media:"')
    c = CapUrn.from_string('cap:in="media:ext=pdf";a;out="media:"')

    # Irreflexivity: a < a must be False
    assert not (a < a)
    assert not (b < b)

    # a and b differ only in op tag — canonical strings determine order
    # a < b lexicographically
    if a < b:
        assert not (b < a), "antisymmetry violated"
        assert a <= b
        assert b > a
        assert b >= a
    else:
        assert b < a
        assert b <= a
        assert a > b
        assert a >= b

    # c has a more-specific in_urn, so it differs on the first key
    # Equal in_urn caps sort by out_urn then tags
    assert (a < c) != (c < a), "antisymmetry violated for a vs c"


# TEST921: Tests creation of a linear chain of capabilities connected in sequence Verifies that linear_chain() correctly links multiple caps with proper edges and topological order
def test_921_cap_urn_order_consistent_with_equality():
    a = CapUrn.from_string('cap:in="media:ext=pdf";convert;out="media:enc=utf-8"')
    b = CapUrn.from_string('cap:in="media:ext=pdf";convert;out="media:enc=utf-8"')
    assert a == b
    assert not (a < b)
    assert not (b < a)
    assert a <= b
    assert a >= b


# TEST922: Tests creation and validation of an empty execution plan with no nodes Verifies that plans without capabilities are valid and handle zero nodes correctly
def test_922_cap_urn_list_sortable():
    urns = [
        CapUrn.from_string('cap:in="media:ext=pdf";z;out="media:"'),
        CapUrn.from_string('cap:in="media:";a;out="media:"'),
        CapUrn.from_string('cap:in="media:ext=pdf";a;out="media:"'),
        CapUrn.from_string('cap:in="media:";z;out="media:"'),
    ]
    sorted_once = sorted(urns)
    sorted_twice = sorted(urns)
    assert sorted_once == sorted_twice, "sort not deterministic"

    # Verify sorted order obeys transitivity: each element ≤ next
    for i in range(len(sorted_once) - 1):
        assert sorted_once[i] <= sorted_once[i + 1], \
            f"sorted order violated at index {i}: {sorted_once[i]} > {sorted_once[i+1]}"


# TEST923: Tests storing and retrieving metadata attached to an execution plan Verifies that arbitrary JSON metadata can be associated with a plan for context preservation
def test_923_cap_urn_order_returns_not_implemented_for_non_cap():
    a = CapUrn.from_string('cap:in="media:";x;out="media:"')
    result = a.__lt__("not a cap urn")
    assert result is NotImplemented
    result = a.__le__(42)
    assert result is NotImplemented
    result = a.__gt__(None)
    assert result is NotImplemented
    result = a.__ge__(object())
    assert result is NotImplemented


# -------------------------------------------------------------------
# CapKind classifier tests (test1800–test1805).
#
# Mirrored across every language port (Rust, Go, Python, Swift/ObjC,
# JS) under the SAME numbers. Any divergence is a wire-level
# inconsistency — the kind taxonomy is part of the protocol's public
# surface, not a per-port detail.
# -------------------------------------------------------------------


# TEST1800: Identity classifier — and only explicit effect=none qualifies.
def test_1800_kind_identity_only_for_bare_cap():
    identity = CapUrn.from_string("cap:effect=none")
    assert identity.kind() == CapKind.IDENTITY

    for spelling in [
        "cap:in=media:;out=media:;effect=none",
        "cap:effect=none;in=*;out=*",
        "cap:effect=none;in=media:",
        "cap:effect=none;out=media:",
    ]:
        cap = CapUrn.from_string(spelling)
        assert cap.kind() == CapKind.IDENTITY, (
            f"{spelling} should classify as Identity (canonical form is `cap:effect=none`)"
        )

    with pytest.raises(CapUrnError):
        CapUrn.from_string("cap:")

    with_op = CapUrn.from_string("cap:passthrough")
    assert with_op.kind() == CapKind.TRANSFORM, (
        "cap:passthrough specifies the operation axis — not Identity"
    )


# TEST1801: Source classifier — in=media:void, out non-void. The y dimension may carry any tags; void on the input alone is what matters.
def test_1801_kind_source_when_input_is_void():
    warm = CapUrn.from_string('cap:in=media:void;out="media:model-artifact";warm')
    assert warm.kind() == CapKind.SOURCE

    gen = CapUrn.from_string('cap:in=media:void;out="media:enc=utf-8"')
    assert gen.kind() == CapKind.SOURCE


# TEST1802: Sink classifier — out=media:void, in non-void.
def test_1802_kind_sink_when_output_is_void():
    discard = CapUrn.from_string("cap:discard;in=media:;out=media:void")
    assert discard.kind() == CapKind.SINK

    log_cap = CapUrn.from_string('cap:in="media:enc=utf-8;fmt=json";log;out=media:void')
    assert log_cap.kind() == CapKind.SINK


# TEST1803: Effect classifier — both sides void. Reads as `() → ()`.
def test_1803_kind_effect_when_both_sides_void():
    ping = CapUrn.from_string("cap:in=media:void;out=media:void;ping")
    assert ping.kind() == CapKind.EFFECT

    bare = CapUrn.from_string("cap:in=media:void;out=media:void")
    assert bare.kind() == CapKind.EFFECT


# TEST1804: Transform classifier — at least one side non-void, and the cap is not the bare identity. The default kind for ordinary data-processing caps.
def test_1804_kind_transform_for_normal_data_processors():
    extract = CapUrn.from_string('cap:extract;in="media:ext=pdf";out="media:enc=utf-8;record"')
    assert extract.kind() == CapKind.TRANSFORM

    labeled = CapUrn.from_string("cap:passthrough;in=media:;out=media:")
    assert labeled.kind() == CapKind.TRANSFORM


# TEST1805: Kind is invariant under canonicalization. The same morphism written in many surface forms must classify the same way once parsed. This pins the rule that kind is a property of the cap as a structured object, not of any particular spelling.
def test_1805_kind_invariant_under_canonical_spellings():
    cases = [
        ("cap:effect=none", "cap:in=media:;out=media:;effect=none", CapKind.IDENTITY),
        (
            'cap:extract;in="media:ext=pdf";out="media:enc=utf-8"',
            'cap:extract;in="media:ext=pdf";out="media:enc=utf-8"',
            CapKind.TRANSFORM,
        ),
        (
            'cap:in=media:void;out="media:enc=utf-8";warm',
            'cap:warm;out="media:enc=utf-8";in=media:void',
            CapKind.SOURCE,
        ),
    ]

    for a, b, expected in cases:
        kind_a = CapUrn.from_string(a).kind()
        kind_b = CapUrn.from_string(b).kind()
        assert kind_a == expected, f"{a} should classify as {expected}, got {kind_a}"
        assert kind_b == expected, f"{b} should classify as {expected}, got {kind_b}"
        assert kind_a == kind_b, (
            f"{a} and {b} parse to the same cap and must classify identically"
        )


# -------------------------------------------------------------------
# Truth-table specificity tests (test1820–test1824).
#
# Mirrored across every language port (Rust, Go, Python, Swift/ObjC,
# JS) under the SAME numbers. Specificity must be the truth-table
# sum across all three axes using the six-form ladder:
#
#   ?x or missing     -> 0   (no constraint)
#   x?=v              -> 1   (absent OR not v)
#   x (=x=*) marker   -> 2   (must-have-any)
#   x!=v              -> 3   (present and not v)
#   x=v exact         -> 4   (must-have-this-value)
#   !x                -> 5   (must-not-have)
# -------------------------------------------------------------------


# TEST1820: A `?`-valued cap-tag scores 0. Same as missing.
def test_1820_specificity_question_is_zero():
    bare = CapUrn.from_string("cap:?effect")
    assert bare.specificity() == 0

    with_q = CapUrn.from_string("cap:?target")
    assert with_q.specificity() == 0, (
        "?x must score 0 (explicit no-constraint, same as missing)"
    )


# TEST1821: A `!`-valued cap-tag scores 5 (top of negative chain).
def test_1821_specificity_must_not_have_is_five():
    cap = CapUrn.from_string("cap:!constrained")
    assert cap.specificity() == 5, "!constrained (must-not-have) must score 5"


# TEST1822: A `*`-valued cap-tag (including bare markers) scores 2.
def test_1822_specificity_must_have_any_is_two():
    bare_marker = CapUrn.from_string("cap:extract")
    assert bare_marker.specificity() == 2, (
        "bare `extract` parses as extract=* (must-have-any) and scores 2"
    )

    explicit_star = CapUrn.from_string("cap:extract=*")
    assert explicit_star.specificity() == 2, (
        "explicit key=* must score 2 (same as bare marker)"
    )

    assert bare_marker.specificity() == explicit_star.specificity(), (
        "bare marker and explicit key=* are the same form and must score identically"
    )


# TEST1823: An exact-valued cap-tag scores 4.
def test_1823_specificity_exact_value_is_four():
    cap = CapUrn.from_string("cap:target=metadata")
    assert cap.specificity() == 4, "target=metadata (exact value) must score 4"


# TEST1824: All six forms compose additively on a single cap. This pins the truth-table sum across the y axis as a whole.
def test_1824_specificity_combined_y_axis():
    cap = CapUrn.from_string(
        "cap:!constrained;?target;extract;stage!=alpha;target2=metadata;ver?=draft"
    )
    assert cap.specificity() == 15, (
        "y combining all six forms (0+1+2+3+4+5) must sum to 15"
    )


# -------------------------------------------------------------------
# Six-form canonicalization tests (test1830–test1835).
#
# Mirrored across every language port (Rust, Go, Python, Swift/ObjC,
# JS) under the SAME numbers.
# -------------------------------------------------------------------


# TEST1830: ?x ≡ x? ≡ x=? all canonicalize to ?x.
def test_1830_canonicalize_no_constraint():
    canonical = "cap:?x"
    for input_str in ["cap:?x", "cap:x?", "cap:x=?"]:
        cap = CapUrn.from_string(input_str)
        assert cap.to_string() == canonical, (
            f"input {input_str!r} must canonicalize to {canonical!r}"
        )


# TEST1831: ?x=v and x?=v both canonicalize to x?=v. The third hypothetical form `x=?v` is NOT recognized as a qualifier — a value starting with `?` is just an exact value beginning with a `?` character.
def test_1831_canonicalize_absent_or_not_value():
    canonical = "cap:x?=foo"
    for input_str in ["cap:?x=foo", "cap:x?=foo"]:
        cap = CapUrn.from_string(input_str)
        assert cap.to_string() == canonical, (
            f"input {input_str!r} must canonicalize to {canonical!r}"
        )

    # `x=?foo` is a plain exact tag whose value is the string `?foo`
    # — NOT a canonicalization alias.
    exact = CapUrn.from_string("cap:x=?foo")
    assert exact.to_string() == "cap:x=?foo"
    assert exact.get_tag("x") == "?foo"


# TEST1832: x ≡ x=* both canonicalize to bare x.
def test_1832_canonicalize_must_have_any():
    canonical = "cap:x"
    for input_str in ["cap:x", "cap:x=*"]:
        cap = CapUrn.from_string(input_str)
        assert cap.to_string() == canonical, (
            f"input {input_str!r} must canonicalize to {canonical!r}"
        )


# TEST1833: !x=v and x!=v both canonicalize to x!=v. The third hypothetical form `x=!v` is NOT recognized as a qualifier — a value starting with `!` is just an exact value beginning with a `!` character.
def test_1833_canonicalize_present_not_value():
    canonical = "cap:x!=foo"
    for input_str in ["cap:!x=foo", "cap:x!=foo"]:
        cap = CapUrn.from_string(input_str)
        assert cap.to_string() == canonical, (
            f"input {input_str!r} must canonicalize to {canonical!r}"
        )

    # `x=!foo` is a plain exact tag whose value is the string `!foo`
    # — NOT a canonicalization alias.
    exact = CapUrn.from_string("cap:x=!foo")
    assert exact.to_string() == "cap:x=!foo"
    assert exact.get_tag("x") == "!foo"


# TEST1834: x=v stays as x=v (the lone exact-value form).
def test_1834_canonicalize_exact_value():
    cap = CapUrn.from_string("cap:x=foo")
    assert cap.to_string() == "cap:x=foo"


# TEST1835: !x ≡ x! ≡ x=! all canonicalize to !x.
def test_1835_canonicalize_must_not_have():
    canonical = "cap:!x"
    for input_str in ["cap:!x", "cap:x!", "cap:x=!"]:
        cap = CapUrn.from_string(input_str)
        assert cap.to_string() == canonical, (
            f"input {input_str!r} must canonicalize to {canonical!r}"
        )


# TEST1842: Full 6×6 truth table — every cell must match the matrix in 04-PREDICATES.md §2.5. Treats prefix `cap:` as the host for a single-key URN (key `x`), pairing every instance form with every pattern form.
def test_1842_truth_table_full_cross_product():
    forms = ["", "?x", "x?=v", "x", "x!=v", "x=v", "!x"]
    expected = [
        # miss   ?x    x?=v   x      x!=v   x=v    !x
        [True, True, True, False, False, False, True],   # missing
        [True, True, True, True, True, True, True],      # ?x
        [True, True, True, False, False, False, True],   # x?=v
        [True, True, True, True, True, True, False],     # x
        [True, True, True, True, True, False, False],    # x!=v
        [True, True, False, True, False, True, False],   # x=v
        [True, True, True, False, False, False, True],   # !x
    ]
    for i, inst_form in enumerate(forms):
        for j, patt_form in enumerate(forms):
            inst_str = "cap:base;" + inst_form if inst_form else "cap:base"
            patt_str = "cap:base;" + patt_form if patt_form else "cap:base"
            inst = CapUrn.from_string(inst_str)
            patt = CapUrn.from_string(patt_str)
            actual = patt.accepts(inst)
            assert actual == expected[i][j], (
                f"cell (inst={inst_form!r}, patt={patt_form!r}) "
                f"expected {expected[i][j]} got {actual}"
            )


# TEST6734: Invalid qualifier combinations must be rejected.
def test_6734_reject_invalid_combinations():
    invalid = [
        "cap:?x?=v",
        "cap:!x!=v",
        "cap:?!x",
        "cap:!?x",
        "cap:?x=*",
        "cap:!x=*",
        "cap:?x=?",
        "cap:?x=!",
        "cap:!x=?",
        "cap:!x=!",
        "cap:?",
        "cap:!",
    ]
    for input_str in invalid:
        with pytest.raises((CapUrnError, Exception)):
            CapUrn.from_string(input_str)


# TEST6735: out-axis difference dominates combined in+y differences.
def test_6735_axis_weighting_out_dominates():
    big_out = CapUrn.from_string('cap:in=media:;out="media:enc=utf-8;record"')
    big_in_and_y = CapUrn.from_string(
        "cap:in=\"media:ext=pdf\";out=media:record;!constrained;?target;extract;"
        "stage!=alpha;target2=metadata;ver?=draft"
    )
    assert big_out.specificity() > big_in_and_y.specificity(), (
        "out-axis difference must dominate combined in+y differences"
    )


# TEST1845: With equal out-axis, in-axis dominates over y-axis.
def test_1845_axis_weighting_in_dominates_y():
    big_in = CapUrn.from_string("cap:in=\"media:ext=pdf\";out=media:record")
    big_y = CapUrn.from_string(
        "cap:in=media:;out=media:record;!constrained;?target;extract;"
        "stage!=alpha;target2=metadata;ver?=draft"
    )
    assert big_in.specificity() > big_y.specificity(), (
        "in-axis difference must dominate y-axis"
    )


# TEST6736: Decoded layout — 10000*out + 100*in + y.
def test_6736_axis_weighting_decoded_layout():
    cap = CapUrn.from_string('cap:in="media:a;b";out="media:a;b;c;d";extract')
    # out=4 markers (8), in=2 markers (4), y=1 marker (2)
    # 10000*8 + 100*4 + 2 = 80402
    assert cap.specificity() == 10000 * 8 + 100 * 4 + 2
