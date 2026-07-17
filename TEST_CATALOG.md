# CapDag-Py Test Catalog

**Total Tests:** 1192

**Numbered Tests:** 1178

**Unnumbered Tests:** 14

**Numbered Tests Missing Descriptions:** 0

**Numbering Mismatches:** 89

All numbered test numbers are unique.

This catalog lists all tests in the CapDag-Py codebase.

| Test # | Function Name | Description | File |
|--------|---------------|-------------|------|
| test001 | `test_001_cap_urn_creation` | TEST1: Test that cap URN is created with tags parsed correctly and direction specs accessible | tests/test_cap_urn.py:31 |
| test002 | `test_002_direction_specs_default_to_wildcard` | TEST2: Test that missing 'in' or 'out' defaults to media: wildcard | tests/test_cap_urn.py:42 |
| test003 | `test_003_direction_matching` | TEST3: Test that direction specs must match exactly, different in/out types don't match, wildcard matches any | tests/test_cap_urn.py:60 |
| test004 | `test_004_unquoted_values_lowercased` | TEST4: Test that unquoted keys and values are normalized to lowercase | tests/test_cap_urn.py:88 |
| test005 | `test_005_quoted_values_preserve_case` | TEST5: Test that quoted values preserve case while unquoted are lowercased | tests/test_cap_urn.py:109 |
| test006 | `test_006_quoted_value_special_chars` | TEST6: Test that quoted values can contain special characters (semicolons, equals, spaces) | tests/test_cap_urn.py:127 |
| test007 | `test_007_quoted_value_escape_sequences` | TEST7: Test that escape sequences in quoted values (\" and \\) are parsed correctly | tests/test_cap_urn.py:142 |
| test008 | `test_008_mixed_quoted_unquoted` | TEST8: Test that mixed quoted and unquoted values in same URN parse correctly | tests/test_cap_urn.py:157 |
| test009 | `test_009_unterminated_quote_error` | TEST9: Test that unterminated quote produces UnterminatedQuote error | tests/test_cap_urn.py:164 |
| test010 | `test_010_invalid_escape_sequence_error` | TEST10: Test that invalid escape sequences (like \n, \x) produce InvalidEscapeSequence error | tests/test_cap_urn.py:170 |
| test011 | `test_011_serialization_smart_quoting` | TEST11: Test that serialization uses smart quoting (no quotes for simple lowercase, quotes for special chars/uppercase) | tests/test_cap_urn.py:180 |
| test012 | `test_012_round_trip_simple` | TEST12: Test that simple cap URN round-trips (parse -> serialize -> parse equals original) | tests/test_cap_urn.py:199 |
| test013 | `test_013_round_trip_quoted` | TEST13: Test that quoted values round-trip preserving case and spaces | tests/test_cap_urn.py:208 |
| test014 | `test_014_round_trip_escapes` | TEST14: Test that escape sequences round-trip correctly | tests/test_cap_urn.py:218 |
| test015 | `test_015_cap_prefix_required` | TEST15: Test that cap: prefix is required and case-insensitive | tests/test_cap_urn.py:228 |
| test016 | `test_016_trailing_semicolon_equivalence` | TEST16: Test that trailing semicolon is equivalent (same hash, same string, matches) | tests/test_cap_urn.py:243 |
| test017 | `test_017_tag_matching` | TEST17: Test tag matching: exact match, subset match, wildcard match, value mismatch | tests/test_cap_urn.py:285 |
| test018 | `test_018_quoted_values_case_sensitive` | TEST18: Test that quoted values with different case do NOT match (case-sensitive) | tests/test_cap_urn.py:310 |
| test019 | `test_019_missing_tag_handling` | TEST19: Missing tag in instance causes rejection — pattern's tags are constraints | tests/test_cap_urn.py:317 |
| test020 | `test_020_specificity_calculation` | TEST020: Specificity is the sum of per-tag truth-table scores across in/out/y. Marker tags (bare segments and `key=*`) score 2 (must-have-any), exact `key=value` tags score 3, missing/`?` score 0, `!` scores 1. | tests/test_cap_urn.py:338 |
| test021 | `test_021_builder_creates_cap_urn` | TEST21: Test builder creates cap URN with correct tags and direction specs | tests/test_cap_urn.py:355 |
| test022 | `test_022_builder_requires_direction_specs` | TEST22: Test builder requires both in_spec and out_spec | tests/test_cap_urn.py:371 |
| test023 | `test_023_builder_preserves_case` | TEST23: Test builder lowercases keys but preserves value case | tests/test_cap_urn.py:386 |
| test024 | `test_024_directional_accepts` | TEST24: Directional accepts — pattern's tags are constraints, instance must satisfy | tests/test_cap_urn.py:430 |
| test025 | `test_025_find_best_match` | TEST25: Test find_best_match returns most specific matching cap | tests/test_cap_urn.py:458 |
| test026 | `test_026_merge_and_subset` | TEST26: Test merge combines tags from both caps, subset keeps only specified tags | tests/test_cap_urn.py:476 |
| test027 | `test_027_with_wildcard_tag` | TEST27: Test with_wildcard_tag sets tag to wildcard, including in/out | tests/test_cap_urn.py:495 |
| test28 | `test_28_empty_cap_urn_is_illegal` | TEST28: Test empty cap URN is illegal after effect transition | tests/test_cap_urn.py:512 |
| test029 | `test_029_minimal_valid_cap_urn` | TEST29: Test minimal valid cap URN has just in and out, empty tags | tests/test_cap_urn.py:518 |
| test030 | `test_030_extended_characters_in_values` | TEST30: Test extended characters (forward slashes, colons) in tag values | tests/test_cap_urn.py:526 |
| test031 | `test_031_wildcard_in_keys_and_values` | TEST31: Test wildcard rejected in keys but accepted in values | tests/test_cap_urn.py:533 |
| test032 | `test_032_duplicate_keys_rejected` | TEST32: Test duplicate keys are rejected with DuplicateKey error | tests/test_cap_urn.py:545 |
| test033 | `test_033_numeric_keys` | TEST33: Test pure numeric keys rejected, mixed alphanumeric allowed, numeric values allowed | tests/test_cap_urn.py:552 |
| test034 | `test_034_empty_values_rejected` | TEST34: Test empty values are rejected | tests/test_cap_urn.py:567 |
| test035 | `test_035_has_tag_behavior` | TEST35: Test has_tag is case-sensitive for values, case-insensitive for keys, works for in/out | tests/test_cap_urn.py:574 |
| test036 | `test_036_with_tag_preserves_case` | TEST36: Test with_tag preserves value case | tests/test_cap_urn.py:593 |
| test037 | `test_037_with_tag_rejects_empty` | TEST37: Test with_tag rejects empty value | tests/test_cap_urn.py:600 |
| test038 | `test_038_semantic_equivalence_quoted_unquoted` | TEST38: Test semantic equivalence of unquoted and quoted simple lowercase values | tests/test_cap_urn.py:607 |
| test039 | `test_039_get_tag_direction_specs` | TEST39: Test get_tag returns direction specs (in/out) with case-insensitive lookup | tests/test_cap_urn.py:616 |
| test040 | `test_040_matching_semantics_exact_match` | TEST40: Matching semantics - exact match succeeds | tests/test_cap_urn.py:640 |
| test041 | `test_041_matching_semantics_cap_missing_tag` | TEST41: Matching semantics - cap missing tag matches (implicit wildcard) | tests/test_cap_urn.py:647 |
| test042 | `test_042_matching_semantics_cap_has_extra_tag` | TEST42: Pattern rejects instance missing required tags | tests/test_cap_urn.py:654 |
| test043 | `test_043_matching_semantics_request_has_wildcard` | TEST43: Matching semantics - request wildcard matches specific cap value | tests/test_cap_urn.py:664 |
| test044 | `test_044_matching_semantics_cap_has_wildcard` | TEST44: Matching semantics - cap wildcard matches specific request value | tests/test_cap_urn.py:671 |
| test045 | `test_045_matching_semantics_value_mismatch` | TEST45: Matching semantics - value mismatch does not match | tests/test_cap_urn.py:678 |
| test046 | `test_046_matching_semantics_fallback_pattern` | TEST46: Matching semantics - fallback pattern (cap missing tag = implicit wildcard) | tests/test_cap_urn.py:685 |
| test047 | `test_047_matching_semantics_thumbnail_void_input` | TEST47: Matching semantics - thumbnail fallback with void input | tests/test_cap_urn.py:693 |
| test048 | `test_048_matching_semantics_direction_mismatch` | TEST48: Matching semantics - wildcard direction matches anything | tests/test_cap_urn.py:717 |
| test049 | `test_049_matching_semantics_cross_dimension` | TEST49: Non-overlapping tags — neither direction accepts | tests/test_cap_urn.py:708 |
| test050 | `test_050_matching_semantics_test10_direction_mismatch` | TEST50: Matching semantics - direction mismatch prevents matching | tests/test_cap_urn.py:726 |
| test051 | `test_051_input_validation_success` | TEST51: Test input validation succeeds with valid positional argument | tests/test_validation.py:44 |
| test052 | `test_052_input_validation_missing_required` | TEST52: Test input validation fails with MissingRequiredArgument when required arg missing | tests/test_validation.py:69 |
| test053 | `test_053_input_validation_wrong_type` | TEST53: Test input validation fails with InvalidArgumentType when wrong type provided | tests/test_validation.py:118 |
| test060 | `test_060_wrong_prefix_fails` | TEST60: Test wrong prefix fails with InvalidPrefix error showing expected and actual prefix | tests/test_media_urn.py:39 |
| test062 | `test_062_is_record` | TEST62: Test is_record returns true when record marker tag is present indicating key-value structure | tests/test_media_urn.py:51 |
| test063 | `test_063_is_scalar` | TEST63: Test is_scalar returns true when list marker tag is absent (scalar is default) | tests/test_media_urn.py:65 |
| test064 | `test_064_is_list` | TEST64: Test is_list returns true when list marker tag is present indicating ordered collection | tests/test_media_urn.py:76 |
| test065 | `test_065_is_opaque` | TEST65: Test is_opaque returns true when record marker is absent (opaque is default) | tests/test_media_urn.py:89 |
| test066 | `test_066_is_json` | TEST66: Test is_json returns true only when json marker tag is present for JSON representation | tests/test_media_urn.py:100 |
| test067 | `test_067_is_text` | TEST67: Text-representability is now carried by the orthogonal `enc=` tag (the old `textable` marker and is_text() are gone). A media is "text" iff it declares an encoding. enc is orthogonal to format/numeric, so only media that actually carry enc= are text. | tests/test_media_urn.py:110 |
| test068 | `test_068_is_void` | TEST68: Test is_void returns true when void flag or type=void tag is present | tests/test_media_urn.py:123 |
| test071 | `test_071_to_string_roundtrip` | TEST71: Test to_string roundtrip ensures serialization and deserialization preserve URN structure | tests/test_media_urn.py:133 |
| test072 | `test_072_all_constants_parse` | TEST72: Test all media URN constants parse successfully as valid media URNs | tests/test_media_urn.py:142 |
| test073 | `test_073_extension_helpers` | TEST73: Test extension helper functions create media URNs with ext tag and correct format | tests/test_media_urn.py:163 |
| test074 | `test_074_media_urn_matching` | TEST74: Test media URN conforms_to using tagged URN semantics with specific and generic requirements | tests/test_media_urn.py:188 |
| test075 | `test_075_matching` | TEST75: Test accepts with implicit wildcards where handlers with fewer tags can handle more requests | tests/test_media_urn.py:207 |
| test076 | `test_076_specificity` | TEST76: Test specificity increases with more tags for ranking conformance | tests/test_media_urn.py:220 |
| test077 | `test_077_serde_roundtrip` | TEST77: Test serde roundtrip serializes to JSON string and deserializes back correctly | tests/test_media_urn.py:237 |
| test078 | `test_078_object_does_not_conform_to_string` | TEST78: conforms_to behavior between MEDIA_OBJECT and MEDIA_STRING | tests/test_media_urn.py:246 |
| test088 | `test_088_resolve_seeded_spec` | TEST88: Resolving a media URN seeded into the registry returns the seeded spec verbatim. A regression in the registry-resolution path would surface as a `None`-shaped result here, since there is no local-override fallback to mask it. | tests/test_media_def.py:44 |
| test089 | `test_089_resolve_seeded_record_spec` | TEST89: A seeded record-shaped media def carries its schema and profile_uri intact through resolution. Catches a regression that dropped optional fields when copying into ResolvedMediaDef. | tests/test_media_def.py:58 |
| test0090 | `test_0090_absent_scan_root_yields_empty_roster` | TEST90: Absent scan root yields empty roster | tests/test_cartridge_discovery.py:78 |
| test0091 | `test_0091_missing_cartridge_json_is_manifest_invalid` | TEST91: Missing cartridge json is manifest invalid | tests/test_cartridge_discovery.py:84 |
| test0092 | `test_0092_channel_mismatch_is_bad_installation` | TEST92: Channel mismatch is bad installation | tests/test_cartridge_discovery.py:91 |
| test093 | `test_093_resolve_unresolvable_fails_hard` | TEST93: Resolving a URN that is neither in the registry cache nor available online fails hard. A regression that made the fail path silently return a stub `ResolvedMediaDef` would surface here as a missing error. | tests/test_media_def.py:79 |
| test0094 | `test_0094_fabric_manifest_mismatch_is_flagged` | TEST94: Fabric manifest mismatch is flagged | tests/test_cartridge_discovery.py:100 |
| test095 | `test_095_media_def_def_serialize` | TEST95: Test MediaDef serializes with required fields and skips None fields | tests/test_media_def.py:93 |
| test096 | `test_096_media_def_def_deserialize` | TEST96: Test deserializing MediaDef from JSON object | tests/test_media_def.py:117 |
| test097 | `test_097_validate_no_duplicate_urns_catches_duplicates` | TEST97: Test duplicate URN validation catches duplicates | tests/test_media_def.py:136 |
| test098 | `test_098_validate_no_duplicate_urns_passes_for_unique` | TEST98: Test duplicate URN validation passes for unique URNs | tests/test_media_def.py:155 |
| test099 | `test_099_resolved_is_binary` | TEST99: The identity media (`media:`) carries no encoding, no record marker, and no format. The old is_binary() delegate is gone (binary/text is no longer a distinction); a media is text-representable iff it declares enc=. | tests/test_media_def.py:178 |
| test100 | `test_100_resolved_is_record` | TEST100: Test ResolvedMediaDef is_record returns true when record marker is present | tests/test_media_def.py:197 |
| test101 | `test_101_resolved_is_scalar` | TEST101: Test ResolvedMediaDef is_scalar returns true when list marker is absent | tests/test_media_def.py:215 |
| test102 | `test_102_resolved_is_list` | TEST102: Test ResolvedMediaDef is_list returns true when list marker is present | tests/test_media_def.py:233 |
| test103 | `test_103_resolved_is_json` | TEST103: Test ResolvedMediaDef is_json returns true when json tag is present | tests/test_media_def.py:251 |
| test104 | `test_104_resolved_is_text` | TEST104: Test ResolvedMediaDef text-representability is carried by the enc= tag | tests/test_media_def.py:268 |
| test105 | `test_105_metadata_propagation` | TEST105: Test metadata propagates from media def def to resolved media def | tests/test_media_def.py:291 |
| test106 | `test_106_metadata_with_validation` | TEST106: Test metadata and validation can coexist in media definition | tests/test_media_def.py:313 |
| test107 | `test_107_extensions_propagation` | TEST107: Test extensions field propagates from media def def to resolved | tests/test_media_def.py:346 |
| test108 | `test_108_cap_creation` | TEST108: Test creating new cap with URN, title, and command verifies correct initialization | tests/test_cap.py:19 |
| test109 | `test_109_cap_with_metadata` | TEST109: Test creating cap with metadata initializes and retrieves metadata correctly | tests/test_cap.py:30 |
| test110 | `test_110_cap_matching` | TEST110: Test cap matching with subset semantics for request fulfillment | tests/test_cap.py:46 |
| test111 | `test_111_cap_title` | TEST111: Test getting and setting cap title updates correctly | tests/test_cap.py:57 |
| test112 | `test_112_cap_definition_equality` | TEST112: Test cap equality based on URN and title matching | tests/test_cap.py:68 |
| test113 | `test_113_cap_stdin` | TEST113: Test cap stdin support via args with stdin source and serialization roundtrip | tests/test_cap.py:82 |
| test114 | `test_114_arg_source_types` | TEST114: Test ArgSource type variants stdin, position, and cli_flag with their accessors | tests/test_cap.py:111 |
| test115 | `test_115_cap_arg_serialization` | TEST115: Test CapArg serialization and deserialization with multiple sources | tests/test_cap.py:146 |
| test116 | `test_116_cap_arg_constructors` | TEST116: Test CapArg constructor methods basic and with_description create args correctly | tests/test_cap.py:171 |
| test117 | `test_117_cap_manifest_channel_roundtrip` | TEST117: A manifest's channel round-trips through serde and the serialized form uses the canonical lowercase wire word ("release" / "nightly"). A missing or unrecognized channel is a hard parse error — no defaults. | tests/test_manifest.py:47 |
| test118 | `test_118_dev_manifest_registry_url_is_explicit_null` | TEST118: A dev manifest (built without `MFR_CARTRIDGE_REGISTRY_URL`) carries `registry_url: null` and serializes the field explicitly. The null-vs-absent distinction matters because the parser refuses to accept absent (test117) — so an old SDK can't accidentally pass for a dev build. | tests/test_manifest.py:90 |
| test119 | `test_119_concatenated_vs_final_payload_divergence` | TEST119: CartridgeResponse::Streaming concatenated() and final_payload() diverge for multi-chunk | tests/test_cartridge_host_runtime.py:284 |
| test0120 | `test_0120_registry_url_under_dev_slug_is_rejected` | TEST120: Registry url under dev slug is rejected | tests/test_cartridge_discovery.py:108 |
| test0125 | `test_0125_effect_none_preserves_runtime_media` | TEST125: effect=none preserves runtime media identity | tests/test_cap_urn.py:1092 |
| test0126 | `test_0126_effect_declared_uses_declared_output` | TEST126: default effect=declared uses the declared output | tests/test_cap_urn.py:1101 |
| test127 | `test_127_wildcard_identity_routing_isolation` | TEST127: invalid effect=none declarations fail hard | tests/test_cap_urn.py:1080 |
| test0128 | `test_0128_effect_dispatch_requires_explicit_wildcard` | TEST128: omitted effect means declared; unconstrained effect must be explicit | tests/test_cap_urn.py:1108 |
| test129 | `test_129_gc_evicts_oldest_entries_by_touch_sequence` | TEST129: The GC drops the OLDEST entries by touch-sequence, not arbitrary keys; the post-GC keyset is exactly what the test computes should survive. | tests/test_cartridge_host_runtime.py:340 |
| test0131 | `test_0131_runtime_identity_probe_required_on_empty_to_nonempty_transition` | TEST0131: empty→non-empty transition must run a runtime identity probe; a master that fails it ends up unhealthy with last_error and its caps are excluded from routing. | tests/test_relay_switch.py:1394 |
| test132 | `test_132_add_master_dynamic` | TEST132: add_master dynamically connects new host to running switch | tests/test_relay_switch.py:1141 |
| test133 | `test_133_reattach_by_id_preserves_slot_index` | Reattach-by-id tests for the cardinality-stable slot model. When a master dies and the host reconnects, the new socket MUST attach to the same slot index — preserving routing entries keyed by index. Accumulating zombie slots on each reconnect was the bug class these tests guard against. | tests/test_relay_switch.py:923 |
| test134 | `test_134_add_master_with_duplicate_healthy_id_errors` | TEST134: Add master with duplicate healthy id errors | tests/test_relay_switch.py:992 |
| test0135 | `test_0135_runtime_identity_probe_success_makes_caps_routable` | TEST0135: the SUCCESS path — a master that advertises caps after connecting and then passes the probe flips healthy and its caps become routable. | tests/test_relay_switch.py:1420 |
| test0136 | `test_0136_all_masters_ready_false_when_expected_count_unset` | TEST136: All masters ready false when expected count unset | tests/test_relay_switch.py:1049 |
| test0137 | `test_0137_all_masters_ready_false_when_partially_connected` | TEST137: All masters ready false when partially connected | tests/test_relay_switch.py:1091 |
| test138 | `test_138_parse_registry_json_with_stdin` | TEST138: Test parsing registry JSON with stdin args verifies stdin media URN extraction | tests/test_registry.py:99 |
| test0139 | `test_0139_all_masters_ready_true_when_masters_connected_but_capless` | TEST139: All masters ready true when masters connected but capless | tests/test_relay_switch.py:1107 |
| test0140 | `test_0140_all_masters_ready_does_not_overshoot` | TEST140: All masters ready does not overshoot | tests/test_relay_switch.py:1125 |
| test141 | `test_141_per_cap_url_shape` | TEST141: URL has the right shape — protocol, host, /caps/ prefix, 64 hex chars, no extension. Mirrors Go's Test141_per_cap_url_shape and ObjC's test141_perCapURLShape; the previous Python TEST141 (`different_caps_different_hashes`) was renumbered to TEST938 to resolve a cross-mirror collision on this number. | tests/test_registry.py:193 |
| test142 | `test_142_normalize_handles_different_tag_orders` | TEST142: Test normalize handles different tag orders producing same canonical form | tests/test_registry.py:225 |
| test143 | `test_143_default_config` | TEST143: Default config points at https://fabric.capdag.com/ unless overridden by CDG_FABRIC_REGISTRY_URL. | tests/test_registry.py:238 |
| test144 | `test_144_custom_registry_url` | TEST1899: Test custom registry URL updates both registry and schema base URLs | tests/test_registry.py:252 |
| test145 | `test_145_custom_registry_and_schema_url` | TEST145: Test custom registry and schema URLs set independently | tests/test_registry.py:288 |
| test146 | `test_146_schema_url_not_overwritten_when_explicit` | TEST146: Test schema URL not overwritten when set explicitly before registry URL | tests/test_registry.py:299 |
| test147 | `test_147_registry_for_test_with_config` | TEST147: Test registry for test with custom config creates registry with specified URLs | tests/test_registry.py:311 |
| test148 | `test_148_cap_manifest_creation` | TEST148: Manifest creation with cap groups | tests/test_manifest.py:25 |
| test149 | `test_149_cap_manifest_with_author` | TEST149: Author field | tests/test_manifest.py:108 |
| test150 | `test_150_cap_manifest_json_serialization` | TEST150: JSON roundtrip | tests/test_manifest.py:124 |
| test151 | `test_151_cap_manifest_required_fields` | TEST151: Missing required fields fail | tests/test_manifest.py:172 |
| test152 | `test_152_cap_manifest_with_multiple_caps` | TEST152: Multiple caps across groups | tests/test_manifest.py:179 |
| test153 | `test_153_cap_manifest_empty_cap_groups` | TEST153: Empty cap groups | tests/test_manifest.py:203 |
| test154 | `test_154_cap_manifest_optional_fields` | TEST154: Optional author field omitted in serialization | tests/test_manifest.py:220 |
| test155 | `test_155_cap_manifest_complex_roundtrip` | TEST155: ComponentMetadata trait | tests/test_manifest.py:238 |
| test156 | `test_156_stdin_source_data_creation` | TEST156: Test creating StdinSource Data variant with byte vector | tests/test_caller.py:31 |
| test157 | `test_157_stdin_source_file_reference_creation` | TEST157: Test creating StdinSource FileReference variant with all required fields | tests/test_caller.py:40 |
| test158 | `test_158_stdin_source_data_empty` | TEST158: Test StdinSource Data with empty vector stores and retrieves correctly | tests/test_caller.py:60 |
| test159 | `test_159_stdin_source_data_binary` | TEST159: Test StdinSource Data with binary content like PNG header bytes | tests/test_caller.py:67 |
| test160 | `test_160_stdin_source_data_clone` | TEST160: Test StdinSource Data clone creates independent copy with same data | tests/test_caller.py:78 |
| test161 | `test_161_stdin_source_file_reference_clone` | TEST161: Test StdinSource FileReference clone creates independent copy with same fields | tests/test_caller.py:96 |
| test162 | `test_162_stdin_source_debug_format` | TEST162: Test StdinSource Debug format displays variant type and relevant fields | tests/test_caller.py:116 |
| test163 | `test_163_argument_schema_validation_success` | TEST163: Test argument schema validation succeeds with valid JSON matching schema | tests/test_schema_validation.py:31 |
| test164 | `test_164_argument_schema_validation_failure` | TEST164: Test argument schema validation fails with JSON missing required fields | tests/test_schema_validation.py:61 |
| test165 | `test_165_output_schema_validation_success` | TEST165: Test output schema validation succeeds with valid JSON matching schema | tests/test_schema_validation.py:93 |
| test166 | `test_166_skip_validation_without_schema` | TEST166: Test validation skipped when resolved media def has no schema | tests/test_schema_validation.py:123 |
| test167 | `test_167_unresolvable_media_urn_fails_hard` | TEST167: Test validation fails hard when media URN cannot be resolved from any source | tests/test_schema_validation.py:149 |
| test168 | `test_168_json_response` | TEST168: Test ResponseWrapper from JSON deserializes to correct structured type | tests/test_response.py:20 |
| test169 | `test_169_primitive_types` | TEST169: Test ResponseWrapper converts to primitive types integer, float, boolean, string | tests/test_response.py:31 |
| test170 | `test_170_binary_response` | TEST170: Test ResponseWrapper from binary stores and retrieves raw bytes correctly | tests/test_response.py:50 |
| test171 | `test_171_frame_type_roundtrip` | TEST171: Test all FrameType discriminants roundtrip through u8 conversion preserving identity | tests/test_cbor_frame.py:29 |
| test172 | `test_172_invalid_frame_type` | TEST172: Test FrameType::from_u8 returns None for values outside the valid discriminant range | tests/test_cbor_frame.py:54 |
| test173 | `test_173_frame_type_discriminant_values` | TEST173: Test FrameType discriminant values match the wire protocol specification exactly | tests/test_cbor_frame.py:66 |
| test174 | `test_174_message_id_uuid` | TEST174: Test MessageId::new_uuid generates valid UUID that roundtrips through string conversion | tests/test_cbor_frame.py:84 |
| test175 | `test_175_message_id_uuid_uniqueness` | TEST175: Test two MessageId::new_uuid calls produce distinct IDs (no collisions) | tests/test_cbor_frame.py:95 |
| test176 | `test_176_message_id_uint_has_no_uuid_string` | TEST176: Test MessageId::Uint does not produce a UUID string, to_uuid_string returns None | tests/test_cbor_frame.py:103 |
| test177 | `test_177_message_id_from_invalid_uuid_str` | TEST177: Test MessageId::from_uuid_str rejects invalid UUID strings | tests/test_cbor_frame.py:110 |
| test178 | `test_178_message_id_as_bytes` | TEST178: Test MessageId::as_bytes produces correct byte representations for Uuid and Uint variants | tests/test_cbor_frame.py:118 |
| test179 | `test_179_message_id_default_is_uuid` | TEST179: Test MessageId::default creates a UUID variant (not Uint) | tests/test_cbor_frame.py:131 |
| test180 | `test_180_hello_frame` | TEST180: Test Frame::hello without manifest produces correct HELLO frame for host side | tests/test_cbor_frame.py:138 |
| test181 | `test_181_hello_frame_with_manifest` | TEST181: Test Frame::hello_with_manifest produces HELLO with manifest bytes for cartridge side | tests/test_cbor_frame.py:152 |
| test182 | `test_182_req_frame` | TEST182: Test Frame::req stores cap URN, payload, and content_type correctly | tests/test_cbor_frame.py:165 |
| test184 | `test_184_chunk_frame` | TEST184: Test Frame::chunk stores seq and payload for streaming (with stream_id) | tests/test_cbor_frame.py:181 |
| test185 | `test_185_err_frame` | TEST185: Test Frame::err stores error code and message in metadata | tests/test_cbor_frame.py:197 |
| test186 | `test_186_log_frame` | TEST186: Test Frame::log stores level and message in metadata | tests/test_cbor_frame.py:207 |
| test187 | `test_187_end_frame_with_payload` | TEST187: Test Frame::end with payload sets eof and optional final payload | tests/test_cbor_frame.py:218 |
| test188 | `test_188_end_frame_without_payload` | TEST188: Test Frame::end without payload still sets eof marker | tests/test_cbor_frame.py:228 |
| test189 | `test_189_chunk_with_offset` | TEST189: Test chunk_with_offset sets offset on all chunks but len only on seq=0 (with stream_id) | tests/test_cbor_frame.py:238 |
| test190 | `test_190_heartbeat_frame` | TEST190: Test Frame::heartbeat creates minimal frame with no payload or metadata | tests/test_cbor_frame.py:267 |
| test191 | `test_191_error_accessors_on_non_err_frame` | TEST191: Test error_code and error_message return None for non-Err frame types | tests/test_cbor_frame.py:279 |
| test192 | `test_192_log_accessors_on_non_log_frame` | TEST192: Test log_level and log_message return None for non-Log frame types | tests/test_cbor_frame.py:290 |
| test193 | `test_193_hello_accessors_on_non_hello_frame` | TEST193: Test hello_max_frame and hello_max_chunk return None for non-Hello frame types | tests/test_cbor_frame.py:298 |
| test194 | `test_194_frame_new_defaults` | TEST194: Test Frame::new sets version and defaults correctly, optional fields are None | tests/test_cbor_frame.py:307 |
| test195 | `test_195_frame_default` | TEST195: Test Frame::default creates a Req frame (the documented default) | tests/test_cbor_frame.py:325 |
| test196 | `test_196_is_eof_when_none` | TEST196: Test is_eof returns false when eof field is None (unset) | tests/test_cbor_frame.py:333 |
| test197 | `test_197_is_eof_when_false` | TEST197: Test is_eof returns false when eof field is explicitly Some(false) | tests/test_cbor_frame.py:340 |
| test198 | `test_198_limits_default` | TEST198: Test Limits::default provides the documented default values | tests/test_cbor_frame.py:348 |
| test199 | `test_199_protocol_version_constant` | TEST199: Test PROTOCOL_VERSION is 3 | tests/test_cbor_frame.py:359 |
| test200 | `test_200_key_constants` | TEST200: Test integer key constants match the protocol specification | tests/test_cbor_frame.py:365 |
| test201 | `test_201_hello_manifest_binary_data` | TEST201: Test hello_with_manifest preserves binary manifest data (not just JSON text) | tests/test_cbor_frame.py:381 |
| test202 | `test_202_message_id_equality_and_hash` | TEST202: Test MessageId Eq/Hash semantics: equal UUIDs are equal, different ones are not | tests/test_cbor_frame.py:389 |
| test203 | `test_203_message_id_cross_variant_inequality` | TEST203: Test Uuid and Uint variants of MessageId are never equal even for coincidental byte values | tests/test_cbor_frame.py:412 |
| test204 | `test_204_req_frame_empty_payload` | TEST204: Test Frame::req with empty payload stores Some(empty vec) not None | tests/test_cbor_frame.py:420 |
| test205 | `test_205_encode_frame_produces_cbor_with_integer_keys` | TEST205: Test REQ frame encode/decode roundtrip preserves all fields | tests/test_cbor_io.py:41 |
| test206 | `test_206_decode_frame_parses_cbor_correctly` | TEST206: Test HELLO frame encode/decode roundtrip preserves max_frame, max_chunk, max_reorder_buffer | tests/test_cbor_io.py:59 |
| test207 | `test_207_decode_frame_fails_on_invalid_cbor` | TEST207: Test ERR frame encode/decode roundtrip preserves error code and message | tests/test_cbor_io.py:71 |
| test208 | `test_208_decode_frame_fails_on_non_map` | TEST208: Test LOG frame encode/decode roundtrip preserves level and message | tests/test_cbor_io.py:77 |
| test210 | `test_210_read_frame_reads_length_prefixed` | TEST210: Test END frame encode/decode roundtrip preserves eof marker and optional payload | tests/test_cbor_io.py:86 |
| test211 | `test_211_read_frame_returns_none_on_eof` | TEST211: Test HELLO with manifest encode/decode roundtrip preserves manifest bytes and limits | tests/test_cbor_io.py:103 |
| test212 | `test_212_read_frame_fails_on_incomplete_length_prefix` | TEST212: Test chunk_with_offset encode/decode roundtrip preserves offset, len, eof (with stream_id) | tests/test_cbor_io.py:112 |
| test213 | `test_213_read_frame_fails_on_incomplete_frame_data` | TEST213: Test heartbeat frame encode/decode roundtrip preserves ID with no extra fields | tests/test_cbor_io.py:121 |
| test214 | `test_214_write_read_frame_io_roundtrip` | TEST214: Test write_frame/read_frame IO roundtrip through length-prefixed wire format | tests/test_cbor_io.py:131 |
| test215 | `test_215_frame_reader_reads_multiple_frames` | TEST215: Test reading multiple sequential frames from a single buffer | tests/test_cbor_io.py:152 |
| test216 | `test_216_write_frame_rejects_oversized_frame` | TEST216: Test write_frame rejects frames exceeding max_frame limit | tests/test_cbor_io.py:189 |
| test217 | `test_217_read_frame_rejects_oversized_incoming_frame` | TEST217: Test read_frame rejects incoming frames exceeding the negotiated max_frame limit | tests/test_cbor_io.py:205 |
| test218 | `test_218_write_chunked_splits_and_reconstructs` | TEST218: Test write_chunked splits data into chunks respecting max_chunk and reconstructs correctly Chunks from write_chunked have seq=0. SeqAssigner at the output stage assigns final seq. Chunk ordering within a stream is tracked by chunk_index (chunk_index field). | tests/test_cbor_io.py:224 |
| test219 | `test_219_write_chunked_empty_data` | TEST219: Test write_chunked with empty data produces a single EOF chunk | tests/test_cbor_io.py:269 |
| test220 | `test_220_write_chunked_exact_fit` | TEST220: Test write_chunked with data exactly equal to max_chunk produces exactly one chunk | tests/test_cbor_io.py:289 |
| test221 | `test_221_read_frame_returns_none_on_eof` | TEST221: Test read_frame returns Ok(None) on clean EOF (empty stream) | tests/test_cbor_io.py:309 |
| test222 | `test_222_read_frame_fails_on_truncated_length_prefix` | TEST222: Test read_frame handles truncated length prefix (fewer than 4 bytes available) | tests/test_cbor_io.py:315 |
| test223 | `test_223_read_frame_fails_on_truncated_frame_body` | TEST223: Test read_frame returns error on truncated frame body (length prefix says more bytes than available) | tests/test_cbor_io.py:322 |
| test224 | `test_224_handshake_negotiates_to_minimum_limits` | TEST224: Test MessageId::Uint roundtrips through encode/decode | tests/test_cbor_io.py:609 |
| test225 | `test_225_handshake_function_full_handshake` | TEST225: Test decode_frame rejects non-map CBOR values (e.g., array, integer, string) | tests/test_cbor_io.py:645 |
| test226 | `test_226_handshake_accept_receives_first` | TEST226: Test decode_frame rejects CBOR map missing required version field | tests/test_cbor_io.py:675 |
| test227 | `test_227_handshake_fails_if_cartridge_missing_manifest` | TEST227: Test decode_frame rejects CBOR map with invalid frame_type value | tests/test_cbor_io.py:706 |
| test228 | `test_228_read_frame_enforces_limit` | TEST228: Test decode_frame rejects CBOR map missing required id field | tests/test_cbor_io.py:731 |
| test229 | `test_229_frame_with_zero_length_payload` | TEST229: Test FrameReader/FrameWriter set_limits updates the negotiated limits | tests/test_cbor_io.py:749 |
| test230 | `test_230_frame_roundtrip_preserves_fields` | TEST230: Test async handshake exchanges HELLO frames and negotiates minimum limits | tests/test_cbor_io.py:764 |
| test231 | `test_231_multiple_readers_on_same_stream` | TEST231: Test handshake fails when peer sends non-HELLO frame | tests/test_cbor_io.py:786 |
| test232 | `test_232_writer_flushes_after_each_frame` | TEST232: Test handshake fails when cartridge HELLO is missing required manifest | tests/test_cbor_io.py:811 |
| test233 | `test_233_frame_encoding_preserves_binary_data` | TEST233: Test binary payload with all 256 byte values roundtrips through encode/decode | tests/test_cbor_io.py:824 |
| test234 | `test_234_handshake_with_very_small_limits` | TEST234: Test decode_frame handles garbage CBOR bytes gracefully with an error | tests/test_cbor_io.py:837 |
| test235 | `test_235_response_chunk` | TEST235: Test ResponseChunk stores payload, seq, offset, len, and eof fields correctly | tests/test_cartridge_host_runtime.py:45 |
| test236 | `test_236_response_chunk_with_all_fields` | TEST236: Test ResponseChunk with all fields populated preserves offset, len, and eof | tests/test_cartridge_host_runtime.py:62 |
| test237 | `test_237_cartridge_response_single` | TEST237: Test CartridgeResponse::Single final_payload returns the single payload slice | tests/test_cartridge_host_runtime.py:79 |
| test238 | `test_238_cartridge_response_single_empty` | TEST238: Test CartridgeResponse::Single with empty payload returns empty slice and empty vec | tests/test_cartridge_host_runtime.py:86 |
| test239 | `test_239_cartridge_response_streaming` | TEST239: Test CartridgeResponse::Streaming concatenated joins all chunk payloads in order | tests/test_cartridge_host_runtime.py:93 |
| test240 | `test_240_cartridge_response_streaming_final_payload` | TEST240: Test CartridgeResponse::Streaming final_payload returns the last chunk's payload | tests/test_cartridge_host_runtime.py:128 |
| test241 | `test_241_cartridge_response_streaming_empty` | TEST241: Test CartridgeResponse::Streaming with empty chunks vec returns empty concatenation | tests/test_cartridge_host_runtime.py:160 |
| test242 | `test_242_cartridge_response_streaming_large` | TEST242: Test CartridgeResponse::Streaming concatenated capacity is pre-allocated correctly for large payloads | tests/test_cartridge_host_runtime.py:167 |
| test243 | `test_243_async_host_error_variants` | TEST243: Test AsyncHostError variants display correct error messages | tests/test_cartridge_host_runtime.py:203 |
| test244 | `test_244_async_host_error_from_cbor` | TEST244: Test AsyncHostError::from converts CborError to Cbor variant | tests/test_cartridge_host_runtime.py:233 |
| test245 | `test_245_async_host_error_from_io` | TEST245: Test AsyncHostError::from converts io::Error to Io variant | tests/test_cartridge_host_runtime.py:241 |
| test246 | `test_246_async_host_error_equality` | TEST246: Test AsyncHostError Clone implementation produces equal values | tests/test_cartridge_host_runtime.py:248 |
| test247 | `test_247_response_chunk_copy` | TEST247: Test ResponseChunk Clone produces independent copy with same data | tests/test_cartridge_host_runtime.py:259 |
| test248 | `test_248_register_and_find_handler` | TEST248: Test register_op and find_handler by exact cap URN | tests/test_cartridge_runtime.py:178 |
| test249 | `test_249_raw_handler` | TEST249: Test register_op handler echoes bytes directly | tests/test_cartridge_runtime.py:192 |
| test250 | `test_250_typed_handler_deserialization` | TEST250: Test Op handler collects input and processes it | tests/test_cartridge_runtime.py:216 |
| test251 | `test_251_typed_handler_rejects_invalid_json` | TEST251: Test Op handler propagates errors through RuntimeError::Handler | tests/test_cartridge_runtime.py:242 |
| test252 | `test_252_find_handler_unknown_cap` | TEST252: Test find_handler returns None for unregistered cap URNs | tests/test_cartridge_runtime.py:265 |
| test253 | `test_253_handler_is_send_sync` | TEST253: Test OpFactory can be cloned via Arc and sent across tasks (Send + Sync) | tests/test_cartridge_runtime.py:296 |
| test254 | `test_254_no_peer_invoker` | TEST254: Test NoPeerInvoker always returns PeerRequest error | tests/test_cartridge_runtime.py:327 |
| test255 | `test_255_no_peer_invoker_with_arguments` | TEST255: Test NoPeerInvoker call_with_bytes also returns error | tests/test_cartridge_runtime.py:337 |
| test256 | `test_256_with_manifest_json` | TEST256: Test CartridgeRuntime::with_manifest_json stores manifest data and parses when valid | tests/test_cartridge_runtime.py:346 |
| test257 | `test_257_new_with_invalid_json` | TEST257: Test CartridgeRuntime::new with invalid JSON still creates runtime (manifest is None) | tests/test_cartridge_runtime.py:357 |
| test258 | `test_258_with_manifest_struct` | TEST258: Test CartridgeRuntime::with_manifest creates runtime with valid manifest data | tests/test_cartridge_runtime.py:364 |
| test259 | `test_259_extract_effective_payload_non_cbor` | TEST259: Test extract_effective_payload with non-CBOR content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:373 |
| test260 | `test_260_extract_effective_payload_no_content_type` | TEST260: Test extract_effective_payload with None content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:381 |
| test261 | `test_261_extract_effective_payload_cbor_match` | TEST261: Test extract_effective_payload with CBOR content extracts matching argument value | tests/test_cartridge_runtime.py:389 |
| test262 | `test_262_extract_effective_payload_cbor_no_match` | TEST262: Test extract_effective_payload with CBOR content fails when no argument matches expected input | tests/test_cartridge_runtime.py:401 |
| test263 | `test_263_extract_effective_payload_invalid_cbor` | TEST263: Test extract_effective_payload with invalid CBOR bytes returns deserialization error | tests/test_cartridge_runtime.py:411 |
| test264 | `test_264_extract_effective_payload_cbor_not_array` | TEST264: Test extract_effective_payload with CBOR non-array (e.g. map) returns error | tests/test_cartridge_runtime.py:418 |
| test266 | `test_266_cli_stream_emitter_construction` | TEST266: Test CliFrameSender wraps CliStreamEmitter correctly (basic construction) | tests/test_cartridge_runtime.py:426 |
| test268 | `test_268_runtime_error_display` | TEST268: Test RuntimeError variants display correct messages | tests/test_cartridge_runtime.py:435 |
| test270 | `test_270_multiple_handlers` | TEST270: Test registering multiple Op handlers for different caps and finding each independently | tests/test_cartridge_runtime.py:456 |
| test271 | `test_271_handler_replacement` | TEST271: Test Op handler replacing an existing registration for the same cap URN | tests/test_cartridge_runtime.py:483 |
| test272 | `test_272_extract_effective_payload_multiple_args` | TEST272: Test extract_effective_payload CBOR with multiple arguments selects the correct one | tests/test_cartridge_runtime.py:514 |
| test273 | `test_273_extract_effective_payload_binary_value` | TEST273: Test extract_effective_payload with binary data in CBOR value (not just text) | tests/test_cartridge_runtime.py:536 |
| test274 | `test_274_cap_argument_value_new` | TEST274: Test CapArgumentValue::new stores media_urn and raw byte value | tests/test_caller.py:143 |
| test275 | `test_275_cap_argument_value_from_str` | TEST275: Test CapArgumentValue::from_str converts string to UTF-8 bytes | tests/test_caller.py:154 |
| test276 | `test_276_cap_argument_value_as_str_success` | TEST276: Test CapArgumentValue::value_as_str succeeds for UTF-8 data | tests/test_caller.py:166 |
| test277 | `test_277_cap_argument_value_as_str_fails_binary` | TEST277: Test CapArgumentValue::value_as_str fails for non-UTF-8 binary data | tests/test_caller.py:172 |
| test278 | `test_278_cap_argument_value_empty` | TEST278: Test CapArgumentValue::new with empty value stores empty vec | tests/test_caller.py:182 |
| test279 | `test_279_cap_argument_value_clone` | TEST279: Test CapArgumentValue Clone produces independent copy with same data | tests/test_caller.py:190 |
| test280 | `test_280_cap_argument_value_debug` | TEST280: Test CapArgumentValue Debug format includes media_urn and value | tests/test_caller.py:205 |
| test281 | `test_281_cap_argument_value_media_urn_types` | TEST281: Test CapArgumentValue::new accepts Into<String> for media_urn (String and &str) | tests/test_caller.py:223 |
| test282 | `test_282_cap_argument_value_unicode` | TEST282: Test CapArgumentValue::from_str with Unicode string preserves all characters | tests/test_caller.py:236 |
| test283 | `test_283_cap_argument_value_large_binary` | TEST283: Test CapArgumentValue with large binary payload preserves all bytes | tests/test_caller.py:246 |
| test284 | `test_284_handshake_host_cartridge` | TEST284: Handshake exchanges HELLO frames, negotiates limits | tests/test_cbor_integration.py:57 |
| test285 | `test_285_request_response_simple` | TEST285: Simple request-response flow (REQ → END with payload) | tests/test_cbor_integration.py:92 |
| test286 | `test_286_streaming_chunks` | TEST286: Streaming response with multiple CHUNK frames | tests/test_cbor_integration.py:132 |
| test287 | `test_287_heartbeat_from_host` | TEST287: Host-initiated heartbeat | tests/test_cbor_integration.py:184 |
| test288 | `test_288_media_documentation_propagates_through_resolve` | TEST288: Documentation propagates from MediaDef through resolve_media_urn into ResolvedMediaDef. This is the resolution path used by every consumer that asks the registry for a media def — info panels, the cap navigator, the UI — so a regression here makes the new field invisible everywhere. | tests/test_media_def.py:547 |
| test289 | `test_289_media_def_def_documentation_round_trip` | TEST289: MediaDef serializes documentation only when present and round-trips losslessly. Mirrors TEST1127/1128 for the cap side. | tests/test_media_def.py:568 |
| test290 | `test_290_limits_negotiation` | TEST290: Limit negotiation picks minimum | tests/test_cbor_integration.py:222 |
| test291 | `test_291_binary_payload_roundtrip` | TEST291: Binary payload roundtrip (all 256 byte values) | tests/test_cbor_integration.py:254 |
| test292 | `test_292_message_id_uniqueness` | TEST292: Sequential requests get distinct MessageIds | tests/test_cbor_integration.py:299 |
| test293 | `test_293_cartridge_runtime_handler_registration` | TEST293: Test CartridgeRuntime Op registration and lookup by exact and non-existent cap URN | tests/test_cartridge_runtime.py:271 |
| test299 | `test_299_empty_payload_roundtrip` | TEST299: Empty payload request/response roundtrip | tests/test_cbor_integration.py:340 |
| test300 | `test_300_get_cartridge_by_id_channel_isolation` | TEST300: A cartridge with the same id can independently exist in both channels. Each lookup must return the channel-specific entry. | tests/test_cartridge_repo.py:295 |
| test301 | `test_301_transform_walks_both_channels_release_first` | TEST301: Walking both channels produces release entries first. | tests/test_cartridge_repo.py:257 |
| test304 | `test_304_media_availability_output_constant` | TEST304: Test MEDIA_AVAILABILITY_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:257 |
| test305 | `test_305_media_path_output_constant` | TEST305: Test MEDIA_PATH_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:265 |
| test306 | `test_306_availability_and_path_output_distinct` | TEST306: Test MEDIA_AVAILABILITY_OUTPUT and MEDIA_PATH_OUTPUT are distinct URNs | tests/test_media_urn.py:273 |
| test307 | `test_307_model_availability_urn` | TEST307: Test model_availability_urn builds valid cap URN with correct op and media defs | tests/test_standard_caps.py:35 |
| test308 | `test_308_model_path_urn` | TEST308: Test model_path_urn builds valid cap URN with correct op and media defs | tests/test_standard_caps.py:43 |
| test309 | `test_309_model_availability_and_path_are_distinct` | TEST309: Test model_availability_urn and model_path_urn produce distinct URNs | tests/test_standard_caps.py:51 |
| test310 | `test_310_llm_generate_text_urn_shape` | TEST310: llm_generate_text_urn() produces a valid cap URN with a UTF-8 text input and plain-text terminal output. | tests/test_standard_caps.py:58 |
| test312 | `test_312_all_urn_builders_produce_valid_urns` | TEST312: Test all URN builders produce parseable cap URNs | tests/test_standard_caps.py:68 |
| test319 | `test_319_update_cache_rejects_malformed_cap_urn` | TEST319: A registry response with a malformed cap URN inside cap_groups must propagate as ParseError when indexed into the cache, not silently disappear. | tests/test_cartridge_repo.py:515 |
| test320 | `test_320_construct_cartridge_info_and_verify_fields` | TEST320: Construct CartridgeInfo and verify round-trip of fields. | tests/test_cartridge_repo.py:154 |
| test321 | `test_321_cartridge_info_is_signed` | TEST321: is_signed() requires both team_id and signed_at to be non-empty. | tests/test_cartridge_repo.py:166 |
| test322 | `test_322_cartridge_info_build_for_platform` | TEST322: build_for_platform returns the matching build for the latest version, None for an unknown platform. | tests/test_cartridge_repo.py:180 |
| test323 | `test_323_cartridge_repo_server_validate_registry` | TEST323: CartridgeRepoServer requires schema 5.0 and rejects older. | tests/test_cartridge_repo.py:194 |
| test324 | `test_324_cartridge_repo_server_transform_to_array` | TEST324: CartridgeRepoServer transforms a v4.0 entry into a flat CartridgeInfo, preserving cap_groups verbatim. | tests/test_cartridge_repo.py:230 |
| test325 | `test_325_cartridge_repo_server_get_cartridges` | TEST325: get_cartridges() wraps the transformed array in the response envelope. | tests/test_cartridge_repo.py:269 |
| test326 | `test_326_cartridge_repo_server_get_cartridge_by_id` | TEST326: get_cartridge_by_id requires a channel and returns Some for a known (channel, id), None otherwise. The same id looked up in the wrong channel must miss — channels are independent namespaces. | tests/test_cartridge_repo.py:282 |
| test327 | `test_327_cartridge_repo_server_search_cartridges` | TEST327: search_cartridges matches against name/description/tags and cap titles, but never against cap URN strings. | tests/test_cartridge_repo.py:313 |
| test328 | `test_328_cartridge_repo_server_get_by_category` | TEST328: get_cartridges_by_category filters on the categories string list. | tests/test_cartridge_repo.py:339 |
| test329 | `test_329_cartridge_repo_server_get_by_cap` | TEST329: get_cartridges_by_cap parses the request URN and matches each cartridge cap via the conforms_to predicate — not string equality, and the `op` tag has no functional role. A request URN whose tags appear in different declared order than the cap's still resolves because the predicate is order-independent. | tests/test_cartridge_repo.py:357 |
| test330 | `test_330_cartridge_repo_client_update_cache` | TEST330: update_cache populates the cartridge map keyed by (channel, id) and the cap-to-cartridge index keyed by normalized URNs. | tests/test_cartridge_repo.py:385 |
| test331 | `test_331_cartridge_repo_client_get_suggestions` | TEST331: get_suggestions_for_cap returns a suggestion with channel propagated from the source cartridge. | tests/test_cartridge_repo.py:403 |
| test332 | `test_332_cartridge_repo_client_get_cartridge` | TEST332: get_cartridge requires a (channel, id) pair and returns the cached entry for known pairs, None otherwise. The same id in the wrong channel must miss. | tests/test_cartridge_repo.py:429 |
| test333 | `test_333_cartridge_repo_client_get_all_caps` | TEST333: get_all_available_caps returns the deduplicated set of normalized URNs across cartridges. | tests/test_cartridge_repo.py:448 |
| test334 | `test_334_cartridge_repo_client_needs_sync` | TEST334: needs_sync returns true on an empty cache, false right after a successful update. | tests/test_cartridge_repo.py:476 |
| test335 | `test_335_cartridge_repo_server_client_integration` | TEST335: A v4.0 nested registry round-trips through Server → CartridgeInfo → fingerprint, preserving the cap_groups structure and the signed flag. | tests/test_cartridge_repo.py:486 |
| test336 | `test_336_file_path_reads_file_passes_bytes` | TEST336: Single file-path arg with stdin source reads file and passes bytes to handler | tests/test_cartridge_runtime.py:569 |
| test337 | `test_337_file_path_without_stdin_passes_string` | TEST337: file-path arg without stdin source passes path as string (no conversion) | tests/test_cartridge_runtime.py:632 |
| test338 | `test_338_file_path_via_cli_flag` | TEST338: file-path arg reads file via --file CLI flag | tests/test_cartridge_runtime.py:660 |
| test339 | `test_339_file_path_array_glob_expansion` | TEST339: file-path-array reads multiple files with glob pattern | tests/test_cartridge_runtime.py:689 |
| test340 | `test_340_file_not_found_clear_error` | TEST340: File not found error provides clear message | tests/test_cartridge_runtime.py:729 |
| test341 | `test_341_stdin_precedence_over_file_path` | TEST341: stdin takes precedence over file-path in source order | tests/test_cartridge_runtime.py:759 |
| test342 | `test_342_file_path_position_zero_reads_first_arg` | TEST342: file-path with position 0 reads first positional arg as file | tests/test_cartridge_runtime.py:792 |
| test343 | `test_343_non_file_path_args_unaffected` | TEST343: Non-file-path args are not affected by file reading | tests/test_cartridge_runtime.py:821 |
| test346 | `test_346_large_file_reads_successfully` | TEST346: Large file (1MB) reads successfully | tests/test_cartridge_runtime.py:913 |
| test347 | `test_347_empty_file_reads_as_empty_bytes` | TEST347: Empty file reads as empty bytes | tests/test_cartridge_runtime.py:946 |
| test348 | `test_348_file_path_conversion_respects_source_order` | TEST348: file-path conversion respects source order | tests/test_cartridge_runtime.py:975 |
| test349 | `test_349_file_path_multiple_sources_fallback` | TEST349: file-path arg with multiple sources tries all in order | tests/test_cartridge_runtime.py:1007 |
| test350 | `test_350_full_cli_mode_with_file_path_integration` | TEST350: Integration test - full CLI mode invocation with file-path | tests/test_cartridge_runtime.py:1038 |
| test352 | `test_352_file_permission_denied_clear_error` | TEST352: file permission denied error is clear (Unix-specific) | tests/test_cartridge_runtime.py:1134 |
| test353 | `test_353_cbor_payload_format_consistency` | TEST353: CBOR payload format matches between CLI and CBOR mode | tests/test_cartridge_runtime.py:1173 |
| test354 | `test_354_glob_pattern_no_matches_fails_hard` | TEST354: Glob pattern with no matches fails hard (NO FALLBACK). Silent empty results mask real user mistakes (typo'd path, wrong directory), so the runtime surfaces them rather than returning an empty array. | tests/test_cartridge_runtime.py:1204 |
| test355 | `test_355_glob_pattern_skips_directories` | TEST355: Glob pattern skips directories | tests/test_cartridge_runtime.py:1235 |
| test356 | `test_356_multiple_glob_patterns_combined` | TEST356: Multiple glob patterns combined | tests/test_cartridge_runtime.py:1274 |
| test357 | `test_357_symlinks_followed` | TEST357: Symlinks are followed when reading files | tests/test_cartridge_runtime.py:1318 |
| test358 | `test_358_binary_file_non_utf8` | TEST358: Binary file with non-UTF8 data reads correctly | tests/test_cartridge_runtime.py:1353 |
| test359 | `test_359_invalid_glob_pattern_fails` | TEST359: Invalid glob pattern fails with clear error | tests/test_cartridge_runtime.py:1385 |
| test360 | `test_360_extract_effective_payload_with_file_data` | TEST360: Extract effective payload handles file-path data correctly | tests/test_cartridge_runtime.py:1418 |
| test361 | `test_361_cli_mode_file_path` | TEST361: CLI mode with file path - pass file path as command-line argument | tests/test_cartridge_runtime.py:1454 |
| test362 | `test_362_cli_mode_piped_binary` | TEST362: CLI mode with binary piped in - pipe binary data via stdin This test simulates real-world conditions: - Pure binary data piped to stdin (NOT CBOR) - CLI mode detected (command arg present) - Cap accepts stdin source - Binary is chunked on-the-fly and accumulated - Handler receives complete CBOR payload | tests/test_cartridge_runtime.py:1491 |
| test363 | `test_363_cbor_mode_chunked_content` | TEST363: CBOR mode with chunked content - send file content streaming as chunks | tests/test_cartridge_runtime.py:1538 |
| test364 | `test_364_cbor_mode_file_path` | TEST364: CBOR mode with file path - send file path in CBOR arguments (auto-conversion) | tests/test_cartridge_runtime.py:1619 |
| test365 | `test_365_stream_start_frame` | TEST365: Frame::stream_start stores request_id, stream_id, and media_urn | tests/test_cbor_frame.py:427 |
| test366 | `test_366_stream_end_frame` | TEST366: Frame::stream_end stores request_id and stream_id | tests/test_cbor_frame.py:442 |
| test367 | `test_367_stream_start_with_empty_stream_id` | TEST367: StreamStart frame with empty stream_id still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:458 |
| test368 | `test_368_stream_start_with_empty_media_urn` | TEST368: StreamStart frame with empty media_urn still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:469 |
| test389 | `test_389_stream_start_roundtrip` | TEST389: StreamStart encode/decode roundtrip preserves stream_id and media_urn | tests/test_cbor_io.py:1001 |
| test390 | `test_390_stream_end_roundtrip` | TEST390: StreamEnd encode/decode roundtrip preserves stream_id, no media_urn | tests/test_cbor_io.py:1017 |
| test395 | `test_395_build_payload_small` | TEST395: Small payload (< max_chunk) produces correct CBOR arguments | tests/test_cartridge_runtime.py:1654 |
| test396 | `test_396_build_payload_large` | TEST396: Large payload (> max_chunk) accumulates across chunks correctly | tests/test_cartridge_runtime.py:1686 |
| test397 | `test_397_build_payload_empty` | TEST397: Empty reader produces valid empty CBOR arguments | tests/test_cartridge_runtime.py:1713 |
| test398 | `test_398_build_payload_io_error` | TEST398: IO error from reader propagates as RuntimeError::Io | tests/test_cartridge_runtime.py:1744 |
| test399 | `test_399_relay_notify_discriminant_roundtrip` | TEST399: Verify RelayNotify frame type discriminant roundtrips through u8 (value 10) | tests/test_cbor_frame.py:480 |
| test400 | `test_400_relay_state_discriminant_roundtrip` | TEST400: Verify RelayState frame type discriminant roundtrips through u8 (value 11) | tests/test_cbor_frame.py:489 |
| test401 | `test_401_relay_notify_factory_and_accessors` | TEST401: Verify relay_notify factory stores manifest and limits, and accessors extract them | tests/test_cbor_frame.py:498 |
| test402 | `test_402_relay_state_factory_and_payload` | TEST402: Verify relay_state factory stores resource payload in frame payload field | tests/test_cbor_frame.py:526 |
| test403 | `test_403_frame_type_one_past_cancel` | TEST403: Verify from_u8 returns None for values past the last valid frame type | tests/test_cbor_frame.py:537 |
| test404 | `test_404_slave_sends_relay_notify_on_connect` | TEST404: Slave sends RelayNotify on connect (initial_notify parameter) | tests/test_cartridge_relay.py:22 |
| test405 | `test_405_master_reads_relay_notify` | TEST405: Master reads RelayNotify and extracts manifest + limits | tests/test_cartridge_relay.py:56 |
| test406 | `test_406_slave_stores_relay_state` | TEST406: Slave stores RelayState from master | tests/test_cartridge_relay.py:84 |
| test407 | `test_407_protocol_frames_pass_through` | TEST407: Protocol frames pass through slave transparently (both directions) | tests/test_cartridge_relay.py:121 |
| test408 | `test_408_relay_frames_not_forwarded` | TEST408: RelayNotify/RelayState are NOT forwarded through relay | tests/test_cartridge_relay.py:210 |
| test409 | `test_409_slave_injects_relay_notify_midstream` | TEST409: Slave can inject RelayNotify mid-stream (cap change) | tests/test_cartridge_relay.py:277 |
| test410 | `test_410_master_receives_updated_relay_notify` | TEST410: Master receives updated RelayNotify (cap change callback via read_frame) | tests/test_cartridge_relay.py:326 |
| test411 | `test_411_socket_close_detection` | TEST411: Socket close detection (both directions) | tests/test_cartridge_relay.py:387 |
| test412 | `test_412_bidirectional_concurrent_flow` | TEST412: Bidirectional concurrent frame flow through relay | tests/test_cartridge_relay.py:421 |
| test413 | `test_413_register_cartridge_adds_cap_table` | TEST413: Register cartridge adds entries to cap_table | tests/test_cartridge_host.py:396 |
| test414 | `test_414_relay_slave_forwards_host_relay_notify` | TEST414: RelaySlave forwards host-originated RelayNotify (local -> socket), dropping only RelayState. The CartridgeHost publishes capability updates (the installed-cartridge inventory the engine routes by) as RelayNotify frames through the slave's local->socket path. Regression lock for the drift (seen in the go mirror) where the slave dropped RelayNotify too, stranding the host's inventory so the engine never learned the cartridge existed. Mirrors the reference RelaySlave Task 2 forwarding. | tests/test_cartridge_relay.py:525 |
| test415 | `test_415_req_triggers_spawn` | TEST415: REQ for known cap triggers spawn attempt (verified by expected spawn error for non-existent binary) | tests/test_cartridge_host.py:445 |
| test416 | `test_416_attach_cartridge_handshake` | TEST416: Attach cartridge performs HELLO handshake, extracts manifest, updates capabilities | tests/test_cartridge_host.py:479 |
| test417 | `test_417_route_req_by_cap_urn` | TEST417: Route REQ to correct cartridge by cap_urn (with two attached cartridges) | tests/test_cartridge_host.py:507 |
| test418 | `test_418_route_continuation_by_req_id` | TEST418: Route STREAM_START/CHUNK/STREAM_END/END by req_id (not cap_urn) Verifies that after the initial REQ→cartridge routing, all subsequent continuation frames with the same req_id are routed to the same cartridge — even though no cap_urn is present on those frames. | tests/test_cartridge_host.py:568 |
| test419 | `test_419_heartbeat_local_handling` | TEST419: Cartridge HEARTBEAT handled locally (not forwarded to relay) | tests/test_cartridge_host.py:627 |
| test420 | `test_420_cartridge_frames_forwarded_to_relay` | TEST420: Cartridge non-HELLO/non-HB frames forwarded to relay (pass-through) | tests/test_cartridge_host.py:689 |
| test421 | `test_421_cartridge_death_updates_caps` | TEST421: Cartridge death updates capability list (caps removed) | tests/test_cartridge_host.py:747 |
| test422 | `test_422_cartridge_death_sends_err` | TEST422: Cartridge death sends ERR for all pending requests via relay | tests/test_cartridge_host.py:788 |
| test423 | `test_423_multi_cartridge_distinct_caps` | TEST423: Multiple cartridges registered with distinct caps route independently | tests/test_cartridge_host.py:836 |
| test424 | `test_424_concurrent_requests_same_cartridge` | TEST424: Concurrent requests to the same cartridge are handled independently | tests/test_cartridge_host.py:917 |
| test425 | `test_425_find_cartridge_for_cap_unknown` | TEST425: find_cartridge_for_cap returns None for unregistered cap | tests/test_cartridge_host.py:984 |
| test426 | `test_426_single_master_req_response` | TEST426: Single master REQ/response routing | tests/test_relay_switch.py:159 |
| test427 | `test_427_multi_master_cap_routing` | TEST427: Multi-master cap routing | tests/test_relay_switch.py:213 |
| test428 | `test_428_unknown_cap_returns_error` | TEST428: Unknown cap returns error | tests/test_relay_switch.py:299 |
| test429 | `test_429_find_master_for_cap` | TEST429: Cap routing logic (find_master_for_cap) | tests/test_relay_switch.py:334 |
| test430 | `test_430_tie_breaking_same_cap_multiple_masters` | TEST430: Tie-breaking (same cap on multiple masters - first match wins, routing is consistent) | tests/test_relay_switch.py:516 |
| test431 | `test_431_continuation_frame_routing` | TEST431: Continuation frame routing (CHUNK, END follow REQ) | tests/test_relay_switch.py:594 |
| test432 | `test_432_empty_masters_list_error` | TEST432: Empty masters list creates empty switch, add_master works | tests/test_relay_switch.py:657 |
| test433 | `test_433_capability_aggregation_deduplicates` | TEST433: Capability aggregation deduplicates caps | tests/test_relay_switch.py:665 |
| test434 | `test_434_limits_negotiation_minimum` | TEST434: Limits negotiation takes minimum | tests/test_relay_switch.py:733 |
| test435 | `test_435_urn_matching_exact_and_accepts` | TEST435: URN matching (exact vs accepts()) | tests/test_relay_switch.py:778 |
| test436 | `test_436_compute_checksum` | TEST436: Verify FNV-1a checksum function produces consistent results | tests/test_cbor_frame.py:573 |
| test437 | `test_437_preferred_cap_routes_to_generic` | TEST437: find_master_for_cap with preferred_cap routes to generic handler With is_dispatchable semantics: - Generic candidate (in=media:) CAN dispatch specific request (in="media:ext=pdf") because media: (wildcard) accepts any input type - Preference routes to preferred among dispatchable candidates | tests/test_relay_switch.py:395 |
| test438 | `test_438_preferred_cap_falls_back_when_not_comparable` | TEST438: find_master_for_cap with preference falls back to closest-specificity when preferred cap is not in the comparable set | tests/test_relay_switch.py:435 |
| test439 | `test_439_generic_candidate_can_dispatch_specific_request` | TEST439: Generic candidate CAN dispatch specific request (but only matches if no more specific candidate exists) With is_dispatchable: generic candidate (in=media:) CAN handle specific request (in="media:ext=pdf") because media: accepts any input type. With preference, can route to generic even when more specific exists. | tests/test_relay_switch.py:475 |
| test440 | `test_440_chunk_index_checksum_roundtrip` | TEST440: CHUNK frame with chunk_index and checksum roundtrips through encode/decode | tests/test_cbor_io.py:1066 |
| test441 | `test_441_stream_end_chunk_count_roundtrip` | TEST441: STREAM_END frame with chunk_count roundtrips through encode/decode | tests/test_cbor_io.py:1086 |
| test442 | `test_442_seq_assigner_monotonic_same_rid` | TEST442: SeqAssigner assigns seq 0,1,2,3 for consecutive frames with same RID | tests/test_cbor_frame.py:593 |
| test443 | `test_443_seq_assigner_independent_rids` | TEST443: SeqAssigner maintains independent counters for different RIDs | tests/test_cbor_frame.py:614 |
| test444 | `test_444_seq_assigner_skips_non_flow` | TEST444: SeqAssigner skips non-flow frames (Heartbeat, RelayNotify, RelayState, Hello) | tests/test_cbor_frame.py:639 |
| test445 | `test_445_seq_assigner_remove_by_flow_key` | TEST445: SeqAssigner.remove with FlowKey(rid, None) resets that flow; FlowKey(rid, Some(xid)) is unaffected | tests/test_cbor_frame.py:653 |
| test446 | `test_446_seq_assigner_mixed_types` | TEST446: SeqAssigner handles mixed frame types (REQ, CHUNK, LOG, END) for same RID | tests/test_cbor_frame.py:722 |
| test447 | `test_447_flow_key_with_xid` | TEST447: FlowKey::from_frame extracts (rid, Some(xid)) when routing_id present | tests/test_cbor_frame.py:743 |
| test448 | `test_448_flow_key_without_xid` | TEST448: FlowKey::from_frame extracts (rid, None) when routing_id absent | tests/test_cbor_frame.py:756 |
| test449 | `test_449_flow_key_equality` | TEST449: FlowKey equality: same rid+xid equal, different xid different key | tests/test_cbor_frame.py:766 |
| test450 | `test_450_flow_key_hash_lookup` | TEST450: FlowKey hash: same keys hash equal (HashMap lookup) | tests/test_cbor_frame.py:779 |
| test451 | `test_451_reorder_buffer_in_order` | TEST451: ReorderBuffer in-order delivery: seq 0,1,2 delivered immediately | tests/test_cbor_frame.py:803 |
| test452 | `test_452_reorder_buffer_out_of_order` | TEST452: ReorderBuffer out-of-order: seq 1 then 0 delivers both in order | tests/test_cbor_frame.py:818 |
| test453 | `test_453_reorder_buffer_gap_fill` | TEST453: ReorderBuffer gap fill: seq 0,2,1 delivers 0, buffers 2, then delivers 1+2 | tests/test_cbor_frame.py:834 |
| test454 | `test_454_reorder_buffer_stale_seq` | TEST454: ReorderBuffer stale seq is hard error | tests/test_cbor_frame.py:851 |
| test455 | `test_455_reorder_buffer_overflow` | TEST455: ReorderBuffer overflow triggers protocol error | tests/test_cbor_frame.py:864 |
| test456 | `test_456_reorder_buffer_independent_flows` | TEST456: Multiple concurrent flows reorder independently | tests/test_cbor_frame.py:877 |
| test457 | `test_457_reorder_buffer_cleanup` | TEST457: cleanup_flow removes state; new frames start at seq 0 | tests/test_cbor_frame.py:896 |
| test458 | `test_458_reorder_buffer_non_flow_bypass` | TEST458: Non-flow frames bypass reorder entirely | tests/test_cbor_frame.py:914 |
| test459 | `test_459_reorder_buffer_end_frame` | TEST459: Terminal END frame flows through correctly | tests/test_cbor_frame.py:928 |
| test460 | `test_460_reorder_buffer_err_frame` | TEST460: Terminal ERR frame flows through correctly | tests/test_cbor_frame.py:942 |
| test461 | `test_461_write_chunked_seq_zero` | TEST461: write_chunked produces frames with seq=0; SeqAssigner assigns at output stage | tests/test_cbor_io.py:329 |
| test462 | `test_462_attached_cartridge_identity_from_manifest` | TEST462: An attached cartridge (pre-connected over raw streams, no on-disk anchor) gets a resolvable install identity derived from its HELLO manifest. Identity gates advertisement, so a None record means the cartridge is silently dropped from every RelayNotify and the engine can never route to it. Locks the attached-cartridge identity path (the swift mirror regressed here: attached cartridges returned nil and never reached the engine). Mirrors the reference installed_cartridge_record_from_manifest. | tests/test_cartridge_host_runtime.py:415 |
| test472 | `test_472_handshake_negotiates_reorder_buffer` | TEST472: Handshake negotiates max_reorder_buffer (minimum of both sides) | tests/test_cbor_io.py:356 |
| test473 | `test_473_cap_discard_parses_as_valid_urn` | TEST473: CAP_DISCARD parses as valid CapUrn with in=media: and out=media:void | tests/test_standard_caps.py:88 |
| test474 | `test_474_cap_discard_accepts_specific_void_cap` | TEST474: CAP_DISCARD accepts specific-input/void-output caps | tests/test_standard_caps.py:95 |
| test475 | `test_475_validate_passes_with_identity` | TEST475: validate() passes with CAP_IDENTITY in a cap group | tests/test_manifest.py:274 |
| test476 | `test_476_validate_fails_without_identity` | TEST476: validate() fails without CAP_IDENTITY | tests/test_manifest.py:285 |
| test478 | `test_478_auto_registers_identity_and_discard_handlers` | TEST478: CartridgeRuntime auto-registers identity and discard handlers on construction | tests/test_cartridge_runtime.py:1765 |
| test479 | `test_479_custom_identity_overrides_default` | TEST479: Custom identity Op overrides auto-registered default | tests/test_cartridge_runtime.py:1774 |
| test481 | `test_481_verify_identity_succeeds` | TEST481: verify_identity succeeds with standard identity echo handler | tests/test_cbor_io.py:515 |
| test482 | `test_482_verify_identity_fails_on_err` | TEST482: verify_identity fails when cartridge returns ERR on identity call | tests/test_cbor_io.py:553 |
| test483 | `test_483_verify_identity_fails_on_close` | TEST483: verify_identity fails when connection closes before response | tests/test_cbor_io.py:582 |
| test485 | `test_485_attach_cartridge_identity_verification_succeeds` | TEST485: attach_cartridge completes identity verification with working cartridge | tests/test_cartridge_host.py:177 |
| test486 | `test_486_attach_cartridge_identity_verification_fails` | TEST486: attach_cartridge rejects cartridge that fails identity verification | tests/test_cartridge_host.py:200 |
| test487 | `test_487_relay_switch_identity_verification_succeeds` | TEST487: RelaySwitch construction verifies identity through relay chain | tests/test_relay_switch.py:833 |
| test488 | `test_488_relay_switch_identity_verification_fails` | TEST488: RelaySwitch construction fails when master's identity verification fails | tests/test_relay_switch.py:850 |
| test489 | `test_489_full_path_identity_verification` | TEST489: Full path identity verification: engine → host (attach_cartridge) → cartridge | tests/test_cartridge_host.py:227 |
| test490 | `test_490_identity_verification_multiple_cartridges` | TEST490: Identity verification with multiple cartridges through single relay Both cartridges must pass identity verification independently before any real requests are routed. | tests/test_cartridge_host.py:278 |
| test491 | `test_491_chunk_requires_chunk_index_and_checksum` | TEST491: Frame::chunk constructor requires and sets chunk_index and checksum | tests/test_cbor_frame.py:964 |
| test492 | `test_492_stream_end_requires_chunk_count` | TEST492: Frame::stream_end constructor requires and sets chunk_count | tests/test_cbor_frame.py:978 |
| test493 | `test_493_compute_checksum_fnv1a_test_vectors` | TEST493: compute_checksum produces correct FNV-1a hash for known test vectors | tests/test_cbor_frame.py:988 |
| test494 | `test_494_compute_checksum_deterministic` | TEST494: compute_checksum is deterministic | tests/test_cbor_frame.py:995 |
| test495 | `test_495_cbor_rejects_chunk_without_chunk_index` | TEST495: CBOR decode REJECTS CHUNK frame missing chunk_index field | tests/test_cbor_frame.py:1005 |
| test496 | `test_496_cbor_rejects_chunk_without_checksum` | TEST496: CBOR decode REJECTS CHUNK frame missing checksum field | tests/test_cbor_frame.py:1024 |
| test497 | `test_497_chunk_corrupted_payload_rejected` | TEST497: Verify CHUNK frame with corrupted payload is rejected by checksum | tests/test_cbor_frame.py:1041 |
| test498 | `test_498_routing_id_cbor_roundtrip` | TEST498: routing_id field roundtrips through CBOR encoding | tests/test_cbor_frame.py:1058 |
| test499 | `test_499_chunk_index_checksum_cbor_roundtrip` | TEST499: chunk_index and checksum roundtrip through CBOR encoding | tests/test_cbor_frame.py:1073 |
| test500 | `test_500_chunk_count_cbor_roundtrip` | TEST500: chunk_count roundtrips through CBOR encoding | tests/test_cbor_frame.py:1089 |
| test501 | `test_501_frame_new_initializes_optional_fields_none` | TEST501: Frame::new initializes new fields to None | tests/test_cbor_frame.py:1102 |
| test502 | `test_502_keys_module_new_field_constants` | TEST502: Keys module has constants for new fields | tests/test_cbor_frame.py:1112 |
| test503 | `test_503_compute_checksum_empty_data` | TEST503: compute_checksum handles empty data correctly | tests/test_cbor_frame.py:1120 |
| test504 | `test_504_compute_checksum_large_payload` | TEST504: compute_checksum handles large payloads without overflow | tests/test_cbor_frame.py:1126 |
| test505 | `test_505_chunk_with_offset_sets_chunk_index` | TEST505: chunk_with_offset sets chunk_index correctly | tests/test_cbor_frame.py:1136 |
| test506 | `test_506_compute_checksum_different_data_different_hash` | TEST506: Different data produces different checksums | tests/test_cbor_frame.py:1159 |
| test507 | `test_507_reorder_buffer_xid_isolation` | TEST507: ReorderBuffer isolates flows by XID (routing_id) - same RID different XIDs | tests/test_cbor_frame.py:1170 |
| test508 | `test_508_reorder_buffer_duplicate_buffered_seq` | TEST508: ReorderBuffer rejects duplicate seq already in buffer | tests/test_cbor_frame.py:1198 |
| test509 | `test_509_reorder_buffer_large_gap_rejected` | TEST509: ReorderBuffer handles large seq gaps without DOS | tests/test_cbor_frame.py:1211 |
| test510 | `test_510_reorder_buffer_multiple_gaps` | TEST510: ReorderBuffer with multiple interleaved gaps fills correctly | tests/test_cbor_frame.py:1227 |
| test511 | `test_511_reorder_buffer_cleanup_with_buffered_frames` | TEST511: ReorderBuffer cleanup with buffered frames discards them | tests/test_cbor_frame.py:1259 |
| test512 | `test_512_reorder_buffer_burst_delivery` | TEST512: ReorderBuffer delivers burst of consecutive buffered frames | tests/test_cbor_frame.py:1277 |
| test513 | `test_513_reorder_buffer_mixed_types_same_flow` | TEST513: ReorderBuffer different frame types in same flow maintain order | tests/test_cbor_frame.py:1294 |
| test514 | `test_514_reorder_buffer_xid_cleanup_isolation` | TEST514: ReorderBuffer with XID cleanup doesn't affect different XID | tests/test_cbor_frame.py:1317 |
| test515 | `test_515_reorder_buffer_overflow_error_details` | TEST515: ReorderBuffer overflow error includes diagnostic information | tests/test_cbor_frame.py:1347 |
| test516 | `test_516_reorder_buffer_stale_error_details` | TEST516: ReorderBuffer stale error includes diagnostic information | tests/test_cbor_frame.py:1365 |
| test517 | `test_517_flow_key_none_vs_some_xid` | TEST517: FlowKey with None XID differs from Some(xid) | tests/test_cbor_frame.py:1379 |
| test518 | `test_518_reorder_buffer_empty_ready_vec` | TEST518: ReorderBuffer handles zero-length ready vec correctly | tests/test_cbor_frame.py:1391 |
| test519 | `test_519_reorder_buffer_state_persistence` | TEST519: ReorderBuffer state persists across accept calls | tests/test_cbor_frame.py:1401 |
| test520 | `test_520_reorder_buffer_per_flow_limit` | TEST520: ReorderBuffer max_buffer_per_flow is per-flow not global | tests/test_cbor_frame.py:1418 |
| test521 | `test_521_relay_notify_cbor_roundtrip` | TEST521: RelayNotify CBOR roundtrip preserves manifest and limits | tests/test_cbor_frame.py:1441 |
| test522 | `test_522_relay_state_cbor_roundtrip` | TEST522: RelayState CBOR roundtrip preserves payload | tests/test_cbor_frame.py:1459 |
| test523 | `test_523_relay_notify_not_flow_frame` | TEST523: is_flow_frame returns false for RelayNotify | tests/test_cbor_frame.py:1472 |
| test524 | `test_524_relay_state_not_flow_frame` | TEST524: is_flow_frame returns false for RelayState | tests/test_cbor_frame.py:1478 |
| test525 | `test_525_relay_notify_empty_manifest` | TEST525: RelayNotify with empty manifest is valid | tests/test_cbor_frame.py:1484 |
| test526 | `test_526_relay_state_empty_payload` | TEST526: RelayState with empty payload is valid | tests/test_cbor_frame.py:1491 |
| test527 | `test_527_relay_notify_large_manifest` | TEST527: RelayNotify with large manifest roundtrips correctly | tests/test_cbor_frame.py:1498 |
| test528 | `test_528_relay_frames_use_uint_zero_id` | TEST528: RelayNotify and RelayState use MessageId::Uint(0) | tests/test_cbor_frame.py:1511 |
| test529 | `test_529_input_stream_recv_order` | TEST529: InputStream recv yields chunks in order | tests/test_cartridge_runtime.py:1861 |
| test530 | `test_530_input_stream_collect_bytes` | TEST530: InputStream::collect_bytes concatenates byte chunks | tests/test_cartridge_runtime.py:1875 |
| test531 | `test_531_input_stream_collect_bytes_text` | TEST531: InputStream::collect_bytes handles text chunks | tests/test_cartridge_runtime.py:1881 |
| test532 | `test_532_input_stream_empty` | TEST532: InputStream empty stream produces empty bytes | tests/test_cartridge_runtime.py:1887 |
| test533 | `test_533_input_stream_error_propagation` | TEST533: InputStream propagates errors | tests/test_cartridge_runtime.py:1893 |
| test534 | `test_534_input_stream_media_urn` | TEST534: InputStream::media_urn returns correct URN | tests/test_cartridge_runtime.py:1901 |
| test535 | `test_535_input_package_iteration` | TEST535: InputPackage recv yields streams | tests/test_cartridge_runtime.py:1907 |
| test536 | `test_536_input_package_collect_all_bytes` | TEST536: InputPackage::collect_all_bytes aggregates all streams | tests/test_cartridge_runtime.py:1932 |
| test537 | `test_537_input_package_empty` | TEST537: InputPackage empty package produces empty bytes | tests/test_cartridge_runtime.py:1943 |
| test538 | `test_538_input_package_error_propagation` | TEST538: InputPackage propagates stream errors | tests/test_cartridge_runtime.py:1949 |
| test539 | `test_539_output_stream_sends_stream_start` | TEST539: OutputStream sends STREAM_START on first write | tests/test_cartridge_runtime.py:1966 |
| test540 | `test_540_output_stream_close_sends_stream_end` | TEST540: OutputStream::close sends STREAM_END with correct chunk_count | tests/test_cartridge_runtime.py:1986 |
| test541 | `test_541_output_stream_chunks_large_data` | TEST541: OutputStream chunks large data correctly | tests/test_cartridge_runtime.py:2008 |
| test542 | `test_542_output_stream_empty` | TEST542: OutputStream empty stream sends STREAM_START and STREAM_END only | tests/test_cartridge_runtime.py:2028 |
| test543 | `test_543_peer_call_arg_creates_stream` | TEST543: PeerCall::arg creates OutputStream with correct stream_id | tests/test_cartridge_runtime.py:2048 |
| test544 | `test_544_peer_invoker_sends_end_frame` | TEST544: PeerCall::finish sends END frame | tests/test_cartridge_runtime.py:2063 |
| test545 | `test_545_peer_response_returns_data` | TEST545: PeerCall::finish returns PeerResponse with data | tests/test_cartridge_runtime.py:2088 |
| test546 | `test_546_is_image` | TEST546: is_image returns true only when image marker tag is present | tests/test_media_urn.py:281 |
| test547 | `test_547_is_audio` | TEST547: is_audio returns true only when audio marker tag is present | tests/test_media_urn.py:292 |
| test548 | `test_548_is_video` | TEST548: is_video returns true only when video marker tag is present | tests/test_media_urn.py:303 |
| test549 | `test_549_is_numeric` | TEST549: is_numeric returns true only when numeric marker tag is present | tests/test_media_urn.py:313 |
| test550 | `test_550_is_bool` | TEST550: is_bool returns true only when bool marker tag is present | tests/test_media_urn.py:325 |
| test551 | `test_551_is_file_path` | TEST551: is_file_path returns true for the single file-path media URN, false for everything else. There is no "array" variant — cardinality is carried by is_sequence on the wire, not by URN tags. | tests/test_media_urn.py:337 |
| test555 | `test_555_with_tag_and_without_tag` | TEST555: with_tag adds a tag and without_tag removes it | tests/test_media_urn.py:344 |
| test556 | `test_556_image_media_urn_for_ext` | TEST556: image_media_urn_for_ext creates valid image media URN | tests/test_media_urn.py:360 |
| test557 | `test_557_audio_media_urn_for_ext` | TEST557: audio_media_urn_for_ext creates valid audio media URN | tests/test_media_urn.py:369 |
| test558 | `test_558_predicate_constant_consistency` | TEST558: predicates are consistent with constants — every constant triggers exactly the expected predicates | tests/test_media_urn.py:378 |
| test559 | `test_559_without_tag` | TEST559: without_tag removes tag, rejects structural keys, case-insensitive for keys | tests/test_cap_urn.py:741 |
| test560 | `test_560_with_in_out_spec` | TEST560: with_in_spec and with_out_spec change direction specs | tests/test_cap_urn.py:766 |
| test561 | `test_561_in_out_media_urn` | TEST561: in_media_urn and out_media_urn parse direction specs into MediaUrn | tests/test_cap_urn.py:787 |
| test562 | `test_562_canonical_option` | TEST562: canonical_option returns None for None input, canonical string for Some | tests/test_cap_urn.py:807 |
| test563 | `test_563_find_all_matches` | TEST563: CapMatcher::find_all_matches returns all matching caps sorted by specificity | tests/test_cap_urn.py:844 |
| test564 | `test_564_are_compatible` | TEST564: CapMatcher::are_compatible detects bidirectional overlap | tests/test_cap_urn.py:862 |
| test565 | `test_565_tags_to_string` | TEST565: tags_to_string returns only tags portion without prefix | tests/test_cap_urn.py:885 |
| test566 | `test_566_with_tag_ignores_in_out` | TEST566: with_tag rejects structural keys | tests/test_cap_urn.py:897 |
| test567 | `test_567_str_variants` | TEST567: conforms_to_str and accepts_str work with string arguments | tests/test_cap_urn.py:910 |
| test568 | `test_568_dispatch_output_tag_order` | TEST568: is_dispatchable with different tag order in output spec | tests/test_cap_urn.py:826 |
| test578 | `test_578_rule1_duplicate_media_urns` | TEST578: RULE1 - duplicate media_urns rejected | tests/test_validation.py:142 |
| test579 | `test_579_rule2_empty_sources` | TEST579: RULE2 - empty sources rejected | tests/test_validation.py:155 |
| test580 | `test_580_rule3_different_stdin_urns` | TEST580: RULE3 - multiple stdin sources with different URNs rejected | tests/test_validation.py:167 |
| test581 | `test_581_rule3_same_stdin_urns_ok` | TEST581: RULE3 - multiple stdin sources with same URN is OK | tests/test_validation.py:180 |
| test582 | `test_582_rule4_duplicate_source_type` | TEST582: RULE4 - duplicate source type in single arg rejected | tests/test_validation.py:191 |
| test583 | `test_583_rule5_duplicate_position` | TEST583: RULE5 - duplicate position across args rejected | tests/test_validation.py:203 |
| test584 | `test_584_rule6_position_gap` | TEST584: RULE6 - position gap rejected (0, 2 without 1) | tests/test_validation.py:216 |
| test585 | `test_585_rule6_sequential_ok` | TEST585: RULE6 - sequential positions (0, 1, 2) pass | tests/test_validation.py:229 |
| test586 | `test_586_rule7_position_and_cli_flag` | TEST586: RULE7 - arg with both position and cli_flag rejected | tests/test_validation.py:240 |
| test587 | `test_587_rule9_duplicate_cli_flag` | TEST587: RULE9 - duplicate cli_flag across args rejected | tests/test_validation.py:252 |
| test588 | `test_588_rule10_reserved_cli_flags` | TEST588: RULE10 - reserved cli_flags rejected | tests/test_validation.py:265 |
| test589 | `test_589_all_rules_pass` | TEST589: valid cap args with mixed sources pass all rules | tests/test_validation.py:279 |
| test590 | `test_590_cli_flag_only_args` | TEST590: validate_cap_args accepts cap with only cli_flag sources (no positions) | tests/test_validation.py:290 |
| test591 | `test_591_is_more_specific_than` | TEST591: is_more_specific_than returns true when self has more tags for same request | tests/test_cap.py:197 |
| test592 | `test_592_remove_metadata` | TEST592: remove_metadata adds then removes metadata correctly | tests/test_cap.py:226 |
| test593 | `test_593_registered_by_lifecycle` | TEST593: registered_by lifecycle — set, get, clear | tests/test_cap.py:245 |
| test594 | `test_594_metadata_json_lifecycle` | TEST594: metadata_json lifecycle — set, get, clear | tests/test_cap.py:266 |
| test595 | `test_595_with_args_constructor` | TEST595: with_args constructor stores args correctly | tests/test_cap.py:284 |
| test596 | `test_596_with_full_definition_constructor` | TEST596: with_full_definition constructor stores all fields | tests/test_cap.py:308 |
| test597 | `test_597_cap_arg_with_full_definition` | TEST597: CapArg::with_full_definition stores all fields including optional ones | tests/test_cap.py:339 |
| test598 | `test_598_cap_output_lifecycle` | TEST598: CapOutput lifecycle — set_output, set/clear metadata | tests/test_cap.py:368 |
| test599 | `test_599_is_empty` | TEST599: is_empty returns true for empty response, false for non-empty | tests/test_response.py:61 |
| test600 | `test_600_size` | TEST600: size returns exact byte count for all content types | tests/test_response.py:76 |
| test601 | `test_601_get_content_type` | TEST601: get_content_type returns correct MIME type for each variant | tests/test_response.py:91 |
| test602 | `test_602_as_type_binary_error` | TEST602: as_type on binary response returns error (cannot deserialize binary) | tests/test_response.py:103 |
| test603 | `test_603_as_bool_edge_cases` | TEST603: as_bool handles all accepted truthy/falsy variants and rejects garbage | tests/test_response.py:112 |
| test605 | `test_605_all_coercion_paths_build_valid_urns` | TEST605: all_coercion_paths each entry builds a valid parseable CapUrn | tests/test_standard_caps.py:111 |
| test606 | `test_606_coercion_urn_specs` | TEST606: coercion_urn in/out specs match the type's media URN constant | tests/test_standard_caps.py:128 |
| test607 | `test_607_media_urns_for_extension_unknown` | TEST607: media_urns_for_extension returns error for unknown extension | tests/test_media_def.py:428 |
| test608 | `test_608_media_urns_for_extension_populated` | TEST608: media_urns_for_extension returns URNs after adding a spec with extensions | tests/test_media_def.py:436 |
| test609 | `test_609_get_extension_mappings` | TEST609: get_extension_mappings returns all registered extension→URN pairs. | tests/test_media_def.py:459 |
| test610 | `test_610_get_cached_spec` | TEST610: get_cached_spec returns None for unknown and Some for known | tests/test_media_def.py:480 |
| test612 | `test_612_clear_cache` | TEST612: clear_cache empties the in-memory cache for seeded schemas. | tests/test_media_profile.py:78 |
| test613 | `test_613_validate_cached` | TEST613: validate_cached validates against cached standard schemas | tests/test_media_profile.py:86 |
| test614 | `test_614_registry_creation` | TEST614: Verify registry creation succeeds and cache directory exists | tests/test_registry.py:33 |
| test616 | `test_616_stored_media_def_to_def` | TEST616: Verify StoredMediaDef converts to MediaDef preserving all fields | tests/test_media_def.py:514 |
| test617 | `test_617_normalize_media_urn` | TEST617: Verify normalize_media_urn produces consistent non-empty results | tests/test_media_def.py:533 |
| test618 | `test_618_registry_creation` | TEST618: Verify profile schema registry creation succeeds with temp cache | tests/test_media_def.py:501 |
| test619 | `test_619_fresh_registry_cache_is_empty` | TEST619: A freshly constructed registry has an empty cache. The well-known profile schemas are no longer bundled in the binary; callers must either fetch them on demand or seed via insert_schema. | tests/test_media_profile.py:109 |
| test620 | `test_620_string_validation` | TEST620: Verify string schema validates strings and rejects non-strings | tests/test_media_profile.py:119 |
| test621 | `test_621_integer_validation` | TEST621: Verify integer schema validates integers and rejects floats and strings | tests/test_media_profile.py:126 |
| test622 | `test_622_number_validation` | TEST622: Verify number schema validates integers and floats, rejects strings | tests/test_media_profile.py:134 |
| test623 | `test_623_boolean_validation` | TEST623: Verify boolean schema validates true/false and rejects string "true" | tests/test_media_profile.py:142 |
| test624 | `test_624_object_validation` | TEST624: Verify object schema validates objects and rejects arrays | tests/test_media_profile.py:150 |
| test625 | `test_625_string_array_validation` | TEST625: Verify string array schema validates string arrays and rejects mixed arrays | tests/test_media_profile.py:157 |
| test626 | `test_626_unknown_profile_skips_validation` | TEST626: Verify unknown profile URL skips validation and returns Ok | tests/test_media_profile.py:165 |
| test627 | `test_627_insert_schema_rejects_invalid_schema` | TEST627: insert_schema rejects malformed JSON Schemas instead of caching them. A registry that silently accepted invalid schemas would hide compilation problems until the first validation call. | tests/test_media_profile.py:171 |
| test628 | `test_628_media_urn_constants_format` | TEST628: Verify media URN constants all start with "media:" prefix | tests/test_media_urn.py:486 |
| test629 | `test_629_profile_constants_format` | TEST629: Verify profile URL constants all start with capdag.com schema prefix | tests/test_media_urn.py:494 |
| test630 | `test_630_cartridge_repo_creation` | TEST630: CartridgeRepo creation starts with empty cartridge list. | tests/test_cartridge_repo.py:537 |
| test631 | `test_631_needs_sync_empty_cache` | TEST631: needs_sync returns true with empty cache and non-empty URLs. | tests/test_cartridge_repo.py:543 |
| test632 | `test_632_deserialize_minimal_registry_cap` | TEST632: A registry cap with only the three required fields parses. | tests/test_cartridge_repo.py:549 |
| test633 | `test_633_deserialize_rich_registry_cap` | TEST633: A registry cap with cap_description, args, output all parses. | tests/test_cartridge_repo.py:566 |
| test634 | `test_634_deserialize_cap_group` | TEST634: A registry cap_group parses with caps + adapter_urns. | tests/test_cartridge_repo.py:605 |
| test635 | `test_635_deserialize_cartridge_info_wire_shape` | TEST635: CartridgeInfo deserializes the wire shape exactly as returned by /api/cartridges (camelCase top-level + snake_case cap_groups). Null camelCase string fields fall back to empty. | tests/test_cartridge_repo.py:621 |
| test636 | `test_636_deserialize_cartridge_info_with_null_strings` | TEST636: CartridgeInfo with null version/description/author still deserializes (the null_as_empty_string deserializer is the only tolerated coercion — every other malformed input is a hard error). | tests/test_cartridge_repo.py:661 |
| test637 | `test_637_deserialize_full_registry_response` | TEST637: A full /api/cartridges-shaped response with two cartridges and nested cap_groups round-trips through the response wrapper. | tests/test_cartridge_repo.py:681 |
| test638 | `test_638_no_peer_router_rejects_all` | TEST638: Verify NoPeerRouter rejects all requests with PeerInvokeNotSupported | tests/test_router.py:9 |
| test639 | `test_639_wildcard_001_empty_cap_is_illegal` | TEST639: bare/default top-to-top declared form is illegal | tests/test_cap_urn.py:941 |
| test640 | `test_640_wildcard_in_only_defaults_out` | TEST640: cap:in defaults to the same illegal bare top form | tests/test_cap_urn.py:947 |
| test641 | `test_641_wildcard_out_only_defaults_in` | TEST641: cap:out defaults to the same illegal bare top form | tests/test_cap_urn.py:953 |
| test642 | `test_642_wildcard_in_out_no_values` | TEST642: cap:in;out becomes the same illegal bare top form | tests/test_cap_urn.py:959 |
| test643 | `test_643_wildcard_explicit_asterisk` | TEST643: cap:in=*;out=* is the same illegal bare top form | tests/test_cap_urn.py:965 |
| test644 | `test_644_wildcard_specific_in_wildcard_out` | TEST644: cap:in=media:;out=* is the same illegal bare top form | tests/test_cap_urn.py:971 |
| test645 | `test_645_wildcard_in_specific_out` | TEST645: cap:in=*;out=media:text has wildcard in, specific out | tests/test_cap_urn.py:977 |
| test646 | `test_646_wildcard_invalid_in_spec` | TEST646: cap:in=foo fails (invalid media URN) | tests/test_cap_urn.py:984 |
| test647 | `test_647_wildcard_invalid_out_spec` | TEST647: cap:in=media:;out=bar fails (invalid media URN) | tests/test_cap_urn.py:990 |
| test648 | `test_648_wildcard_010_wildcard_accepts_specific` | TEST648: Wildcard in/out match specific caps | tests/test_cap_urn.py:996 |
| test649 | `test_649_wildcard_011_specificity_scoring` | TEST649: Specificity - wildcard has 0, specific has tag count | tests/test_cap_urn.py:1005 |
| test650 | `test_650_wildcard_012_preserve_other_tags` | TEST650: cap:in=media:;out=media:;test preserves other tags | tests/test_cap_urn.py:1014 |
| test652 | `test_652_wildcard_cap_identity_constant` | TEST652: CAP_IDENTITY constant matches identity caps regardless of string form | tests/test_cap_urn.py:1065 |
| test653 | `test_653_effect_none_illegal_declaration_rejected` | TEST653: invalid effect=none declarations fail at construction | tests/test_cap_urn.py:1086 |
| test658 | `test_658_heartbeat_response` | TEST658: InProcessCartridgeHost handles heartbeat by echoing same ID | tests/test_in_process_host.py:255 |
| test659 | `test_659_handler_error_returns_err_frame` | TEST659: InProcessCartridgeHost handler error returns ERR frame | tests/test_in_process_host.py:281 |
| test660 | `test_660_closest_specificity_routing` | TEST660: InProcessCartridgeHost closest-specificity routing prefers specific over identity | tests/test_in_process_host.py:332 |
| test662 | `test_662_rebuild_capabilities_includes_non_running_cartridges` | TEST662: rebuild_capabilities includes non-running cartridges' caps (each cartridge's `cap_groups` is the source of truth, regardless of whether its process has been spawned yet). | tests/test_cartridge_host.py:1053 |
| test663 | `test_663_hello_failed_cartridge_removed_from_capabilities` | TEST663: Cartridge with hello_failed is permanently removed from capabilities | tests/test_cartridge_host.py:1082 |
| test664 | `test_664_running_cartridge_uses_manifest_caps` | TEST664: Running cartridge uses manifest caps; the post-HELLO cap_groups overwrite the registration-time ones. | tests/test_cartridge_host.py:1108 |
| test665 | `test_665_cap_table_mixed_running_and_non_running` | TEST665: Cap table aggregates caps from every healthy cartridge — attached/running cartridges contribute their post-HELLO cap_groups, registered-but-not-yet-spawned cartridges contribute their probe-time cap_groups. Both flow through the same `cap_urns()` view. | tests/test_cartridge_host.py:1145 |
| test666 | `test_666_preferred_cap_routing` | TEST666: Preferred cap routing - routes to exact equivalent when multiple masters match | tests/test_relay_switch.py:872 |
| test667 | `test_667_verify_chunk_checksum_detects_corruption` | TEST667: verify_chunk_checksum detects corrupted payload | tests/test_cbor_frame.py:544 |
| test668 | `test_668_resolve_slot_with_populated_byte_slot_values` | TEST668: resolve_slot_with_populated_byte_slot_values | tests/test_planner_argument_binding.py:37 |
| test669 | `test_669_resolve_slot_falls_back_to_default` | TEST669: resolve_binding falls back to cap default value when slot has no data | tests/test_planner_argument_binding.py:54 |
| test670 | `test_670_resolve_required_slot_no_value_returns_err` | TEST670: resolve_binding returns error when required slot has no value and no default | tests/test_planner_argument_binding.py:63 |
| test671 | `test_671_resolve_optional_slot_no_value_returns_none` | TEST671: resolve_binding returns None when optional slot has no value and no default | tests/test_planner_argument_binding.py:71 |
| test675 | `test_675_build_request_frames_preserves_media_urn_in_stream_start` | TEST675: build_request_frames with full media URN preserves it in STREAM_START frame | tests/test_caller.py:286 |
| test676 | `test_676_build_request_frames_round_trip_find_stream_succeeds` | TEST676: Full round-trip: build_request_frames → extract streams → find_stream succeeds | tests/test_caller.py:298 |
| test677 | `test_677_base_urn_does_not_match_full_urn_in_find_stream` | TEST677: build_request_frames with BASE URN → find_stream with FULL URN FAILS This documents the root cause of the cartridge_client.rs bug: sender used "media:llm-generation-request" (base), receiver looked for "media:fmt=json;llm-generation-request;record" (full). is_equivalent requires exact tag set match, so base != full. | tests/test_caller.py:312 |
| test678 | `test_678_find_stream_equivalent_urn` | TEST678: find_stream with exact equivalent URN (same tags, different order) succeeds | tests/test_cartridge_runtime.py:2225 |
| test679 | `test_679_find_stream_base_vs_full_fails` | TEST679: find_stream with base URN vs full URN fails — is_equivalent is strict This is the root cause of the cartridge_client.rs bug. Sender sent "media:llm-generation-request" but receiver looked for "media:fmt=json;llm-generation-request;record". | tests/test_cartridge_runtime.py:2234 |
| test680 | `test_680_require_stream_missing_fails` | TEST680: require_stream with missing URN returns hard StreamError | tests/test_cartridge_runtime.py:2243 |
| test681 | `test_681_find_stream_multiple` | TEST681: find_stream with multiple streams returns the correct one | tests/test_cartridge_runtime.py:2253 |
| test682 | `test_682_require_stream_returns_data` | TEST682: require_stream_str returns UTF-8 string for text data | tests/test_cartridge_runtime.py:2265 |
| test683 | `test_683_find_stream_invalid_urn_returns_none` | TEST683: find_stream returns None for invalid media URN string (not a parse error — just None) | tests/test_cartridge_runtime.py:2274 |
| test688 | `test_688_is_multiple` | TEST688: Tests is_multiple method correctly identifies multi-value cardinalities Verifies Single returns false while Sequence and AtLeastOne return true | tests/test_cardinality.py:19 |
| test689 | `test_689_accepts_single` | TEST689: Tests accepts_single method identifies cardinalities that accept single values Verifies Single and AtLeastOne accept singles while Sequence does not | tests/test_cardinality.py:26 |
| test690 | `test_690_compatibility_single_to_single` | TEST690: Tests cardinality compatibility for single-to-single data flow Verifies Direct compatibility when both input and output are Single | tests/test_cardinality.py:33 |
| test691 | `test_691_compatibility_single_to_vector` | TEST691: Tests cardinality compatibility when wrapping single value into array Verifies WrapInArray compatibility when Sequence expects Single input | tests/test_cardinality.py:39 |
| test692 | `test_692_compatibility_vector_to_single` | TEST692: Tests cardinality compatibility when unwrapping array to singles Verifies RequiresFanOut compatibility when Single expects Sequence input | tests/test_cardinality.py:45 |
| test693 | `test_693_compatibility_vector_to_vector` | TEST693: Tests cardinality compatibility for sequence-to-sequence data flow Verifies Direct compatibility when both input and output are Sequence | tests/test_cardinality.py:51 |
| test697 | `test_697_cap_shape_info_one_to_one` | TEST697: Tests CapShapeInfo correctly identifies one-to-one pattern Verifies Single input and Single output result in OneToOne pattern | tests/test_cardinality.py:57 |
| test698 | `test_698_cap_shape_info_cardinality_always_single_from_urn` | TEST698: CapShapeInfo cardinality is always Single when derived from URN Cardinality comes from context (is_sequence), not from URN tags. The list tag is a semantic type property, not a cardinality indicator. | tests/test_cardinality.py:67 |
| test699 | `test_699_cap_shape_info_list_urn_still_single_cardinality` | TEST699: CapShapeInfo cardinality from URN is always Single; ManyToOne requires is_sequence | tests/test_cardinality.py:78 |
| test709 | `test_709_pattern_produces_vector` | TEST709: Tests CardinalityPattern correctly identifies patterns that produce vectors Verifies OneToMany and ManyToMany return true, others return false | tests/test_cardinality.py:89 |
| test710 | `test_710_pattern_requires_vector` | TEST710: Tests CardinalityPattern correctly identifies patterns that require vectors Verifies ManyToOne and ManyToMany return true, others return false | tests/test_cardinality.py:97 |
| test711 | `test_711_strand_shape_analysis_simple_linear` | TEST711: Tests shape chain analysis for simple linear one-to-one capability chains Verifies chains with no fan-out are valid and require no transformation | tests/test_cardinality.py:105 |
| test712 | `test_712_strand_shape_analysis_with_fan_out` | TEST712: Tests shape chain analysis detects fan-out points in capability chains Fan-out requires is_sequence=true on the cap's output, not a "list" URN tag | tests/test_cardinality.py:117 |
| test713 | `test_713_strand_shape_analysis_empty` | TEST713: Tests shape chain analysis handles empty capability chains correctly Verifies empty chains are valid and require no transformation | tests/test_cardinality.py:135 |
| test714 | `test_714_cardinality_serialization` | TEST714: Tests InputCardinality serializes and deserializes correctly to/from JSON Verifies JSON round-trip preserves cardinality values | tests/test_cardinality.py:142 |
| test715 | `test_715_pattern_serialization` | TEST715: Tests CardinalityPattern serializes and deserializes correctly to/from JSON Verifies JSON round-trip preserves pattern values with snake_case formatting | tests/test_cardinality.py:149 |
| test716 | `test_716_empty_collection` | TEST716: Tests CapInputCollection empty collection has zero files and folders Verifies is_empty() returns true and counts are zero for new collection | tests/test_collection_input.py:7 |
| test717 | `test_717_collection_with_files` | TEST717: Tests CapInputCollection correctly counts files in flat collection Verifies total_file_count() returns 2 for collection with 2 files, no folders | tests/test_collection_input.py:15 |
| test718 | `test_718_nested_collection` | TEST718: Tests CapInputCollection correctly counts files and folders in nested structure Verifies total_file_count() includes subfolder files and total_folder_count() counts subfolders | tests/test_collection_input.py:26 |
| test719 | `test_719_flatten_to_files` | TEST719: Tests CapInputCollection flatten_to_files recursively collects all files Verifies flatten() extracts files from root and all subfolders into flat list | tests/test_collection_input.py:39 |
| test720 | `test_720_from_media_urn_opaque` | TEST720: Tests InputStructure correctly identifies opaque media URNs Verifies that URNs without record marker are parsed as Opaque | tests/test_cardinality.py:156 |
| test721 | `test_721_from_media_urn_record` | TEST721: Tests InputStructure correctly identifies record media URNs Verifies that URNs with record marker tag are parsed as Record | tests/test_cardinality.py:164 |
| test722 | `test_722_structure_compatibility_opaque_to_opaque` | TEST722: Tests structure compatibility for opaque-to-opaque data flow | tests/test_cardinality.py:175 |
| test723 | `test_723_structure_compatibility_record_to_record` | TEST723: Tests structure compatibility for record-to-record data flow | tests/test_cardinality.py:183 |
| test724 | `test_724_structure_incompatibility_opaque_to_record` | TEST724: Tests structure incompatibility for opaque-to-record flow | tests/test_cardinality.py:191 |
| test725 | `test_725_structure_incompatibility_record_to_opaque` | TEST725: Tests structure incompatibility for record-to-opaque flow | tests/test_cardinality.py:197 |
| test726 | `test_726_apply_structure_add_record` | TEST726: Tests applying Record structure adds record marker to URN | tests/test_cardinality.py:203 |
| test727 | `test_727_apply_structure_remove_record` | TEST727: Tests applying Opaque structure removes record marker from URN | tests/test_cardinality.py:208 |
| test728 | `test_728_cap_node_helpers` | TEST728: Tests MachineNode helper methods for identifying node types (cap, fan-out, fan-in) Verifies is_cap(), is_fan_out(), is_fan_in(), and cap_urn() correctly classify node types | tests/test_plan.py:23 |
| test729 | `test_729_edge_types` | TEST729: Tests creation and classification of different edge types (Direct, Iteration, Collection, JsonField) Verifies that edge constructors produce correct EdgeType variants | tests/test_plan.py:43 |
| test730 | `test_730_media_shape_from_urn_all_combinations` | TEST730: Tests MediaShape correctly parses all four combinations | tests/test_cardinality.py:213 |
| test731 | `test_731_media_shape_compatible_direct` | TEST731: Tests MediaShape compatibility for matching shapes | tests/test_cardinality.py:232 |
| test732 | `test_732_media_shape_cardinality_changes` | TEST732: Tests MediaShape compatibility for cardinality changes with matching structure | tests/test_cardinality.py:245 |
| test733 | `test_733_media_shape_structure_mismatch` | TEST733: Tests MediaShape incompatibility when structures don't match | tests/test_cardinality.py:264 |
| test734 | `test_734_topological_order_self_loop` | TEST734: Tests topological sort detects self-referencing cycles (A→A) Verifies that self-loops are recognized as cycles and produce an error | tests/test_plan.py:53 |
| test735 | `test_735_topological_order_multiple_entry_points` | TEST735: Tests topological sort handles graphs with multiple independent starting nodes Verifies that parallel entry points (A→C, B→C) both precede their merge point in ordering | tests/test_plan.py:62 |
| test736 | `test_736_topological_order_complex_dag` | TEST736: Tests topological sort on a complex multi-path DAG with 6 nodes Verifies that all dependency constraints are satisfied in a graph with multiple converging paths | tests/test_plan.py:82 |
| test737 | `test_737_linear_chain_single_cap` | TEST737: Tests linear_chain() with exactly one capability Verifies that a single-element chain produces a valid plan with input_slot, cap, and output | tests/test_plan.py:108 |
| test738 | `test_738_linear_chain_empty` | TEST738: Tests linear_chain() with empty capability list Verifies that an empty chain produces a plan with zero nodes and edges | tests/test_plan.py:116 |
| test739 | `test_739_node_execution_result_success` | TEST739: Tests NodeExecutionResult structure for successful node execution Verifies that success status, outputs (binary and text), and error fields work correctly | tests/test_plan.py:123 |
| test740 | `test_740_cap_shape_info_from_specs` | TEST740: Tests CapShapeInfo correctly parses cap specs | tests/test_cardinality.py:279 |
| test741 | `test_741_cap_shape_info_pattern` | TEST741: Tests CapShapeInfo pattern detection — OneToMany requires output is_sequence=true | tests/test_cardinality.py:288 |
| test742 | `test_742_edge_type_serialization` | TEST742: Tests EdgeType enum serialization and deserialization to/from JSON Verifies that edge types like Direct and JsonField correctly round-trip through serde_json | tests/test_plan.py:137 |
| test743 | `test_743_execution_node_type_serialization` | TEST743: Tests ExecutionNodeType enum serialization and deserialization to/from JSON Verifies that node types like Cap and ForEach correctly serialize with their fields | tests/test_plan.py:149 |
| test744 | `test_744_plan_serialization` | TEST744: Tests MachinePlan serialization and deserialization to/from JSON Verifies that complete plans with nodes and edges correctly round-trip through JSON | tests/test_plan.py:161 |
| test745 | `test_745_merge_strategy_serialization` | TEST745: Tests MergeStrategy enum serialization to JSON Verifies that merge strategies like Concat and ZipWith serialize to correct string values | tests/test_plan.py:173 |
| test746 | `test_746_cap_node_output` | TEST746: Tests creation of Output node type that references a source node Verifies that MachineNode::output() correctly constructs an Output node with name and source | tests/test_plan.py:179 |
| test747 | `test_747_cap_node_merge` | TEST747: Tests creation and validation of Merge node that combines multiple inputs Verifies that Merge nodes with multiple input nodes and a strategy can be added to plans | tests/test_plan.py:187 |
| test748 | `test_748_cap_node_split` | TEST748: Tests creation of Split node that distributes input to multiple outputs Verifies that Split nodes correctly specify an input node and output count | tests/test_plan.py:203 |
| test749 | `test_749_get_node` | TEST749: Tests get_node() method for looking up nodes by ID in a plan Verifies that existing nodes are found and non-existent nodes return None | tests/test_plan.py:215 |
| test750 | `test_750_strand_shape_valid` | TEST750: Tests shape chain analysis for valid chain with matching structures | tests/test_cardinality.py:300 |
| test751 | `test_751_strand_shape_structure_mismatch` | TEST751: Tests shape chain analysis detects structure mismatch | tests/test_cardinality.py:311 |
| test752 | `test_752_strand_shape_with_fanout` | TEST752: Tests shape chain analysis with fan-out (matching structures) Fan-out requires output is_sequence=true on the disbind cap | tests/test_cardinality.py:323 |
| test753 | `test_753_strand_shape_list_record_to_list_record` | TEST753: Tests shape chain analysis correctly handles list-to-list record flow | tests/test_cardinality.py:341 |
| test754 | `test_754_extract_prefix_nonexistent` | TEST754: extract_prefix_to with nonexistent node returns error | tests/test_plan.py:277 |
| test755 | `test_755_extract_foreach_body` | TEST755: extract_foreach_body extracts body as standalone plan | tests/test_plan.py:283 |
| test756 | `test_756_extract_foreach_body_unclosed` | TEST756: extract_foreach_body for unclosed ForEach (single body cap) | tests/test_plan.py:300 |
| test757 | `test_757_extract_foreach_body_wrong_type` | TEST757: extract_foreach_body fails for non-ForEach node | tests/test_plan.py:311 |
| test758 | `test_758_extract_suffix_from` | TEST758: extract_suffix_from extracts collect → cap_post → output | tests/test_plan.py:317 |
| test759 | `test_759_extract_suffix_nonexistent` | TEST759: extract_suffix_from fails for nonexistent node | tests/test_plan.py:332 |
| test760 | `test_760_decomposition_covers_all_caps` | TEST760: Full decomposition roundtrip — prefix + body + suffix cover all cap nodes | tests/test_plan.py:338 |
| test761 | `test_761_prefix_is_dag` | TEST761: Prefix sub-plan can be topologically sorted (is a valid DAG) | tests/test_plan.py:352 |
| test762 | `test_762_body_is_dag` | TEST762: Body sub-plan can be topologically sorted (is a valid DAG) | tests/test_plan.py:358 |
| test763 | `test_763_suffix_is_dag` | TEST763: Suffix sub-plan can be topologically sorted (is a valid DAG) | tests/test_plan.py:364 |
| test764 | `test_764_extract_prefix_to_input_slot` | TEST764: extract_prefix_to with InputSlot as target (trivial prefix) | tests/test_plan.py:372 |
| test765 | `test_765_validation_to_json_empty` | TEST765: Tests validation_to_json() returns None for empty validation constraints Verifies that default MediaValidation with no constraints produces JSON None | tests/test_plan_builder.py:38 |
| test766 | `test_766_validation_to_json_with_constraints` | TEST766: Tests validation_to_json() converts MediaValidation with constraints to JSON Verifies that min/max validation rules are correctly serialized as JSON fields | tests/test_plan_builder.py:45 |
| test767 | `test_767_argument_info_serialization` | TEST767: Tests ArgumentInfo struct serialization to JSON Verifies that argument metadata including resolution status and validation is correctly serialized | tests/test_plan_builder.py:54 |
| test768 | `test_768_path_argument_requirements_structure` | TEST768: Tests PathArgumentRequirements structure for single-step execution paths Verifies that argument requirements are correctly organized by step with resolution information | tests/test_plan_builder.py:72 |
| test769 | `test_769_path_with_required_slot` | TEST769: Tests PathArgumentRequirements tracking of required user-input slots Verifies that arguments requiring user input are collected in slots and can_execute_without_input is false | tests/test_plan_builder.py:106 |
| test770 | `test_770_rejects_foreach` | TEST770: plan_to_resolved_graph rejects plans containing ForEach nodes | tests/test_orchestrator_plan_converter.py:40 |
| test771 | `test_771_rejects_collect` | TEST771: plan_to_resolved_graph rejects plans containing Collect nodes | tests/test_orchestrator_plan_converter.py:106 |
| test772 | `test_772_find_paths_finds_multi_step_paths` | TEST772: Tests find_paths_to_exact_target() finds multi-step paths Verifies that paths through intermediate nodes are found correctly | tests/test_live_cap_fab.py:58 |
| test773 | `test_773_find_paths_returns_empty_when_no_path` | TEST773: Tests find_paths_to_exact_target() returns empty when no path exists Verifies that pathfinding returns no paths when target is unreachable | tests/test_live_cap_fab.py:72 |
| test774 | `test_774_get_reachable_targets_finds_all_targets` | TEST774: Tests get_reachable_targets() returns all reachable targets Verifies that reachable targets include direct cap targets and cardinality variants (list versions via Collect) | tests/test_live_cap_fab.py:82 |
| test777 | `test_777_type_mismatch_pdf_cap_does_not_match_png_input` | TEST777: Tests type checking prevents using PDF-specific cap with PNG input Verifies that media type compatibility is enforced during pathfinding | tests/test_live_cap_fab.py:93 |
| test778 | `test_778_type_mismatch_png_cap_does_not_match_pdf_input` | TEST778: Tests type checking prevents using PNG-specific cap with PDF input Verifies that media type compatibility is enforced during pathfinding | tests/test_live_cap_fab.py:109 |
| test779 | `test_779_get_reachable_targets_respects_type_matching` | TEST779: Tests get_reachable_targets() only returns targets reachable via type-compatible caps Verifies that PNG and PDF inputs reach different cap targets (not each other's) | tests/test_live_cap_fab.py:125 |
| test780 | `test_780_split_integer_array` | TEST780: split_cbor_array splits a simple array of integers | tests/test_cbor_util.py:19 |
| test781 | `test_781_find_paths_respects_type_chain` | TEST781: Tests find_paths_to_exact_target() enforces type compatibility across multi-step chains Verifies that paths are only found when all intermediate types are compatible | tests/test_live_cap_fab.py:140 |
| test782 | `test_782_split_non_array` | TEST782: split_cbor_array rejects non-array input | tests/test_cbor_util.py:28 |
| test783 | `test_783_split_empty_array` | TEST783: split_cbor_array rejects empty array | tests/test_cbor_util.py:35 |
| test784 | `test_784_split_invalid_cbor` | TEST784: split_cbor_array rejects invalid CBOR bytes | tests/test_cbor_util.py:42 |
| test785 | `test_785_assemble_integer_array` | TEST785: assemble_cbor_array creates array from individual items | tests/test_cbor_util.py:48 |
| test786 | `test_786_roundtrip_split_assemble` | TEST786: split then assemble roundtrip preserves data | tests/test_cbor_util.py:55 |
| test787 | `test_787_find_paths_sorting_prefers_shorter` | TEST787: Tests find_paths_to_exact_target() sorts paths by length, preferring shorter ones Verifies that among multiple paths, the shortest is ranked first | tests/test_live_cap_fab.py:166 |
| test788 | `test_788_foreach_only_with_sequence_input` | TEST788: ForEach is only synthesized when is_sequence=true | tests/test_live_cap_fab.py:186 |
| test789 | `test_789_cap_from_json_has_valid_specs` | TEST789: Tests that caps loaded from JSON have correct in_spec/out_spec | tests/test_live_cap_fab.py:218 |
| test790 | `test_790_identity_urn_is_specific` | TEST790: Tests identity_urn is specific and doesn't match everything | tests/test_live_cap_fab.py:240 |
| test791 | `test_791_sync_from_cap_urns_adds_edges` | TEST791: Tests sync_from_cap_urns actually adds edges | tests/test_live_cap_fab.py:253 |
| test792 | `test_792_argument_binding_requires_input` | TEST792: Tests ArgumentBinding requires_input distinguishes Slots from Literals Verifies Slot returns true (needs user input) while Literal returns false | tests/test_planner_argument_binding.py:200 |
| test793 | `test_793_argument_binding_serialization` | TEST793: Tests ArgumentBinding PreviousOutput serializes/deserializes correctly Verifies JSON round-trip preserves node_id and output_field values | tests/test_planner_argument_binding.py:206 |
| test794 | `test_794_argument_bindings_add_file_path` | TEST794: Tests ArgumentBindings add_file_path adds InputFilePath binding Verifies add_file_path() creates binding map entry with InputFilePath variant | tests/test_planner_argument_binding.py:218 |
| test795 | `test_795_argument_bindings_unresolved_slots` | TEST795: Tests ArgumentBindings identifies unresolved Slot bindings Verifies has_unresolved_slots() and get_unresolved_slots() detect Slots needing values | tests/test_planner_argument_binding.py:226 |
| test796 | `test_796_resolve_input_file_path` | TEST796: Tests resolve_binding resolves InputFilePath to current file path Verifies InputFilePath binding resolves to file path bytes with InputFile source | tests/test_planner_argument_binding.py:235 |
| test797 | `test_797_resolve_literal` | TEST797: Tests resolve_binding resolves Literal to JSON-encoded bytes Verifies Literal binding serializes value to bytes with Literal source | tests/test_planner_argument_binding.py:252 |
| test798 | `test_798_resolve_previous_output` | TEST798: Tests resolve_binding extracts value from previous node output Verifies PreviousOutput binding fetches field from earlier execution results | tests/test_planner_argument_binding.py:267 |
| test799 | `test_799_machine_input_single` | TEST799: Tests StrandInput single constructor creates valid Single cardinality input Verifies single() wraps one file with Single cardinality and validates correctly | tests/test_planner_argument_binding.py:283 |
| test800 | `test_800_machine_input_vector` | TEST800: Tests StrandInput sequence constructor creates valid Sequence cardinality input Verifies sequence() wraps multiple files with Sequence cardinality | tests/test_planner_argument_binding.py:292 |
| test801 | `test_801_cap_input_file_deserialization_from_dry_context` | TEST801: Tests CapInputFile deserializes from JSON with source metadata fields Verifies JSON with source_id and source_type deserializes to CapInputFile correctly | tests/test_planner_argument_binding.py:304 |
| test802 | `test_802_cap_input_file_deserialization_via_value` | TEST802: Tests CapInputFile deserializes from compact JSON via serde_json::Value Verifies deserialization through Value intermediate works correctly | tests/test_planner_argument_binding.py:319 |
| test803 | `test_803_machine_input_invalid_single` | TEST803: Tests StrandInput validation detects mismatched Single cardinality with multiple files Verifies is_valid() returns false when Single cardinality has more than one file | tests/test_planner_argument_binding.py:329 |
| test804 | `test_804_extract_json_path_simple` | TEST804: Tests basic JSON path extraction with dot notation for nested objects Verifies that simple paths like "data.message" correctly extract values from nested JSON structures | tests/test_executor.py:10 |
| test805 | `test_805_extract_json_path_with_array` | TEST805: Tests JSON path extraction with array indexing syntax Verifies that bracket notation like "items[0].name" correctly accesses array elements and their nested fields | tests/test_executor.py:16 |
| test806 | `test_806_extract_json_path_missing_field` | TEST806: Tests error handling when JSON path references non-existent fields Verifies that accessing missing fields returns an appropriate error message | tests/test_executor.py:22 |
| test807 | `test_807_apply_edge_type_direct` | TEST807: Tests EdgeType::Direct passes JSON values through unchanged Verifies that Direct edge type acts as a transparent passthrough without transformation | tests/test_executor.py:32 |
| test808 | `test_808_apply_edge_type_json_field` | TEST808: Tests EdgeType::JsonField extracts specific top-level fields from JSON objects Verifies that JsonField edge type correctly isolates a single named field from the source output | tests/test_executor.py:38 |
| test809 | `test_809_apply_edge_type_json_field_missing` | TEST809: Tests EdgeType::JsonField error handling for missing fields Verifies that attempting to extract a non-existent field returns an error | tests/test_executor.py:44 |
| test810 | `test_810_apply_edge_type_json_path` | TEST810: Tests EdgeType::JsonPath extracts values using nested path expressions Verifies that JsonPath edge type correctly navigates through multiple levels like "data.nested.value" | tests/test_executor.py:54 |
| test811 | `test_811_apply_edge_type_iteration` | TEST811: Tests EdgeType::Iteration preserves array values for iterative processing Verifies that Iteration edge type passes through arrays unchanged to enable ForEach patterns | tests/test_executor.py:60 |
| test812 | `test_812_apply_edge_type_collection` | TEST812: Tests EdgeType::Collection preserves collected values without transformation Verifies that Collection edge type maintains structure for aggregation patterns | tests/test_executor.py:66 |
| test813 | `test_813_extract_json_path_deeply_nested` | TEST813: Tests JSON path extraction through deeply nested object hierarchies (4+ levels) Verifies that paths can traverse multiple nested levels like "level1.level2.level3.level4.value" | tests/test_executor.py:72 |
| test814 | `test_814_extract_json_path_array_out_of_bounds` | TEST814: Tests error handling when array index exceeds available elements Verifies that out-of-bounds array access returns a descriptive error message | tests/test_executor.py:78 |
| test815 | `test_815_extract_json_path_single_segment` | TEST815: Tests JSON path extraction with single-level paths (no nesting) Verifies that simple field names without dots correctly extract top-level values | tests/test_executor.py:88 |
| test816 | `test_816_extract_json_path_with_special_characters` | TEST816: Tests JSON path extraction preserves special characters in string values Verifies that quotes, backslashes, and other special characters are correctly maintained | tests/test_executor.py:93 |
| test817 | `test_817_extract_json_path_with_null_value` | TEST817: Tests JSON path extraction correctly handles explicit null values Verifies that null is returned as serde_json::Value::Null rather than an error | tests/test_executor.py:99 |
| test818 | `test_818_extract_json_path_with_empty_array` | TEST818: Tests JSON path extraction correctly returns empty arrays Verifies that zero-length arrays are extracted as valid empty array values | tests/test_executor.py:105 |
| test819 | `test_819_extract_json_path_with_numeric_types` | TEST819: Tests JSON path extraction handles various numeric types correctly Verifies extraction of integers, floats, negative numbers, and zero | tests/test_executor.py:111 |
| test820 | `test_820_extract_json_path_with_boolean` | TEST820: Tests JSON path extraction correctly handles boolean values Verifies that true and false are extracted as proper boolean JSON values | tests/test_executor.py:120 |
| test821 | `test_821_extract_json_path_with_nested_arrays` | TEST821: Tests JSON path extraction with multi-dimensional arrays (matrix access) Verifies that nested array structures like "matrix[1]" correctly extract inner arrays | tests/test_executor.py:127 |
| test822 | `test_822_extract_json_path_invalid_array_index` | TEST822: Tests error handling for non-numeric array indices Verifies that invalid indices like "items[abc]" return a descriptive parse error | tests/test_executor.py:133 |
| test823 | `test_823_dispatch_exact_match` | TEST823: is_dispatchable — exact match candidate dispatches request | tests/test_cap_urn.py:1117 |
| test824 | `test_824_dispatch_contravariant_input` | TEST824: is_dispatchable — candidate with broader input handles specific request (contravariance) | tests/test_cap_urn.py:1128 |
| test825 | `test_825_dispatch_request_unconstrained_input` | TEST825: is_dispatchable — request with unconstrained input dispatches to specific candidate media: on the request input axis means "unconstrained" — vacuously true | tests/test_cap_urn.py:1139 |
| test826 | `test_826_dispatch_covariant_output` | TEST826: is_dispatchable — candidate output must satisfy request output (covariance) | tests/test_cap_urn.py:1151 |
| test827 | `test_827_dispatch_generic_output_fails` | TEST827: is_dispatchable — candidate with generic output cannot satisfy specific request | tests/test_cap_urn.py:1163 |
| test828 | `test_828_dispatch_wildcard_requires_tag_presence` | TEST828: is_dispatchable — wildcard * tag in request, candidate missing tag → reject | tests/test_cap_urn.py:1175 |
| test829 | `test_829_dispatch_wildcard_with_tag_present` | TEST829: is_dispatchable — wildcard * tag in request, candidate has tag → accept | tests/test_cap_urn.py:1187 |
| test830 | `test_830_dispatch_candidate_extra_tags` | TEST830: is_dispatchable — candidate extra tags are refinement, always OK | tests/test_cap_urn.py:1199 |
| test831 | `test_831_dispatch_cross_backend_mismatch` | TEST831: is_dispatchable — cross-backend mismatch prevented | tests/test_cap_urn.py:1211 |
| test832 | `test_832_dispatch_asymmetric` | TEST832: is_dispatchable is NOT symmetric | tests/test_cap_urn.py:1223 |
| test833 | `test_833_comparable_symmetric` | TEST833: is_comparable — both directions checked | tests/test_cap_urn.py:1242 |
| test834 | `test_834_comparable_unrelated` | TEST834: is_comparable — unrelated caps are NOT comparable | tests/test_cap_urn.py:1254 |
| test835 | `test_835_equivalent_identical` | TEST835: is_equivalent — identical caps | tests/test_cap_urn.py:1266 |
| test836 | `test_836_equivalent_non_equivalent` | TEST836: is_equivalent — non-equivalent comparable caps | tests/test_cap_urn.py:1278 |
| test837 | `test_837_dispatch_op_mismatch` | TEST837: is_dispatchable — op tag mismatch rejects | tests/test_cap_urn.py:1290 |
| test838 | `test_838_dispatch_request_wildcard_output` | TEST838: is_dispatchable — request with wildcard output accepts any candidate output | tests/test_cap_urn.py:1301 |
| test839 | `test_839_peer_response_delivers_logs_before_stream_start` | TEST839: LOG frames arriving BEFORE StreamStart are delivered immediately This tests the critical fix: during a peer call, the peer (e.g., modelcartridge) sends LOG frames for minutes during model download BEFORE sending any data (StreamStart + Chunk). The handler must receive these LOGs in real-time so it can re-emit progress and keep the engine's activity timer alive. Previously, demux_single_stream blocked on awaiting StreamStart before returning PeerResponse, which meant the handler couldn't call recv() until data arrived — causing 120s activity timeouts during long downloads. | tests/test_cartridge_runtime.py:2113 |
| test840 | `test_840_peer_response_collect_bytes_discards_logs` | TEST840: PeerResponse::collect_bytes discards LOG frames | tests/test_cartridge_runtime.py:2164 |
| test841 | `test_841_peer_response_collect_value_discards_logs` | TEST841: PeerResponse::collect_value discards LOG frames | tests/test_cartridge_runtime.py:2194 |
| test842 | `test_842_progress_sender_emits_frames` | TEST842: run_with_keepalive returns closure result (fast operation, no keepalive frames) | tests/test_cartridge_runtime.py:2287 |
| test843 | `test_843_progress_sender_from_background_thread` | TEST843: run_with_keepalive returns Ok/Err from closure | tests/test_cartridge_runtime.py:2304 |
| test844 | `test_844_progress_sender_multiple_threads` | TEST844: run_with_keepalive propagates errors from closure | tests/test_cartridge_runtime.py:2327 |
| test845 | `test_845_progress_sender_independent_of_emitter` | TEST845: ProgressSender emits progress and log frames independently of OutputStream | tests/test_cartridge_runtime.py:2352 |
| test846 | `test_846_progress_frame_roundtrip` | TEST846: Test progress LOG frame encode/decode roundtrip preserves progress float | tests/test_cbor_io.py:1101 |
| test847 | `test_847_progress_double_roundtrip` | TEST847: Double roundtrip (modelcartridge → relay → candlecartridge) | tests/test_cbor_io.py:1134 |
| test848 | `test_848_relay_notify_roundtrip` | TEST848: RelayNotify encode/decode roundtrip preserves manifest and limits | tests/test_cbor_io.py:1032 |
| test849 | `test_849_relay_state_roundtrip` | TEST849: RelayState encode/decode roundtrip preserves resource payload | tests/test_cbor_io.py:1054 |
| test850 | `test_850_all_format_conversion_paths_build_valid_urns` | TEST850: all_format_conversion_paths each entry builds a valid parseable CapUrn | tests/test_standard_format_conversion.py:9 |
| test851 | `test_851_format_conversion_urn_specs` | TEST851: format_conversion_urn in/out specs match the input constants | tests/test_standard_format_conversion.py:23 |
| test852 | `test_852_lub_identical` | TEST852: LUB of identical URNs returns the same URN | tests/test_media_urn.py:413 |
| test853 | `test_853_lub_no_common_tags` | TEST853: LUB of URNs with no common tags returns media: (universal) | tests/test_media_urn.py:420 |
| test854 | `test_854_lub_partial_overlap` | TEST854: LUB keeps common tags, drops differing ones. Two text values with differing serialization formats share their encoding but not their fmt. | tests/test_media_urn.py:431 |
| test855 | `test_855_lub_list_vs_scalar` | TEST855: LUB of list and non-list drops list tag | tests/test_media_urn.py:441 |
| test856 | `test_856_lub_empty` | TEST856: LUB of empty input returns universal type | tests/test_media_urn.py:451 |
| test857 | `test_857_lub_single` | TEST857: LUB of single input returns that input | tests/test_media_urn.py:458 |
| test858 | `test_858_lub_three_inputs` | TEST858: LUB with three+ inputs narrows correctly | tests/test_media_urn.py:465 |
| test859 | `test_859_lub_valued_tags` | TEST859: LUB with valued tags (non-marker) that differ | tests/test_media_urn.py:476 |
| test860 | `test_860_seq_assigner_same_rid_different_xids_independent` | TEST860: Same RID with different XIDs get independent seq counters | tests/test_cbor_frame.py:693 |
| test880 | `test_880_no_duplicates_with_unique_caps` | TEST880: Tests duplicate detection passes for caps with unique URN combinations Verifies that check_for_duplicate_caps() correctly accepts caps with different op/in/out combinations | tests/test_plan_builder.py:167 |
| test886 | `test_886_optional_non_io_arg_with_default_has_default` | TEST886: Tests optional non-IO arguments with default values are marked as HasDefault Verifies that optional arguments with defaults behave the same as required ones with defaults | tests/test_plan_builder.py:294 |
| test890 | `test_890_direction_semantic_matching` | TEST890: Semantic direction matching - generic candidate matches specific request | tests/test_cap_urn.py:1313 |
| test891 | `test_891_direction_semantic_specificity` | TEST891: Semantic direction specificity — more constraints in either axis means a higher score under the truth-table-driven sum. media: (top, no tags) scores 0; each marker tag scores 2; each exact tag scores 3. | tests/test_cap_urn.py:1389 |
| test892 | `test_892_extensions_serialization` | TEST892: Test extensions serializes/deserializes correctly in MediaDef | tests/test_media_def.py:362 |
| test893 | `test_893_extensions_with_metadata_and_validation` | TEST893: Test extensions can coexist with metadata and validation | tests/test_media_def.py:384 |
| test894 | `test_894_multiple_extensions` | TEST894: Test multiple extensions in a media def | tests/test_media_def.py:406 |
| test898 | `test_898_binary_integrity_through_relay` | TEST898: Binary data integrity through full relay path (256 byte values) | tests/test_cbor_integration.py:670 |
| test899 | `test_899_streaming_chunks_through_relay` | TEST899: Streaming chunks flow through relay without accumulation | tests/test_cbor_integration.py:781 |
| test900 | `test_900_two_cartridges_routed_independently` | TEST900: Two cartridges routed independently by cap_urn | tests/test_cbor_integration.py:880 |
| test901 | `test_901_req_for_unknown_cap_returns_err_frame` | TEST901: REQ for unknown cap returns ERR frame (not fatal) | tests/test_cbor_integration.py:1033 |
| test902 | `test_902_compute_checksum_empty` | TEST902: Verify FNV-1a checksum handles empty data | tests/test_cbor_frame.py:1520 |
| test903 | `test_903_chunk_with_chunk_index_and_checksum` | TEST903: Verify CHUNK frame can store chunk_index and checksum fields | tests/test_cbor_frame.py:1526 |
| test904 | `test_904_stream_end_with_chunk_count` | TEST904: Verify STREAM_END frame can store chunk_count field | tests/test_cbor_frame.py:1542 |
| test908 | `test_908_cached_caps_accessible_when_offline` | TEST908: cached caps remain accessible while offline. | tests/test_registry.py:262 |
| test910 | `test_910_map_progress_monotonic` | TEST910: map_progress output is monotonic for monotonically increasing input | tests/test_executor.py:152 |
| test911 | `test_911_map_progress_bounded` | TEST911: map_progress output is bounded within [base, base+weight] | tests/test_executor.py:162 |
| test912 | `test_912_progress_mapper_reports_through_parent` | TEST912: ProgressMapper correctly maps through a CapProgressFn | tests/test_executor.py:174 |
| test913 | `test_913_progress_mapper_as_cap_progress_fn` | TEST913: ProgressMapper.as_cap_progress_fn produces same mapping | tests/test_executor.py:192 |
| test914 | `test_914_progress_mapper_sub_mapper` | TEST914: ProgressMapper.sub_mapper chains correctly | tests/test_executor.py:212 |
| test915 | `test_915_per_group_subdivision_monotonic_bounded` | TEST915: Per-group subdivision produces monotonic, bounded progress for N groups Uses pre-computed boundaries (same pattern as production code) to guarantee monotonicity regardless of f32 rounding. | tests/test_executor.py:233 |
| test917 | `test_917_high_frequency_progress_bounded` | TEST917: High-frequency progress emission does not violate bounds (Regression test for the deadlock scenario — verifies computation stays bounded) | tests/test_executor.py:271 |
| test919 | `test_919_parse_simple_testcartridge_graph` | TEST919: Parse simple machine notation graph with test-edge1 | tests/test_orchestrator_parser.py:355 |
| test920 | `test_920_cap_urn_total_order_basic` | TEST920: Tests creation of a simple execution plan with a single capability Verifies that single_cap() generates a valid plan with input_slot, cap node, and output node | tests/test_cap_urn.py:1422 |
| test921 | `test_921_cap_urn_order_consistent_with_equality` | TEST921: Tests creation of a linear chain of capabilities connected in sequence Verifies that linear_chain() correctly links multiple caps with proper edges and topological order | tests/test_cap_urn.py:1450 |
| test922 | `test_922_cap_urn_list_sortable` | TEST922: Tests creation and validation of an empty execution plan with no nodes Verifies that plans without capabilities are valid and handle zero nodes correctly | tests/test_cap_urn.py:1461 |
| test923 | `test_923_cap_urn_order_returns_not_implemented_for_non_cap` | TEST923: Tests storing and retrieving metadata attached to an execution plan Verifies that arbitrary JSON metadata can be associated with a plan for context preservation | tests/test_cap_urn.py:1479 |
| test924 | `test_924_validate_invalid_edge` | TEST924: Tests plan validation detects edges pointing to non-existent nodes Verifies that validate() returns an error when an edge references a missing to_node | tests/test_plan.py:437 |
| test925 | `test_925_topological_order_diamond` | TEST925: Tests topological sort correctly orders a diamond-shaped DAG (A->B,C->D) Verifies that nodes with multiple paths respect dependency constraints (A first, D last) | tests/test_plan.py:446 |
| test926 | `test_926_topological_order_detects_cycle` | TEST926: Tests topological sort detects and rejects cyclic dependencies (A->B->C->A) Verifies that circular references produce a "Cycle detected" error | tests/test_plan.py:465 |
| test927 | `test_927_execution_result` | TEST927: Tests MachineResult structure for successful execution outcomes Verifies that success status, outputs, and primary_output() accessor work correctly | tests/test_plan.py:426 |
| test928 | `test_928_validate_invalid_from_node` | TEST928: Tests plan validation detects edges originating from non-existent nodes Verifies that validate() returns an error when an edge references a missing from_node | tests/test_plan.py:481 |
| test929 | `test_929_validate_invalid_entry_node` | TEST929: Tests plan validation detects invalid entry node references Verifies that validate() returns an error when entry_nodes contains a non-existent node ID | tests/test_plan.py:490 |
| test930 | `test_930_validate_invalid_output_node` | TEST930: Tests plan validation detects invalid output node references Verifies that validate() returns an error when output_nodes contains a non-existent node ID | tests/test_plan.py:499 |
| test931 | `test_931_node_execution_result_failure` | TEST931: Tests NodeExecutionResult structure for failed node execution Verifies that failure status, error message, and absence of outputs are correctly represented | tests/test_plan.py:508 |
| test932 | `test_932_execution_result_failure` | TEST932: Tests MachineResult structure for failed chain execution Verifies that failure status, error message, and absence of outputs are correctly represented | tests/test_plan.py:522 |
| test933 | `test_933_serialization_roundtrip` | TEST933: Tests CapInputCollection serializes to JSON and deserializes correctly Verifies JSON round-trip preserves folder_id, folder_name, files and file metadata | tests/test_collection_input.py:56 |
| test934 | `test_934_find_first_foreach` | TEST934: find_first_foreach detects ForEach in a plan | tests/test_plan.py:379 |
| test935 | `test_935_find_first_foreach_linear` | TEST935: find_first_foreach returns None for linear plans | tests/test_plan.py:385 |
| test936 | `test_936_has_foreach` | TEST936: has_foreach detects ForEach nodes | tests/test_plan.py:391 |
| test937 | `test_937_extract_prefix_to` | TEST937: extract_prefix_to extracts input_slot -> cap_0 as a standalone plan | tests/test_plan.py:413 |
| test938 | `test_938_different_caps_different_hashes` | TEST938: Two genuinely different caps must hash to different keys. If the canonical-form algorithm ever drifts to coalesce non-equivalent URNs (e.g. by stripping a tag that has functional meaning), this test fails immediately. Renumbered from TEST141 to resolve a collision with Go/ObjC's TEST141 (URL-shape). | tests/test_registry.py:214 |
| test939 | `test_939_cap_urn_canonical_form_drops_wildcard_in_out` | TEST939: The canonical form drops `in=media:` and `out=media:` segments. Every spelling of "the same cap with wildcard in/out" collapses to one byte-identical canonical string. This is the contract that makes registry lookups work: the cap-publisher hashes `<canonical-urn>` to compute the cache key, and every language port (Rust, Go, Python, JS, ObjC) must agree on the canonical form for cross-language lookups to land on the same key. A regression that emitted the wildcard segments would silently move the published cap to a different SHA-256 bucket, 404'ing every reader that hashes the canonical form. | tests/test_cap_urn.py:263 |
| test947 | `test_947_cap_not_found` | TEST947: Cap not found in registry | tests/test_orchestrator_parser.py:421 |
| test948 | `test_948_invalid_cap_urn` | TEST948: Invalid cap URN in machine notation | tests/test_orchestrator_parser.py:410 |
| test949 | `test_949_empty_graph` | TEST949: Empty machine notation (no edges) | tests/test_orchestrator_parser.py:399 |
| test950 | `test_950_reject_cycles` | TEST950: Validate that cycles are rejected | tests/test_orchestrator_parser.py:379 |
| test951 | `test_951_split_map_array` | TEST951: split_cbor_array with nested maps | tests/test_cbor_util.py:68 |
| test953 | `test_953_linear_plan_still_works` | TEST953: Linear plans (no ForEach/Collect) still convert successfully | tests/test_orchestrator_plan_converter.py:144 |
| test954 | `test_954_standalone_collect_passthrough` | TEST954: Standalone Collect nodes are handled as pass-through | tests/test_orchestrator_plan_converter.py:173 |
| test956 | `test_956_roundtrip_assemble_split` | TEST956: assemble then split roundtrip preserves data | tests/test_cbor_util.py:77 |
| test957 | `test_957_cap_input_file_new` | TEST957: Tests CapInputFile constructor creates file with correct path and media URN Verifies new() initializes file_path, media_urn and leaves metadata/source_id as None | tests/test_planner_argument_binding.py:342 |
| test958 | `test_958_cap_input_file_from_listing` | TEST958: Tests CapInputFile from_listing sets source metadata correctly Verifies from_listing() populates source_id and source_type as Listing | tests/test_planner_argument_binding.py:351 |
| test959 | `test_959_cap_input_file_filename` | TEST959: Tests CapInputFile extracts filename from full path correctly Verifies filename() returns just the basename without directory path | tests/test_planner_argument_binding.py:358 |
| test960 | `test_960_argument_binding_literal_string` | TEST960: Tests ArgumentBinding literal_string creates Literal variant with string value Verifies literal_string() wraps string in JSON Value::String | tests/test_planner_argument_binding.py:364 |
| test961 | `test_961_assemble_empty` | TEST961: assemble empty list produces empty CBOR array | tests/test_cbor_util.py:85 |
| test962 | `test_962_assemble_invalid_item` | TEST962: assemble rejects invalid CBOR item | tests/test_cbor_util.py:90 |
| test963 | `test_963_split_binary_items` | TEST963: split preserves CBOR byte strings (binary data — the common case in bifaci) | tests/test_cbor_util.py:96 |
| test964 | `test_964_split_sequence_bytes` | TEST964: split_cbor_sequence splits concatenated CBOR Bytes values | tests/test_cbor_util.py:110 |
| test965 | `test_965_split_sequence_text` | TEST965: split_cbor_sequence splits concatenated CBOR Text values | tests/test_cbor_util.py:120 |
| test966 | `test_966_split_sequence_mixed` | TEST966: split_cbor_sequence handles mixed types | tests/test_cbor_util.py:129 |
| test967 | `test_967_split_sequence_single` | TEST967: split_cbor_sequence single-item sequence | tests/test_cbor_util.py:138 |
| test968 | `test_968_roundtrip_assemble_split_sequence` | TEST968: roundtrip — assemble then split preserves items | tests/test_cbor_util.py:146 |
| test969 | `test_969_roundtrip_split_assemble_sequence` | TEST969: roundtrip — split then assemble preserves byte-for-byte | tests/test_cbor_util.py:153 |
| test970 | `test_970_split_sequence_empty` | TEST970: split_cbor_sequence rejects empty data | tests/test_cbor_util.py:160 |
| test971 | `test_971_split_sequence_truncated` | TEST971: split_cbor_sequence rejects truncated CBOR | tests/test_cbor_util.py:166 |
| test972 | `test_972_assemble_sequence_invalid_item` | TEST972: assemble_cbor_sequence rejects invalid CBOR item | tests/test_cbor_util.py:175 |
| test973 | `test_973_assemble_sequence_empty` | TEST973: assemble_cbor_sequence with empty items list produces empty bytes | tests/test_cbor_util.py:181 |
| test974 | `test_974_sequence_is_not_array` | TEST974: CBOR sequence is NOT a CBOR array — split_cbor_array rejects a sequence | tests/test_cbor_util.py:186 |
| test975 | `test_975_single_value_sequence` | TEST975: split_cbor_sequence works on data that is also a valid CBOR array (single top-level value) | tests/test_cbor_util.py:193 |
| test976 | `test_976_wrap_raw_items_roundtrips_and_assemble_rejects_them` | TEST976: wrap_raw_items_as_cbor_sequence wraps RAW (non-CBOR) item bytes — e.g. PNG frames — into a valid, self-delimiting CBOR sequence that split_cbor_sequence round-trips back to the exact raw items. Regression guard for commit 99df51c4 ("full dag"), which materialised sequence node_data with assemble_cbor_sequence(items) on the *raw* (unwrapped) items from decode_terminal_output. Raw binary is not itself CBOR, so that path failed with "Item 0: ..." (observed as the video extract-frames chain failure). This test asserts the wrap path succeeds AND that the assemble path genuinely rejects the same raw bytes — so the two functions are not interchangeable and the fix is load-bearing. | tests/test_cbor_util.py:211 |
| test977 | `test_977_os_files_excluded_integration` | TEST977: OS files excluded in resolve_paths | tests/test_input_resolver.py:222 |
| test987 | `test_987_gc_secondary_pass_enforces_hard_cap` | TEST987: The secondary hard-cap pass kicks in if the table exceeds HARD_CAP — a single eviction-fraction pass is not enough to recover headroom. | tests/test_cartridge_host_runtime.py:372 |
| test988 | `test_988_gc_reduces_table_below_soft_watermark_in_one_pass` | TEST988: GC keeps the table strictly below the hard cap and the single soft-watermark pass evicts exactly EVICTION_FRACTION of the pre-state. | tests/test_cartridge_host_runtime.py:305 |
| test991 | `test_991_detects_duplicate_cap_urns` | TEST991: Tests duplicate detection identifies caps with identical URNs Verifies that check_for_duplicate_caps() returns an error when multiple caps share the same cap_urn | tests/test_plan_builder.py:150 |
| test992 | `test_992_different_ops_same_types_not_duplicates` | TEST992: Tests caps with different operations but same input/output types are not duplicates Verifies that only the complete URN (including op) is used for duplicate detection | tests/test_plan_builder.py:178 |
| test993 | `test_993_same_op_different_input_types_not_duplicates` | TEST993: Tests caps with same operation but different input types are not duplicates Verifies that input type differences distinguish caps with the same operation name | tests/test_plan_builder.py:188 |
| test994 | `test_994_input_arg_first_cap_auto_resolved_from_input` | TEST994: Tests first cap's input argument is automatically resolved from input file Verifies that determine_resolution_with_io_check() returns FromInputFile for the first cap in a chain | tests/test_plan_builder.py:198 |
| test995 | `test_995_input_arg_subsequent_cap_auto_resolved_from_previous` | TEST995: Tests subsequent caps' input arguments are automatically resolved from previous output Verifies that determine_resolution_with_io_check() returns FromPreviousOutput for caps after the first | tests/test_plan_builder.py:212 |
| test996 | `test_996_output_arg_auto_resolved` | TEST996: Tests output arguments are automatically resolved from previous cap's output Verifies that arguments matching the output spec are always resolved as FromPreviousOutput | tests/test_plan_builder.py:236 |
| test997 | `test_997_file_path_type_fallback_first_cap` | TEST997: Tests MEDIA_FILE_PATH argument type resolves to input file for first cap Verifies that generic file-path arguments are bound to input file in the first cap | tests/test_plan_builder.py:250 |
| test998 | `test_998_file_path_type_fallback_subsequent_cap` | TEST998: Tests MEDIA_FILE_PATH argument type resolves to previous output for subsequent caps Verifies that generic file-path arguments are bound to previous cap's output after the first cap | tests/test_plan_builder.py:264 |
| test1000 | `test_1000_single_existing_file` | TEST1000: Single existing file | tests/test_input_resolver.py:36 |
| test1001 | `test_1001_nonexistent_file` | TEST1001: Single non-existent file | tests/test_input_resolver.py:45 |
| test1002 | `test_1002_empty_directory` | TEST1002: Empty directory | tests/test_input_resolver.py:51 |
| test1003 | `test_1003_directory_with_files` | TEST1003: Directory with files | tests/test_input_resolver.py:56 |
| test1004 | `test_1004_directory_with_subdirs` | TEST1004: Directory with subdirs (recursive) | tests/test_input_resolver.py:64 |
| test1005 | `test_1005_glob_matching_files` | TEST1005: Glob matching files | tests/test_input_resolver.py:73 |
| test1006 | `test_1006_glob_matching_nothing` | TEST1006: Glob matching nothing | tests/test_input_resolver.py:81 |
| test1007 | `test_1007_recursive_glob` | TEST1007: Recursive glob | tests/test_input_resolver.py:87 |
| test1008 | `test_1008_mixed_file_dir` | TEST1008: Mixed file + dir | tests/test_input_resolver.py:96 |
| test1009 | `test_1009_non_io_arg_with_default_has_default` | TEST1009: Tests required non-IO arguments with default values are marked as HasDefault Verifies that arguments like integers with defaults don't require user input | tests/test_plan_builder.py:280 |
| test1010 | `test_1010_duplicate_paths` | TEST1010: Duplicate paths are deduplicated | tests/test_input_resolver.py:106 |
| test1011 | `test_1011_invalid_glob` | TEST1011: Invalid glob syntax | tests/test_input_resolver.py:114 |
| test1012 | `test_1012_non_io_arg_without_default_requires_user_input` | TEST1012: Tests required non-IO arguments without defaults require user input Verifies that arguments like strings without defaults are marked as RequiresUserInput | tests/test_plan_builder.py:308 |
| test1013 | `test_1013_empty_input` | TEST1013: Empty input array | tests/test_input_resolver.py:120 |
| test1014 | `test_1014_symlink_to_file` | TEST1014: Symlink to file | tests/test_input_resolver.py:127 |
| test1015 | `test_1015_optional_non_io_arg_without_default_requires_user_input` | TEST1015: Tests optional non-IO arguments without defaults still require user input Verifies that optional arguments without defaults must be explicitly provided or skipped | tests/test_plan_builder.py:322 |
| test1016 | `test_1016_path_with_spaces` | TEST1016: Path with spaces | tests/test_input_resolver.py:136 |
| test1017 | `test_1017_path_with_unicode` | TEST1017: Path with unicode | tests/test_input_resolver.py:143 |
| test1018 | `test_1018_relative_path` | TEST1018: Relative path | tests/test_input_resolver.py:150 |
| test1019 | `test_1019_validation_to_json_none` | TEST1019: Tests validation_to_json() returns None for None input Verifies that missing validation metadata is converted to JSON None | tests/test_plan_builder.py:336 |
| test1020 | `test_1020_ds_store_excluded` | TEST1020: macOS .DS_Store is excluded | tests/test_input_resolver.py:158 |
| test1021 | `test_1021_thumbs_db_excluded` | TEST1021: Windows Thumbs.db is excluded | tests/test_input_resolver.py:164 |
| test1022 | `test_1022_resource_fork_excluded` | TEST1022: macOS resource fork files are excluded | tests/test_input_resolver.py:170 |
| test1023 | `test_1023_office_lock_excluded` | TEST1023: Office lock files are excluded | tests/test_input_resolver.py:176 |
| test1024 | `test_1024_git_dir_excluded` | TEST1024: .git directory is excluded | tests/test_input_resolver.py:182 |
| test1025 | `test_1025_macosx_dir_excluded` | TEST1025: __MACOSX archive artifact is excluded | tests/test_input_resolver.py:188 |
| test1026 | `test_1026_temp_files_excluded` | TEST1026: Temp files are excluded | tests/test_input_resolver.py:194 |
| test1027 | `test_1027_localized_excluded` | TEST1027: .localized is excluded | tests/test_input_resolver.py:202 |
| test1028 | `test_1028_desktop_ini_excluded` | TEST1028: desktop.ini is excluded | tests/test_input_resolver.py:207 |
| test1029 | `test_1029_normal_files_not_excluded` | TEST1029: Normal files are NOT excluded | tests/test_input_resolver.py:212 |
| test1090 | `test_1090_single_file_scalar` | TEST1090: 1 file → is_sequence=false | tests/test_input_resolver.py:231 |
| test1092 | `test_1092_two_files` | TEST1092: 2 files → is_sequence=true | tests/test_input_resolver.py:239 |
| test1093 | `test_1093_dir_single_file` | TEST1093: 1 dir with 1 file → is_sequence=false | tests/test_input_resolver.py:248 |
| test1094 | `test_1094_dir_multiple_files` | TEST1094: 1 dir with 3 files → is_sequence=true | tests/test_input_resolver.py:256 |
| test1098 | `test_1098_extension_based_pdf` | TEST1098: Extension-based detection picks up pdf tag for .pdf files | tests/test_input_resolver.py:266 |
| test1100 | `test_1100_cap_urn_normalizes_media_urn_tag_order` | TEST1100: Tests that CapUrn normalizes media URN tags to canonical order This is the root cause fix for caps not matching when cartridges report URNs with different tag ordering than the registry (e.g., "record;enc=utf-8" vs "enc=utf-8;record") | tests/test_cap_urn.py:1354 |
| test1103 | `test_1103_is_dispatchable_uses_correct_directionality` | TEST1103: Tests that is_dispatchable has correct directionality The available cap (candidate) must be dispatchable for the requested cap (request). This tests the directionality: candidate.is_dispatchable(&request) NOTE: This now tests CapUrn::is_dispatchable directly, not via MachinePlanBuilder | tests/test_cap_urn.py:1368 |
| test1104 | `test_1104_is_dispatchable_rejects_non_dispatchable` | TEST1104: Tests that is_dispatchable rejects when candidate cannot dispatch request | tests/test_cap_urn.py:1379 |
| test1105 | `test_1105_two_steps_same_cap_urn_different_slot_values` | TEST1105: Two steps with the same cap_urn get distinct slot values via different node_ids. This is the core disambiguation scenario that step-index keying was designed to solve. | tests/test_planner_argument_binding.py:83 |
| test1106 | `test_1106_slot_falls_through_to_cap_settings_shared` | TEST1106: Slot resolution falls through to cap_settings when no slot_value exists. cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value. | tests/test_planner_argument_binding.py:110 |
| test1107 | `test_1107_slot_value_overrides_cap_settings_per_step` | TEST1107: step_0 has a slot_value override, step_1 falls through to cap_settings. Proves per-step override works while shared settings remain as fallback. | tests/test_planner_argument_binding.py:130 |
| test1108 | `test_1108_resolve_all_passes_node_id` | TEST1108: ResolveAll with node_id threads correctly through to each binding. | tests/test_planner_argument_binding.py:157 |
| test1109 | `test_1109_slot_key_uses_node_id_not_cap_urn` | TEST1109: Slot key uses node_id, NOT cap_urn — a slot_value keyed by cap_urn must not match. | tests/test_planner_argument_binding.py:184 |
| test1111 | `test_1111_foreach_for_user_provided_list_source` | TEST1111: ForEach works for user-provided list sources not in the graph. This is the original bug — media:enc=utf-8;ext=txt;list is a user import source, not a cap output. Previously, no ForEach edge existed for it because insert_cardinality_transitions() only pre-computed edges for cap outputs. With dynamic synthesis, ForEach is available for ANY list source. | tests/test_live_cap_fab.py:484 |
| test1112 | `test_1112_no_collect_in_path_finding` | TEST1112: Collect is not synthesized during path finding. Reaching a list target type requires the cap itself to output a list type. | tests/test_live_cap_fab.py:529 |
| test1113 | `test_1113_multi_cap_path_no_collect` | TEST1113: Multi-cap path without Collect — Collect is not synthesized | tests/test_live_cap_fab.py:551 |
| test1114 | `test_1114_graph_stores_only_cap_edges` | TEST1114: Graph stores only Cap edges after sync | tests/test_live_cap_fab.py:573 |
| test1115 | `test_1115_dynamic_foreach_with_is_sequence` | TEST1115: ForEach is synthesized when is_sequence=true AND caps can consume items | tests/test_live_cap_fab.py:604 |
| test1116 | `test_1116_collect_never_synthesized` | TEST1116: Collect is never synthesized during path finding | tests/test_live_cap_fab.py:633 |
| test1117 | `test_1117_no_foreach_when_not_sequence` | TEST1117: ForEach is NOT synthesized when is_sequence=false | tests/test_live_cap_fab.py:655 |
| test1118 | `test_1118_no_foreach_without_cap_consumers` | TEST1118: ForEach not synthesized without cap consumers even with is_sequence=true | tests/test_live_cap_fab.py:678 |
| test1119 | `test_1119_strand_knit_with_registry_returns_single_strand_machine` | TEST1119: Strand::knit returns a single-strand Machine via the new resolver. Smoke test the registry-threaded API end-to-end. | tests/test_live_cap_fab.py:693 |
| test1120 | `test_1120_strand_knit_unknown_cap_fails_hard` | TEST1120: Strand::knit fails hard when the cap is not in the registry — the planner produces strands referencing caps that must be present in the cap registry's cache for resolution to succeed. | tests/test_live_cap_fab.py:734 |
| test1122 | `test_1122_full_path_engine_req_to_cartridge_response` | TEST1122: Full path: engine REQ → runtime → cartridge → response back through relay | tests/test_cbor_integration.py:489 |
| test1123 | `test_1123_cartridge_error_flows_to_engine` | TEST1123: Cartridge ERR frame flows back to engine through relay | tests/test_cbor_integration.py:592 |
| test1126 | `test_1126_map_progress_deterministic` | TEST1126: map_progress is deterministic — same inputs always produce same output | tests/test_executor.py:143 |
| test1127 | `test_1127_cap_documentation_round_trip_with_markdown_body` | TEST1127: Documentation field round-trips through JSON serialize/deserialize. | tests/test_cap.py:438 |
| test1128 | `test_1128_cap_documentation_omitted_when_none` | TEST1128: When documentation is None, the serializer must skip the field entirely. | tests/test_cap.py:465 |
| test1129 | `test_1129_cap_documentation_parses_from_capfab_json` | TEST1129: A JSON document produced by capfab (the canonical source) with a `documentation` field must deserialize into a Cap with the body intact. Models the actual on-disk shape — not a synthetic round-trip — to catch a mismatch between the JSON schema and the Rust struct field naming. | tests/test_cap.py:480 |
| test1130 | `test_1130_cap_documentation_set_and_clear_lifecycle` | TEST1130: documentation set/clear lifecycle parallels cap_description. | tests/test_cap.py:572 |
| test1133 | `test_1133_media_def_def_documentation_lifecycle` | TEST1133: MediaDef set/clear lifecycle for documentation. Catches a regression where the setter or clearer accidentally writes to or reads from `description` (the short field) instead of `documentation` (the long markdown body). | tests/test_media_def.py:593 |
| test1135 | `test_1135_strand_node_urn_accessor` | TEST1135: MachineStrand.node_urn(id) returns the MediaUrn at that NodeId. | tests/test_machine.py:598 |
| test1136 | `test_1136_parse_machine_undefined_alias_raises_syntax_error` | TEST1136: parse_machine with undefined cap alias raises MachineParseError wrapping UndefinedAliasError. | tests/test_machine.py:617 |
| test1140 | `test_1140_write_stream_chunked_reassembly` | TEST1140: write_stream_chunked (protocol v2) splits payload into STREAM_START → CHUNK(s) → STREAM_END → END with correct frame types, stream_id, media_urn, and data integrity. | tests/test_cbor_io.py:858 |
| test1141 | `test_1141_exact_max_chunk_stream_chunked` | TEST1141: write_stream_chunked with data exactly equal to max_chunk produces exactly one CHUNK | tests/test_cbor_io.py:900 |
| test1142 | `test_1142_resolved_graph_to_mermaid_renders_shapes_dedupes_edges_and_escapes` | TEST1142: ResolvedGraph.to_mermaid() renders node shapes, deduplicates edges, and escapes labels | tests/test_orchestrator_types.py:13 |
| test1143 | `test_1143_input_item_from_string_distinguishes_glob_directory_and_file` | TEST1143: InputItem::from_string distinguishes glob patterns, directories, and files | tests/test_input_resolver.py:585 |
| test1144 | `test_1144_content_structure_helpers_and_display` | TEST1144: ContentStructure is_list/is_record helpers and Display implementation are correct | tests/test_input_resolver.py:603 |
| test1145 | `test_1145_resolved_input_set_uses_equivalent_media_and_file_count_cardinality` | TEST1145: ResolvedInputSet uses URN equivalence for common_media and file count for is_sequence | tests/test_input_resolver.py:614 |
| test1146 | `test_1146_input_resolver_error_display_and_source` | TEST1146: InputResolverError subclass display messages and exception hierarchy are correct. | tests/test_input_resolver.py:648 |
| test1147 | `test_1147_machine_syntax_error_display_is_specific` | TEST1147: InvalidWiringError display message is human-readable and specific. | tests/test_machine.py:713 |
| test1148 | `test_1148_machine_parse_error_from_syntax_preserves_variant` | TEST1148: MachineParseError::from(MachineSyntaxError) preserves the syntax error variant | tests/test_machine.py:720 |
| test1149 | `test_1149_machine_parse_error_from_resolution_preserves_variant` | TEST1149: MachineParseError::from(MachineAbstractionError) preserves the resolution error variant | tests/test_machine.py:730 |
| test1150 | `test_1150_add_cap_and_basic_traversal` | TEST1150: Adding one cap creates one edge and makes its output reachable in one step. | tests/test_live_cap_fab.py:381 |
| test1151 | `test_1151_exact_vs_conformance_matching` | TEST1151: Exact target lookup prefers the direct singular or list-producing path over longer alternatives. | tests/test_live_cap_fab.py:401 |
| test1152 | `test_1152_multi_step_path` | TEST1152: Path finding returns the expected two-cap chain through an intermediate media type. | tests/test_live_cap_fab.py:425 |
| test1153 | `test_1153_deterministic_ordering` | TEST1153: Repeated path searches return the same path order for the same graph and target. | tests/test_live_cap_fab.py:441 |
| test1154 | `test_1154_sync_from_caps` | TEST1154: Syncing from caps replaces the existing graph contents with the new cap set. | tests/test_live_cap_fab.py:461 |
| test1155 | `test_1155_from_strand_produces_single_strand_machine` | TEST1155: Building a machine from one strand produces one strand with one resolved edge. | tests/test_machine.py:198 |
| test1156 | `test_1156_from_strands_keeps_strands_disjoint` | TEST1156: Building from multiple strands keeps them disjoint and preserves input strand order. | tests/test_machine.py:212 |
| test1157 | `test_1157_from_strands_empty_raises_no_capability_steps` | TEST1157: Building from zero strands fails with NoCapabilitySteps. | tests/test_machine.py:233 |
| test1158 | `test_1158_machine_is_equivalent_strict_positional_order_matters` | TEST1158: Machine equivalence is strict about strand order and rejects reordered strands. | tests/test_machine.py:240 |
| test1159 | `test_1159_strand_is_equivalent_consistent_node_bijection` | TEST1159: MachineStrand equivalence accepts two separately built but structurally identical strands. | tests/test_machine.py:261 |
| test1160 | `test_1160_machine_run_new_stores_canonical_notation` | TEST1160: Creating a MachineRun stores the canonical notation and starts in the pending state. | tests/test_machine.py:1016 |
| test1161 | `test_1161_simple_linear_chain_conversion` | TEST1161: Converting a simple linear plan produces resolved edges for the cap-to-cap chain. | tests/test_orchestrator_plan_converter.py:73 |
| test1162 | `test_1162_heartbeat_frame_with_memory_meta` | TEST1162: Heartbeat frames preserve self-reported memory values stored in metadata. | tests/test_cbor_frame.py:1718 |
| test1163 | `test_1163_parse_single_strand_two_caps_connected_via_shared_node` | TEST1163: Parsing one connected strand yields a single machine strand with both caps connected by the shared node. | tests/test_machine.py:1032 |
| test1164 | `test_1164_parse_machine_disconnected_wirings_become_separate_strands` | TEST1164: Parsing two disconnected strand definitions yields two separate machine strands. | tests/test_machine.py:399 |
| test1165 | `test_1165_parse_machine_unknown_cap_raises_parse_error_with_abstraction_cause` | TEST1165: Parsing fails hard when a referenced cap is missing from the registry cache. | tests/test_machine.py:363 |
| test1166 | `test_1166_parse_duplicate_alias_is_syntax_error` | TEST1166: Duplicate header aliases are reported as syntax errors. | tests/test_machine.py:750 |
| test1167 | `test_1167_parse_undefined_alias_is_syntax_error` | TEST1167: Wiring that references an undefined alias is reported as a syntax error. | tests/test_machine.py:763 |
| test1168 | `test_1168_parse_node_alias_collision_with_header_alias_fails_hard` | TEST1168: Parsing rejects node names that collide with declared cap aliases. | tests/test_machine.py:775 |
| test1169 | `test_1169_sequence_into_scalar_cap_derives_is_loop` | TEST1169: A sequence-output cap feeding a scalar-input cap makes the resolved edge a per-item map (is_loop), derived from cardinality — the single rule Cap.needs_foreach, which replaces the retired `LOOP` keyword. The scalar->sequence producer edge itself does not loop. | tests/test_machine.py:791 |
| test1170 | `test_1170_parse_then_serialize_round_trips_to_canonical_form` | TEST1170: Parsing and then serializing machine notation round-trips to the canonical form. | tests/test_machine.py:827 |
| test1171 | `test_1171_machine_parse_error_wraps_syntax_error` | TEST1171: Empty machine notation is rejected as a syntax error. | tests/test_machine.py:351 |
| test1172 | `test_1172_serialize_two_step_strand_emits_global_aliases_and_node_names` | TEST1172: Serializing a two-step strand emits the expected aliases and node names. | tests/test_machine.py:853 |
| test1173 | `test_1173_serialize_then_parse_round_trip_preserves_strict_equivalence` | TEST1173: Serializing and reparsing a machine preserves strict machine equivalence. | tests/test_machine.py:871 |
| test1174 | `test_1174_line_based_format_round_trips_to_same_machine` | TEST1174: The line-based notation format round-trips back to the same machine. | tests/test_machine.py:888 |
| test1175 | `test_1175_empty_machine_serializes_to_empty_string` | TEST1175: Serializing an empty machine produces an empty string. | tests/test_machine.py:904 |
| test1176 | `test_1176_render_payload_json_includes_strand_with_anchors` | TEST1176: Rendering payload JSON includes strand anchor metadata for a populated machine. | tests/test_machine.py:912 |
| test1177 | `test_1177_render_payload_for_empty_machine_has_empty_strands_array` | TEST1177: Rendering payload JSON for an empty machine emits an empty strands array. | tests/test_machine.py:935 |
| test1178 | `test_1178_match_single_source_picks_unique_arg` | TEST1178: One source is assigned to the single compatible cap argument. | tests/test_machine.py:1057 |
| test1179 | `test_1179_match_sources_more_specific_source_matches_general_arg` | TEST1179: Source-to-arg matching assigns a more specific source to a compatible general argument. | tests/test_machine.py:287 |
| test1180 | `test_1180_match_sources_unmatched_source_fails_hard` | TEST1180: Matching fails when a source does not conform to any cap input argument. | tests/test_machine.py:297 |
| test1181 | `test_1181_match_two_sources_disambiguated_by_specificity` | TEST1181: Two sources disambiguated by specificity — unique minimum-cost assignment. | tests/test_machine.py:947 |
| test1182 | `test_1182_match_sources_ambiguous_raises_ambiguous_error` | TEST1182: Matching fails as ambiguous when two sources can be swapped at equal minimum cost. | tests/test_machine.py:311 |
| test1183 | `test_1183_match_more_sources_than_args_fails_hard` | TEST1183: Matching fails when more sources are provided than the cap has input arguments. | tests/test_machine.py:967 |
| test1184 | `test_1184_single_edge_strand_resolves_correctly` | TEST1184: Resolving a strand with one cap produces one resolved machine edge. | tests/test_machine.py:144 |
| test1185 | `test_1185_resolve_strand_chained_caps_share_intermediate_node` | TEST1185: Resolving a chained strand reuses the intermediate node between adjacent caps. | tests/test_machine.py:1068 |
| test1186 | `test_1186_resolve_strand_foreach_marks_following_cap_as_loop` | TEST1186: A ForEach step immediately following disbind is elided; is_loop is derived from cardinality: disbind produces a SEQUENCE of pages, and make_decision consumes a scalar page, so make_decision's edge maps per item. The trailing Collect step is also elided. | tests/test_machine.py:1104 |
| test1187 | `test_1187_unknown_cap_error_when_not_in_registry` | TEST1187: Strand resolution fails when a referenced cap is not found in the registry. | tests/test_machine.py:129 |
| test1188 | `test_1188_resolve_strand_no_cap_steps_fails_hard` | TEST1188: Strand resolution fails when the strand contains no capability steps. | tests/test_machine.py:122 |
| test1189 | `test_1189_resolve_strand_canonical_anchor_order_is_stable` | TEST1189: Strand resolution keeps canonical anchor ordering stable across equivalent inputs. | tests/test_machine.py:976 |
| test1190 | `test_1190_resolve_strand_inverse_format_converters_no_cycle` | TEST1190: Inverse format converters resolve without introducing a cycle in the strand graph. | tests/test_machine.py:991 |
| test1191 | `test_1191_resolve_strand_disbind_pdf_with_file_path_slot_identity` | TEST1191: Disbinding a PDF with a file-path slot preserves the expected identity of the slot binding. | tests/test_machine.py:1171 |
| test1196 | `test_1196_aliased_serialization_uses_alias_and_round_trips` | TEST1196: `to_machine_notation_aliased` renders a cap by its registered display alias (shortest, then alphabetical), referenced directly in the wiring with no header; falls back to the raw URN + header for a cap with no alias; and the result round-trips back to the same machine (the parser resolves the alias from the warm cache). | tests/test_machine.py:1206 |
| test1221 | `test_1221_refine_with_matching_adapter` | TEST1221: Matching value adapters refine the base media URN when the value fits. | tests/test_input_resolver.py:358 |
| test1222 | `test_1222_refine_no_matching_adapter` | TEST1222: Base URNs without a registered adapter are returned unchanged. | tests/test_input_resolver.py:367 |
| test1223 | `test_1223_refine_adapter_returns_none` | TEST1223: Adapters that decline to refine leave the original media URN intact. | tests/test_input_resolver.py:374 |
| test1224 | `test_1224_refine_longest_prefix_match` | TEST1224: When multiple adapter prefixes match, the longest prefix wins. | tests/test_input_resolver.py:381 |
| test1225 | `test_1225_empty_registry` | TEST1225: An empty value adapter registry returns the input media URN unchanged. | tests/test_input_resolver.py:389 |
| test1226 | `test_1226_has_adapter` | TEST1226: Adapter presence checks report only the prefixes that were registered. | tests/test_input_resolver.py:395 |
| test1228 | `test_1228_value_adapter_refine_match` | TEST1228: Value adapters can append a more specific marker when both base URN and value match. | tests/test_input_resolver.py:403 |
| test1229 | `test_1229_value_adapter_refine_no_match_base` | TEST1229: Value adapters return no refinement when the base media URN is outside their domain. | tests/test_input_resolver.py:409 |
| test1230 | `test_1230_value_adapter_refine_no_match_value` | TEST1230: Value adapters return no refinement when the inspected value does not match. | tests/test_input_resolver.py:415 |
| test1235 | `test_1235_disc_1_plain_text_eliminates_model_specs` | TEST1235: Plain text without model-spec syntax eliminates model-spec TXT candidates. | tests/test_input_resolver.py:421 |
| test1236 | `test_1236_disc_2_model_spec_validation_pattern_filters_content` | TEST1236: Colon-delimited model spec text survives TXT candidate discrimination. TEST1236: Discrimination matches a candidate's validation pattern against the file content. media:model-spec is a value type with no associated file extension, so it does NOT appear among txt candidates. When passed in explicitly as a candidate, content that matches its `^(scheme):\S+$` regex must survive; content that doesn't (plain prose with whitespace) must be filtered out. | tests/test_input_resolver.py:437 |
| test1237 | `test_1237_disc_5_empty_candidates` | TEST1237: Empty candidates → empty result | tests/test_input_resolver.py:463 |
| test1238 | `test_1238_disc_6_unknown_urn_survives` | TEST1238: Unknown URN survives discrimination | tests/test_input_resolver.py:471 |
| test1256 | `test_1256_parse_simple_machine` | TEST1256: Parsing a single-cap machine notation produces a graph with 2 nodes and 1 edge. | tests/test_orchestrator_parser.py:45 |
| test1257 | `test_1257_parse_two_step_chain` | TEST1257: Two sequential wirings preserve the intermediate node media type. | tests/test_orchestrator_parser.py:66 |
| test1258 | `test_1258_parse_fan_out` | TEST1258: One source node can fan out into multiple caps and target nodes. | tests/test_orchestrator_parser.py:111 |
| test1259 | `test_1259_parse_fan_in` | TEST1259: Fan-in wiring resolves multiple upstream outputs into one multi-arg cap. | tests/test_orchestrator_parser.py:135 |
| test1260 | `test_1260_loop_keyword_retired` | TEST1260: The `LOOP` keyword is retired from the grammar. A keyword-free wiring parses to a single edge; the old `LOOP` form no longer parses. ForEach is never authored — it is derived from cardinality in the resolver/realizer. | tests/test_orchestrator_parser.py:162 |
| test1261 | `test_1261_cap_not_found_in_registry` | TEST1261: A cap URN not present in the registry cache causes a parse orchestration error. | tests/test_orchestrator_parser.py:88 |
| test1262 | `test_1262_invalid_machine_notation` | TEST1262: Non-machine text fails with a machine syntax parse error. | tests/test_orchestrator_parser.py:103 |
| test1263 | `test_1263_cycle_detection` | TEST1263: Cyclic wirings are rejected as non-DAG orchestrations. | tests/test_orchestrator_parser.py:181 |
| test1264 | `test_1264_incompatible_media_types_at_shared_node` | TEST1264: Shared nodes with incompatible upstream and downstream media fail during parsing. | tests/test_orchestrator_parser.py:198 |
| test1265 | `test_1265_compatible_media_urns_at_shared_node` | TEST1265: Compatible media urns at shared node | tests/test_orchestrator_parser.py:227 |
| test1266 | `test_1266_structure_mismatch_record_to_opaque` | TEST1266: Record-to-opaque structure mismatches are rejected once structure checking is enabled. | tests/test_orchestrator_parser.py:247 |
| test1267 | `test_1267_structure_match_both_record` | TEST1267: Record-shaped outputs can feed record-shaped inputs without error. | tests/test_orchestrator_parser.py:267 |
| test1268 | `test_1268_structure_match_both_opaque` | TEST1268: Opaque outputs can feed opaque inputs without triggering structure conflicts. | tests/test_orchestrator_parser.py:286 |
| test1269 | `test_1269_parse_multiline_machine` | TEST1269: Multi-line machine notation parses successfully with the same semantics as inline notation. | tests/test_orchestrator_parser.py:305 |
| test1271 | `test_1271_media_adapter_selection_constant` | TEST1271: MEDIA_ADAPTER_SELECTION constant parses and has expected tags | tests/test_media_urn.py:501 |
| test1272 | `test_1272_adapter_cap_constant_parses` | TEST1272: CAP_ADAPTER_SELECTION constant parses as a valid CapUrn | tests/test_standard_caps.py:145 |
| test1273 | `test_1273_adapter_selection_urn_builder` | TEST1273: adapter_selection_urn() returns a valid CapUrn with correct in/out specs | tests/test_standard_caps.py:152 |
| test1275 | `test_1275_adapter_selection_dispatchable_by_specific_candidate` | TEST1275: A cap whose output is adapter-selection can dispatch adapter-selection requests; identity (wildcard output) cannot, because wildcard output cannot satisfy a specific output requirement. | tests/test_standard_caps.py:165 |
| test1276 | `test_1276_register_non_conflicting` | TEST1276: Registration of a cap group with non-conflicting adapters succeeds | tests/test_input_resolver.py:480 |
| test1277 | `test_1277_reject_conforming_overlap` | TEST1277: Registration of a cap group with an adapter that conforms_to an existing adapter is rejected | tests/test_input_resolver.py:487 |
| test1278 | `test_1278_reject_entire_group` | TEST1278: Registration rejects the entire group — no partial registration | tests/test_input_resolver.py:498 |
| test1279 | `test_1279_intra_group_conflict` | TEST1279: Intra-group conflict (two adapters within same group overlap) is rejected | tests/test_input_resolver.py:507 |
| test1280 | `test_1280_find_adapters_for_extension` | TEST1280: find_adapters_for_extension returns correct cartridge IDs | tests/test_input_resolver.py:514 |
| test1281 | `test_1281_no_adapter_for_unknown` | TEST1281: has_adapter_for_extension returns false for unregistered extension | tests/test_input_resolver.py:523 |
| test1282 | `test_1282_adapter_selection_auto_registered` | TEST1282: AdapterSelectionOp is auto-registered by CartridgeRuntime | tests/test_cartridge_runtime.py:2370 |
| test1283 | `test_1283_adapter_selection_custom_override` | TEST1283: Custom adapter selection Op overrides the default | tests/test_cartridge_runtime.py:2377 |
| test1284 | `test_1284_cap_group_with_adapter_urns` | TEST1284: Cap group with adapter URNs serializes and deserializes correctly | tests/test_manifest.py:297 |
| test1285 | `test_1285_confirmed_no_adapters_fails` | TEST1285: detect_file_confirmed fails when no adapters are registered for the extension | tests/test_input_resolver.py:530 |
| test1286 | `test_1286_confirmed_adapter_returns_urns` | TEST1286: detect_file_confirmed succeeds when adapter returns URNs | tests/test_input_resolver.py:540 |
| test1287 | `test_1287_confirmed_all_adapters_no_match` | TEST1287: detect_file_confirmed fails when all adapters return empty END (no match) | tests/test_input_resolver.py:557 |
| test1288 | `test_1288_structure_from_marker_tags` | TEST1288: structure_from_marker_tags correctly maps tag combinations to ContentStructure | tests/test_input_resolver.py:275 |
| test1289 | `test_1289_bfs_reachable_includes_source_roundtrip` | TEST1289: BFS reachable targets includes the source itself when round-trip paths exist. A→B and B→A means A is reachable from A (via A→B→A). | tests/test_live_cap_fab.py:273 |
| test1290 | `test_1290_iddfs_finds_roundtrip_paths` | TEST1290: IDDFS find_paths_to_exact_target finds round-trip paths when source == target. | tests/test_live_cap_fab.py:298 |
| test1291 | `test_1291_iddfs_roundtrip_with_sequence` | TEST1291: IDDFS round-trip paths are also found with is_sequence=true. The ForEach/Collect edges must not block round-trip discovery. | tests/test_live_cap_fab.py:325 |
| test1292 | `test_1292_bfs_iddfs_roundtrip_consistency` | TEST1292: BFS and IDDFS agree that round-trip targets exist. | tests/test_live_cap_fab.py:350 |
| test1293 | `test_1293_roundtrip_requires_cap_steps` | TEST1293: IDDFS round-trip does not produce paths with 0 cap steps. Identity-only round trips (no real transformation) must be excluded. | tests/test_live_cap_fab.py:367 |
| test1294 | `test_1294_rule11_void_input_with_stdin` | TEST1294: RULE11 - void-input cap with stdin source rejected | tests/test_validation.py:301 |
| test1295 | `test_1295_rule11_non_void_input_without_stdin` | TEST1295: RULE11 - non-void-input cap without stdin source rejected | tests/test_validation.py:313 |
| test1296 | `test_1296_rule11_void_input_cli_flag_only` | TEST1296: RULE11 - void-input cap with only cli_flag sources passes | tests/test_validation.py:325 |
| test1297 | `test_1297_rule11_non_void_input_with_stdin` | TEST1297: RULE11 - non-void-input cap with stdin source passes | tests/test_validation.py:335 |
| test1300 | `test_1300_sequence_item_fragments_reassemble_into_one_item` | TEST1300: A sequence item CBOR-encoded once and split across multiple CHUNK frames (the emit_list_item framing) reassembles into exactly one delivered item carrying the first fragment's per-item metadata. | tests/test_cartridge_runtime.py:2878 |
| test1301 | `test_1301_sequence_stream_truncated_mid_item_fails_hard` | TEST1301: A sequence stream that ENDs mid-item (trailing fragment bytes that never complete a CBOR item) surfaces a hard decode error instead of silently dropping the partial item. | tests/test_cartridge_runtime.py:2929 |
| test1302 | `test_1302_sequence_fragment_frames_are_credited_on_arrival` | TEST1302: Continuation fragments of a multi-frame sequence item are credited back by the demux on arrival — the handler grants one frame per consumed item, so without fragment grants an item spanning more frames than the credit window could never finish arriving. | tests/test_cartridge_runtime.py:2952 |
| test1308 | `test_1308_cyclic_strand_fails_hard` | TEST1308: A wiring that forms a cycle raises CyclicMachineStrandError. | tests/test_machine.py:325 |
| test1309 | `test_1309_parse_machine_single_wiring_one_strand` | TEST1309: Parsing a single-cap machine notation produces one strand with one edge. | tests/test_machine.py:381 |
| test1310 | `test_1310_strand_equivalence_rejects_mismatched_node_urns` | TEST1310: Two strands differing only in one node's media URN are not equivalent (Python-specific coverage). | tests/test_machine.py:489 |
| test1311 | `test_1311_machine_from_string_delegates_to_parse_machine` | TEST1311: Machine.from_string is an alias for parse_machine — both produce equivalent results (Python-specific coverage). | tests/test_machine.py:560 |
| test1312 | `test_1312_record_appends_one_json_line_per_snapshot` | TEST1312: Two snapshots recorded to a temp file produce exactly two JSONL lines, each carrying ts + segment + a round-tripped stats object (requests/drops). | tests/test_protocol_trace.py:89 |
| test1313 | `test_1313_record_deduped_writes_only_on_change` | TEST1313: Dedup: recording identical protocol state twice writes ONE line; a real change (a bumped counter, a moved stream byte) writes another. This is what keeps a stalled engine's repeated live samples from spamming the trace. | tests/test_protocol_trace.py:118 |
| test1314 | `test_1314_fingerprint_ignores_advancing_clocks` | TEST1314: The fingerprint EXCLUDES advancing clocks: two snapshots differing only in age_ms/idle_ms are the same transition, while a flow-counter change is a new one. If dedup keyed on the whole serialized stats, these clocks would defeat it and every sample would write. | tests/test_protocol_trace.py:140 |
| test1315 | `test_1315_record_to_unwritable_path_is_a_hard_error` | TEST1315: Requested diagnostics fail HARD, never silently: a write to an unwritable sink raises. `/dev/full` opens fine but every write is ENOSPC -- the Linux-standard way to exercise a write failure deterministically. | tests/test_protocol_trace.py:157 |
| test1317 | `test_1317_wrap_raw_items_empty` | TEST1317: empty item list wraps to empty bytes (mirrors the scalar/empty sink case where a chain produced no items). | tests/test_cbor_util.py:240 |
| test1800 | `test_1800_kind_identity_only_for_bare_cap` | TEST1800: Identity classifier — and only explicit effect=none qualifies. | tests/test_cap_urn.py:1502 |
| test1801 | `test_1801_kind_source_when_input_is_void` | TEST1801: Source classifier — in=media:void, out non-void. The y dimension may carry any tags; void on the input alone is what matters. | tests/test_cap_urn.py:1527 |
| test1802 | `test_1802_kind_sink_when_output_is_void` | TEST1802: Sink classifier — out=media:void, in non-void. | tests/test_cap_urn.py:1536 |
| test1803 | `test_1803_kind_effect_when_both_sides_void` | TEST1803: Effect classifier — both sides void. Reads as `() → ()`. | tests/test_cap_urn.py:1545 |
| test1804 | `test_1804_kind_transform_for_normal_data_processors` | TEST1804: Transform classifier — at least one side non-void, and the cap is not the bare identity. The default kind for ordinary data-processing caps. | tests/test_cap_urn.py:1554 |
| test1805 | `test_1805_kind_invariant_under_canonical_spellings` | TEST1805: Kind is invariant under canonicalization. The same morphism written in many surface forms must classify the same way once parsed. This pins the rule that kind is a property of the cap as a structured object, not of any particular spelling. | tests/test_cap_urn.py:1563 |
| test1810 | `test_1810_media_void_is_atomic` | TEST1810: media:void is atomic — refinements are parse errors. Mirrored across every language port (Rust, Go, Python, Swift/ObjC, JS) under the SAME number. Any divergence is a wire-level inconsistency — the unit type's atomicity is part of the protocol's deepest layer, not a per-port detail. The bare `media:void` parses successfully; any combination with another tag (marker or key=value) MUST fail with VoidNotAtomic. This forecloses a fake taxonomy of unit values; reasons or labels for *why* void is used belong on the cap URN's non-directional tags or in cap args. | tests/test_media_urn.py:513 |
| test1820 | `test_1820_specificity_question_is_zero` | TEST1820: A `?`-valued cap-tag scores 0. Same as missing. | tests/test_cap_urn.py:1605 |
| test1821 | `test_1821_specificity_must_not_have_is_five` | TEST1821: A `!`-valued cap-tag scores 5 (top of negative chain). | tests/test_cap_urn.py:1616 |
| test1822 | `test_1822_specificity_must_have_any_is_two` | TEST1822: A `*`-valued cap-tag (including bare markers) scores 2. | tests/test_cap_urn.py:1622 |
| test1823 | `test_1823_specificity_exact_value_is_four` | TEST1823: An exact-valued cap-tag scores 4. | tests/test_cap_urn.py:1639 |
| test1824 | `test_1824_specificity_combined_y_axis` | TEST1824: All six forms compose additively on a single cap. This pins the truth-table sum across the y axis as a whole. | tests/test_cap_urn.py:1645 |
| test1830 | `test_1830_canonicalize_no_constraint` | TEST1830: ?x ≡ x? ≡ x=? all canonicalize to ?x. | tests/test_cap_urn.py:1663 |
| test1831 | `test_1831_canonicalize_absent_or_not_value` | TEST1831: ?x=v and x?=v both canonicalize to x?=v. The third hypothetical form `x=?v` is NOT recognized as a qualifier — a value starting with `?` is just an exact value beginning with a `?` character. | tests/test_cap_urn.py:1673 |
| test1832 | `test_1832_canonicalize_must_have_any` | TEST1832: x ≡ x=* both canonicalize to bare x. | tests/test_cap_urn.py:1689 |
| test1833 | `test_1833_canonicalize_present_not_value` | TEST1833: !x=v and x!=v both canonicalize to x!=v. The third hypothetical form `x=!v` is NOT recognized as a qualifier — a value starting with `!` is just an exact value beginning with a `!` character. | tests/test_cap_urn.py:1699 |
| test1834 | `test_1834_canonicalize_exact_value` | TEST1834: x=v stays as x=v (the lone exact-value form). | tests/test_cap_urn.py:1715 |
| test1835 | `test_1835_canonicalize_must_not_have` | TEST1835: !x ≡ x! ≡ x=! all canonicalize to !x. | tests/test_cap_urn.py:1721 |
| test1842 | `test_1842_truth_table_full_cross_product` | TEST1842: Full 6×6 truth table — every cell must match the matrix in 04-PREDICATES.md §2.5. Treats prefix `cap:` as the host for a single-key URN (key `x`), pairing every instance form with every pattern form. | tests/test_cap_urn.py:1731 |
| test1845 | `test_1845_axis_weighting_in_dominates_y` | TEST1845: With equal out-axis, in-axis dominates over y-axis. | tests/test_cap_urn.py:1790 |
| test1847 | `test_1847_cartridge_build_legacy_package_fallback` | TEST1847: A build from a registry manifest published BEFORE `packages[]` existed carries only the legacy singular `package` (no `format`). It must still deserialize (a missing `packages` must not fail the whole parse) and `primary_package()` must fall back to that legacy package, so a registry not yet republished with the dual-write keeps installing. When `packages[]` is present it is preferred over the legacy field. | tests/test_cartridge_repo.py:764 |
| test1849 | `test_1849_resolve_for_host_compatible_latest` | TEST1849: latest version has a host build → Compatible, resolving to the latest version and that platform's native-format package. | tests/test_cartridge_repo.py:848 |
| test1850 | `test_1850_resolve_for_host_compatible_outdated` | TEST1850: the latest version lacks a host build but an older version has one → CompatibleOutdated, resolving to the older version with a reason naming both the latest and the resolved version. | tests/test_cartridge_repo.py:866 |
| test1851 | `test_1851_resolve_for_host_incompatible` | TEST1851: no version ships a host build → Incompatible, no resolved version/package, reason states the host platform. | tests/test_cartridge_repo.py:886 |
| test1852 | `test_1852_resolve_for_host_skips_build_with_no_installer` | TEST1852: a host build whose packages[] is empty AND has no legacy `package` ships no installer; resolution must SKIP it (not resolve to an un-downloadable version) and fall through to an older usable version. | tests/test_cartridge_repo.py:902 |
| test1853 | `test_1853_host_platform_normalized_form` | TEST1853: host_platform() returns a normalized {os}-{arch} string with arch aarch64 mapped to arm64 — the exact form the registry uses. | tests/test_cartridge_repo.py:923 |
| test1871 | `test_1871_sync_roster_adds_and_removes_registered_dir_live` | TEST1871: SyncRoster updates the LIVE host inventory in place — the engine sees an added registered-dir cartridge via a fresh RelayNotify without reconnecting, and a subsequent empty sync removes it. This is the macOS-XPC `syncDiscoveryOutcomes` parity path the daemon uses after a registry verdict flips a held cartridge to Listed. | tests/test_cartridge_host.py:1185 |
| test1872 | `test_1872_registry_url_from_build_env_passes_through_nonempty` | TEST1872: `registry_url_from_build_env` passes a non-empty registry URL through unchanged. This is the function that decides the engine's baked PRIMARY registry (surfaced over SystemService.HealthStatus); a published build must report exactly the URL it was compiled with. | tests/test_manifest.py:319 |
| test1873 | `test_1873_registry_url_from_build_env_none_for_dev` | TEST1873: an unset env (None) yields None — a dev build has no baked registry, so the engine reports an empty primary-registry URL and loads only `dev/` cartridges. This is the dev-engine contract the registry sheets rely on to omit the read-only "Primary · built-in" row. | tests/test_manifest.py:325 |
| test1874 | `test_1874_registry_url_from_build_env_rejects_empty_string` | TEST1874: an exported-but-empty env (`Some("")`) is neither a dev build nor a valid identity and MUST fail hard at compile time, so the build can never silently hash the empty string into a fake registry slug. We assert the panic rather than letting a bogus empty primary registry ship. | tests/test_manifest.py:379 |
| test1875 | `test_1875_scan_all_reaches_both_dev_and_registry_slugs` | TEST1875: scan-all — a registry slug folder AND the dev slot present on disk are BOTH scanned, regardless of the host's own baked registry. The dev cartridge (null registry under dev/) and the registry cartridge (its url hashing to its slug folder) each reach their probe. Both fixtures lack a real bifaci binary, so both end at HandshakeFailed — proving discovery REACHED them (was not filtered out by a registry pin), which is the behavior under test. A registry-pin rejection would instead surface BadInstallation and never probe. | tests/test_cartridge_discovery.py:124 |
| test1876 | `test_1876_other_channel_subtree_is_skipped` | TEST1876: only the host's channel subtree is scanned. A cartridge under a slug's `release/` folder is invisible to a nightly host even though the slug folder is present (its `nightly/` subtree is absent). | tests/test_cartridge_discovery.py:154 |
| test1877 | `test_1877_registry_cartridge_under_wrong_slug_is_bad_install` | TEST1877: a registry cartridge hand-copied under the WRONG registry slug folder fails the three-place rule (BadInstallation) — scan-all does not mean "accept anywhere", placement must still be self-consistent. | tests/test_cartridge_discovery.py:168 |
| test1878 | `test_1878_bundled_cartridge_without_baked_hash_is_rejected` | TEST1878: a cartridge marked `installed_from: bundle` with no baked hash in BUNDLED_CARTRIDGE_HASHES (the const is empty under plain `cargo test`) is rejected as BadInstallation — the bundled-integrity gate fires before the probe. Proves the verify is wired into discovery; a real bundle build bakes the hash so the matching directory passes. Non-macOS only: on macOS the baked-hash path is intentionally absent (OS code-signature is the guard), so a bundled cartridge is accepted there and would instead end at the probe. | tests/test_cartridge_discovery.py:179 |
| test1880 | `test_1880_alias_name_normalization_rules` | TEST1880: alias name normalization lowercases and accepts the allowed character class; rejects colon, whitespace, and out-of-class chars with the right error. A broken validator would let a URN-shaped or whitespace name through, or mangle a valid name. | tests/test_fabric_alias.py:53 |
| test1881 | `test_1881_token_urn_vs_alias_detection` | TEST1881: URN-vs-alias detection keys purely on the presence of ':'. The whole design rests on this discriminator being exact. | tests/test_fabric_alias.py:69 |
| test1882 | `test_1882_classify_alias_target_by_prefix` | TEST1882: alias target classification distinguishes cap from media by prefix and rejects a non-URN target. The typed-boundary enforcement in the registry depends on this. | tests/test_fabric_alias.py:78 |
| test1883 | `test_1883_cap_position_alias_resolves_to_cap` | TEST1883: a cap-position name with no local header resolves as a cap alias. | tests/test_fabric_alias.py:214 |
| test1884 | `test_1884_local_header_shadows_cap_alias` | TEST1884: a local header alias shadows a fabric alias of the same name. | tests/test_fabric_alias.py:224 |
| test1885 | `test_1885_cap_position_alias_to_media_is_error` | TEST1885: a cap-position alias that resolves to a MEDIA URN is a hard error. | tests/test_fabric_alias.py:236 |
| test1886 | `test_1886_unregistered_cap_name_is_undefined_alias` | TEST1886: a cap-position name that is neither a local header nor a registered alias still raises UndefinedAlias. The alias mechanism must not mask a genuinely undefined name. | tests/test_fabric_alias.py:256 |
| test1887 | `test_1887_manifest_serde_round_trips_aliases` | TEST1887: the Manifest type round-trips an `aliases` map. | tests/test_fabric_alias.py:93 |
| test1888 | `test_1888_resolve_alias_returns_target` | TEST1888: resolve_alias returns the alias target untyped. Seeding a media alias and resolving it yields the media URN; a malformed alias name is rejected before any lookup. | tests/test_fabric_alias.py:111 |
| test1889 | `test_1889_resolve_alias_typed_enforces_kind` | TEST1889: resolve_alias_typed enforces the expected kind. | tests/test_fabric_alias.py:124 |
| test1890 | `test_1890_get_cap_via_alias_and_type_mismatch` | TEST1890: get_cap accepts a cap alias and returns the aliased cap; a media alias passed to get_cap fails hard (typed boundary). This proves alias substitution AND type enforcement at the registry's cap surface. | tests/test_fabric_alias.py:140 |
| test1891 | `test_1891_get_media_def_via_alias_and_type_mismatch` | TEST1891: get_media_def accepts a media alias and returns the aliased spec; a cap alias passed to get_media_def fails hard. | tests/test_fabric_alias.py:164 |
| test1892 | `test_1892_unknown_alias_is_not_found` | TEST1892: an unknown alias name is a hard not-found, never a silent empty; unknown and malformed names are treated the same. This is the "expose issues, no fallback" contract. | tests/test_fabric_alias.py:190 |
| test1893 | `test_1893_cache_root_is_namespaced_per_registry_origin` | TEST1893: Cache root is namespaced per registry origin. Without the per-origin namespace, a cache populated from one registry (prod) is reused to satisfy a lookup against a different registry (staging) — and they serve different bytes for the same URN/version, so the lookup resolves against the wrong snapshot. This pins three properties: distinct origins must NOT share a cache root; the same origin must map to a stable (deterministic) root, or caching never hits; and the slug is the same slug_for(url) scheme the cartridge registry layout uses, living directly under the shared "capdag" cache directory. | tests/test_registry.py:430 |
| test1894 | `test_1894_select_display_alias_ordering` | TEST1894: select_display_alias picks the SHORTEST name, ties broken alphabetically. This is the deterministic ordering every aliased-display surface relies on; a regression here silently changes which alias the whole UI renders. | tests/test_fabric_alias.py:267 |
| test1895 | `test_1895_display_alias_for_urn` | TEST1895: display_alias_for_urn reverse-resolves a URN to its display alias. Proves: (1) the shortest-then-alphabetical winner among multiple aliases on the same target, (2) a NON-canonical query URN (different tag order) still resolves because the query is canonicalised before matching, (3) a URN with no alias returns None, (4) a non-URN string returns None. | tests/test_fabric_alias.py:279 |
| test1896 | `test_1896_cached_cap_aliases_filters_to_cap_targets` | TEST1896: cached_cap_aliases returns only CAP-targeted aliases as (name, target) pairs — media aliases are excluded. Drives the notation editor's registered-alias completions. | tests/test_fabric_alias.py:319 |
| test1897 | `test_1897_unhealthy_master_inventory_retained_but_not_routable` | TEST1897: the installed-cartridge INVENTORY is NOT health-filtered. A master held unhealthy by a failed probe still has its cartridges visible in the inventory aggregate, even though its caps are excluded from routing. | tests/test_relay_switch.py:1443 |
| test1898 | `test_1898_subscribe_capabilities_delivers_routable_set` | TEST1898: the routable-capability watch (subscribe_capabilities). A subscriber must receive the CURRENT routable cap set on subscribe even though it was rebuilt during construction — BEFORE any receiver existed (the watch must persist the value, i.e. send_replace, not a plain broadcast that drops it with zero receivers). The delivered set is the health-filtered routable cap URNs. | tests/test_relay_switch.py:1477 |
| test1899 | `test_1899_media_def_resolves_to_versioned_object_path_under_manifest` | TEST0144: a media def published under a manifest (v>=1) resolves to the VERSIONED object path `/media/<sha>/<defver>.json`, never the legacy flat path `/media/<sha>`. The flat path is the pre-manifest (v0) layout; a registry that silently runs in v0 mode fetches it and 404s every lookup against a versioned registry — the exact regression where a fabric-registry mirror defaulted its manifest version to 0. This pins both the URL rule and the manifest-driven defver resolution. | tests/test_registry.py:326 |
| test1900 | `test_1900_err_frame_failure_class_wire_contract` | TEST1900: the ERR frame failure-class wire contract (docs/failure-taxonomy.md): err_classified writes meta code+class+message; plain err defaults class to internal; a missing or unknown class token reads as INTERNAL (unclassified means "ours", never a guess); a known token round-trips exactly. | tests/test_cbor_frame.py:1742 |
| test1904 | `test_1904_add_master_probe_failure_registers_unhealthy_not_raises` | Gap-5 lock: an add_master identity-probe FAILURE registers the master as UNHEALTHY (inventory visible) rather than RAISING — matching the reference add_master (and unlike the constructor, which raises; see test_488). | tests/test_relay_switch.py:1531 |
| test6189 | `test_6189_same_cap_different_spellings_same_hash` | TEST6189: Different URN spellings of the same cap (different tag order, whitespace, quoting) MUST produce the same SHA-256 hash, because the canonicaliser reduces them to the same string before hashing. This is the property that makes cross-language lookups land at the same registry key regardless of which capdag implementation issued the request. | tests/test_registry.py:152 |
| test6203 | `test_6203_matching_semantics_wildcard_direction` | TEST6203: Matching semantics - generic legal wildcard cap matches specific caps | tests/test_cap_urn.py:701 |
| test6211 | `test_6211_cap_version_zero_round_trip` | TEST6211: Cap.version=0 round-trip — zero is the default and must NOT appear in the serialized dict | tests/test_cap.py:403 |
| test6215 | `test_6215_cap_version_nonzero_round_trip` | TEST6215: Cap.version nonzero round-trip — emitted in dict and restored on deserialization | tests/test_cap.py:420 |
| test6231 | `test_6231_wildcard_empty_cap_defaults` | TEST6231: cap: (empty) is the illegal bare top form | tests/test_cap_urn.py:935 |
| test6235 | `test_6235_lookup_cap_fabric_has_defver_arg` | TEST6235: lookup_cap_fabric_cap has a --defver arg with MEDIA_FABRIC_DEFVER and required==False | tests/test_standard_caps.py:181 |
| test6239 | `test_6239_lookup_media_def_fabric_has_defver_arg` | TEST6239: lookup_media_def_fabric_cap has a --defver arg with MEDIA_FABRIC_DEFVER and required==False | tests/test_standard_caps.py:206 |
| test6264 | `test_6264_cartridge_json_fabric_manifest_version_zero_round_trip` | TEST6264: CartridgeJson fabric_manifest_version=0 is the default and absent from wire dict | tests/test_cartridge_repo.py:953 |
| test6268 | `test_6268_cartridge_json_fabric_manifest_version_nonzero_round_trip` | TEST6268: CartridgeJson fabric_manifest_version nonzero is emitted and restored | tests/test_cartridge_repo.py:973 |
| test6282 | `test_6282_resolve_custom_media_def` | TEST6282: Test resolving a custom media URN from a registry-seeded media def | tests/test_media_def.py:622 |
| test6283 | `test_6283_resolve_custom_with_schema` | TEST6283: Test resolving a custom record media def carrying a schema from a registry-seeded media def | tests/test_media_def.py:640 |
| test6314 | `test_6314_complex_nested_schema_validation` | TEST6314: Complex nested schema validation | tests/test_schema_validation.py:389 |
| test6317 | `test_6317_media_urn_resolution_with_registry` | TEST6317: Media urn resolution with registry | tests/test_schema_validation.py:453 |
| test6326 | `test_6326_max_chunk_plus_one_splits_into_two_chunks` | TEST6326: Test payload of max_chunk + 1 bytes produces exactly two chunks | tests/test_cbor_io.py:931 |
| test6330 | `test_6330_chunking_data_integrity_3x` | TEST6330: Test auto-chunking preserves data integrity across chunk boundaries for 3x max_chunk payload | tests/test_cbor_io.py:967 |
| test6333 | `test_6333_registry_add_caps_to_cache` | TEST6333: Test adding caps to the registry cache and retrieving them | tests/test_registry.py:365 |
| test6336 | `test_6336_registry_config_builder_pattern` | TEST6336: Test registry configuration builder sets registry and schema URLs | tests/test_registry.py:379 |
| test6340 | `test_6340_normalize_urn_with_trailing_semicolon` | TEST6340: normalize_cap_urn strips trailing semicolons, producing the same canonical form with or without a trailing semicolon | tests/test_registry.py:390 |
| test6344 | `test_6344_nested_object_schema_validation` | TEST6344: Schema validation with nested object schemas | tests/test_schema_validation.py:174 |
| test6348 | `test_6348_array_schema_validation` | TEST6348: Schema validation with array schemas including minItems and item constraints | tests/test_schema_validation.py:226 |
| test6352 | `test_6352_type_constraint_validation` | TEST6352: Schema validation with type constraints (integer, number, boolean) | tests/test_schema_validation.py:269 |
| test6356 | `test_6356_validate_multiple_arguments` | TEST6356: Schema validation with multiple arguments validates each independently | tests/test_schema_validation.py:303 |
| test6360 | `test_6360_output_validation_with_details` | TEST6360: Output validation surfaces schema violation details | tests/test_schema_validation.py:356 |
| test6363 | `test_6363_cap_manifest_with_page_url` | TEST6363: Cap manifest with page_url — the optional page_url is carried and serialized as `page_url`. | tests/test_manifest.py:330 |
| test6364 | `test_6364_input_validation_optional_arg` | TEST6364: Input validation succeeds when optional positional argument is omitted | tests/test_validation.py:87 |
| test6368 | `test_6368_input_validation_too_many_args` | TEST6368: Input validation fails with TooManyArgumentsError when extra positional args supplied | tests/test_validation.py:100 |
| test6371 | `test_6371_cap_manifest_compatibility` | TEST6371: Cap manifest compatibility — two independently-constructed cartridge manifests serialize to the same JSON shape (same keys). | tests/test_manifest.py:351 |
| test6382 | `test_6382_parse_registry_json` | TEST6382: Test parsing registry JSON without stdin args verifies cap structure | tests/test_registry.py:54 |
| test6388 | `test_6388_per_cap_url_uses_sha256` | TEST6388: Per-cap URLs use SHA-256 of the canonical URN as the path key. The path scheme is /caps/<sha256-hex> — no colons, no quotes, no percent-encoding gymnastics. Same hash function across every capdag implementation guarantees a single bucket key per equivalence class. | tests/test_registry.py:125 |
| test6391 | `test_6391_same_cap_different_spellings_same_url` | TEST6391: Equivalent URNs (different tag order, etc.) hash to the same key. | tests/test_registry.py:181 |
| test6396 | `test_6396_malformed_cap_urn_fails_hard` | TEST6396: A malformed cap URN must FAIL HARD with a ParseError, not be passed through raw (the old fallback) and surface later as a misleading NotFound. The `out` value below contains an unquoted `=`, which the cap grammar rejects. Against the old `except Exception: return urn` fallback, normalize_cap_urn returned the raw string and _cap_defver then reported "not part of manifest" (a NotFoundError); this test asserts the truthful error type on both the direct and the public (get_cap) paths. | tests/test_registry.py:408 |
| test6544 | `test_6544_builder_rejects_structural_keys` | TEST6544: Builder rejects reserved structural keys on tag/marker helpers | tests/test_cap_urn.py:403 |
| test6586 | `test_6586_file_path_array_invalid_json_fails` | TEST6586: A scalar file-path arg receiving a nonexistent path fails hard with a clear error that names the path. The runtime refuses to silently swallow user mistakes like typos or wrong directories. | tests/test_cartridge_runtime.py:851 |
| test6587 | `test_6587_file_path_array_one_file_missing_fails_hard` | TEST6587: file-path-array with literal nonexistent path fails hard | tests/test_cartridge_runtime.py:881 |
| test6588 | `test_6588_file_path_array_empty_array` | TEST6588: file-path arg in CBOR mode with empty Array returns empty. CBOR Array (not JSON-encoded) is the multi-input wire form for sequence args. Mirrors Rust test351_file_path_array_empty_array. | tests/test_cartridge_runtime.py:1105 |
| test6594 | `test_6594_capabilities_empty_initially` | TEST6594: capabilities() with registered cartridge advertises after a rebuild. Mirrors Rust: registration populates cap_groups, then a call to `_rebuild_capabilities` materialises the inventory snapshot. The run loop normally drives rebuild as cartridges attach/die; for a unit test that drives registration directly we trigger it explicitly. | tests/test_cartridge_host.py:422 |
| test6600 | `test_6600_parse_cap_groups_rejects_manifest_without_identity` | TEST6600: parse_cap_groups_from_manifest rejects manifest without CAP_IDENTITY | tests/test_cartridge_host.py:167 |
| test6601 | `test_6601_attached_cartridge_identity_derived_from_manifest` | TEST6601: An attached cartridge (raw-stream, no on-disk anchor) gets a resolvable install identity derived from its HELLO manifest. Advertisement is identity-gated, so without this the attached cartridge would be silently excluded from every RelayNotify and the engine could never route to it — the deadlock that hung the rust-rust-rust interop echo test. Mirrors the reference test6601. | tests/test_cartridge_host.py:363 |
| test6605 | `test_6605_insert_schema_populates_cache` | TEST6605: insert_schema seeds the cache so subsequent validation hits a real compiled schema rather than the skip-on-unknown path. A registry that silently dropped inserts would let validation calls return None even for inputs that violate the schema. | tests/test_media_profile.py:65 |
| test6607 | `test_6607_registry_creation` | TEST6607: A freshly constructed registry is operational and reports an empty cache. Schemas must be inserted explicitly — none are bundled. | tests/test_media_profile.py:103 |
| test6614 | `test_6614_wildcard_accepts_specific` | TEST6614: Legal generic cap with top directions matches specific caps | tests/test_cap_urn.py:1022 |
| test6616 | `test_6616_wildcard_specificity_scoring` | TEST6616: Specificity - generic marker-only cap has y-axis specificity only | tests/test_cap_urn.py:1031 |
| test6617 | `test_6617_wildcard_preserve_other_tags` | TEST6617: legal top-to-top generic transform preserves other tags | tests/test_cap_urn.py:1040 |
| test6619 | `test_6619_wildcard_identity_forms_equivalent` | TEST6619: Explicit identity forms produce the same CapUrn | tests/test_cap_urn.py:1049 |
| test6623 | `test_6623_cartridge_death_keeps_known_caps_advertised` | TEST6623: Cartridge death keeps caps advertised for on-demand respawn. | tests/test_cartridge_host.py:1013 |
| test6672 | `test_6672_cbor_accepts_stream_end_without_chunk_count` | TEST6672: CBOR decode ACCEPTS STREAM_END without chunk_count — unbounded streams make no length promise (v3, L16) | tests/test_cbor_frame.py:1553 |
| test6689 | `test_6689_abstraction_error_subclass_hierarchy` | TEST6689: All resolution error subclasses are instances of MachineAbstractionError. | tests/test_machine.py:581 |
| test6691 | `test_6691_two_strand_machine_serializes_to_notation` | TEST6691: Machine with two strands serializes to a non-empty notation string. | tests/test_machine.py:633 |
| test6692 | `test_6692_assignment_bindings_sorted_by_slot_urn` | Mirror-specific coverage: Assignment bindings are sorted by cap_arg_media_urn for canonical form | tests/test_machine.py:658 |
| test6693 | `test_6693_resolve_inputs_confirmed_wraps_detect_file_confirmed` | TEST6693: Resolve inputs confirmed wraps detect file confirmed | tests/test_input_resolver.py:569 |
| test6698 | `test_6698_parse_machine_shared_node_name_yields_one_strand` | TEST6698: Two caps whose wirings share a node name are folded into a single strand with two edges. | tests/test_machine.py:423 |
| test6703 | `test_6703_match_sources_to_args_single_trivial` | TEST6703: Source-to-arg matching: single source picks the unique arg. | tests/test_machine.py:274 |
| test6709 | `test_6709_two_step_chain_shares_intermediate_node` | TEST6709: Resolving a strand with two chained caps shares the intermediate node. | tests/test_machine.py:166 |
| test6710 | `test_6710_resolve_strand_foreach_sets_is_loop_on_next_cap` | TEST6710: A cap step fed by a sequence-producing predecessor maps per item (is_loop=True), derived purely from cardinality — the retired `LOOP` keyword and bare ForEach steps carry no wiring effect any more. | tests/test_machine.py:517 |
| test6713 | `test_6713_binding_slot_identity_is_outer_media_urn` | TEST6713: EdgeAssignmentBinding.cap_arg_media_urn is the slot identity (outer media_urn), not the stdin inner URN. | tests/test_machine.py:448 |
| test6734 | `test_6734_reject_invalid_combinations` | TEST6734: Invalid qualifier combinations must be rejected. | tests/test_cap_urn.py:1757 |
| test6735 | `test_6735_axis_weighting_out_dominates` | TEST6735: out-axis difference dominates combined in+y differences. | tests/test_cap_urn.py:1778 |
| test6736 | `test_6736_axis_weighting_decoded_layout` | TEST6736: Decoded layout — 10000*out + 100*in + y. | tests/test_cap_urn.py:1802 |
| test6745 | `test_6745_relay_switch_init_rejects_duplicate_ids` | TEST6745: RelaySwitch::new rejects duplicate ids in its cardinality list. | tests/test_relay_switch.py:1032 |
| test6748 | `test_6748_routes_req_to_handler` | TEST6748: InProcessCartridgeHost routes REQ to matching handler and returns response | tests/test_in_process_host.py:96 |
| test6749 | `test_6749_identity_verification` | TEST6749: InProcessCartridgeHost handles identity verification (echo nonce) | tests/test_in_process_host.py:160 |
| test6750 | `test_6750_no_handler_returns_err` | TEST6750: InProcessCartridgeHost returns NO_HANDLER for unregistered cap | tests/test_in_process_host.py:206 |
| test6751 | `test_6751_manifest_includes_all_caps` | TEST6751: InProcessCartridgeHost manifest includes identity cap and handler caps | tests/test_in_process_host.py:236 |
| test7000 | `test_7000_v3_handshake_negotiates_all_four_limits` | TEST7000: v3 handshake succeeds and negotiates the element-wise minimum of all four limits including initial_credit | tests/test_cbor_io.py:440 |
| test7001 | `test_7001_handshake_rejects_version_2` | TEST7001: HELLO carrying protocol version 2 is rejected at handshake with a version-mismatch error | tests/test_cbor_io.py:460 |
| test7002 | `test_7002_initial_credit_negotiated_minimum` | TEST7002: initial_credit negotiation picks the element-wise minimum of the two proposals | tests/test_cbor_io.py:490 |
| test7003 | `test_7003_decode_frame_rejects_malformed_id_wrong_length` | TEST7003: decode_frame rejects a MessageId byte string that is not exactly 16 bytes, for every wrong length — it must never fall back to a fabricated MessageId(0), which would misroute the frame | tests/test_cbor_io.py:1182 |
| test7004 | `test_7004_decode_frame_rejects_malformed_id_wrong_type` | TEST7004: decode_frame rejects an id whose CBOR type is neither bytes nor an unsigned integer (text, float, bool, array, map) — a wrong-typed id is a hard decode error, not a fabricated zero id | tests/test_cbor_io.py:1197 |
| test7005 | `test_7005_decode_frame_strict_routing_id` | TEST7005: a present routing_id (key 13) must be a well-formed MessageId — a malformed one is a hard InvalidFrameError, never silently dropped (which would strip the relay hint and misroute) nor fabricated as MessageId(0). Valid routing_ids still round-trip; an absent routing_id decodes as None. | tests/test_cbor_io.py:1211 |
| test7010 | `test_7010_credit_frame_roundtrip` | TEST7010: CREDIT frame round-trips encode/decode with rid, stream_id, and credit count | tests/test_cbor_frame.py:1568 |
| test7011 | `test_7011_credit_is_non_flow` | TEST7011: CREDIT is a non-flow frame — no seq assigned, passes the reorder buffer untouched regardless of flow state | tests/test_cbor_frame.py:1601 |
| test7012 | `test_7012_stream_start_unbounded_roundtrip` | TEST7012: STREAM_START unbounded flag round-trips through CBOR; absent flag means bounded | tests/test_cbor_frame.py:1628 |
| test7013 | `test_7013_cbor_rejects_credit_without_count` | TEST7013: CBOR decode REJECTS a CREDIT frame missing its credit count | tests/test_cbor_frame.py:1645 |
| test7014 | `test_7014_end_terminal_meta_roundtrip` | TEST7014: END terminal meta (progress, message) round-trips; successful END without progress reads as 1.0; failed END without progress reads as None | tests/test_cbor_frame.py:1690 |
| test7015 | `test_7015_credit_gate_acquire_and_grant` | TEST7015: CreditGate acquire succeeds immediately within the initial window and waits when exhausted until a grant arrives. | tests/test_credit.py:20 |
| test7016 | `test_7016_credit_gate_close_releases_waiters` | TEST7016: CreditGate close releases blocked waiters with CreditClosed and fails all future acquires. | tests/test_credit.py:48 |
| test7017 | `test_7017_credit_router_routing` | TEST7017: CreditRouter routes grants by (rid, stream_id), falls back to a request's sole gate for stream-less grants, and reports unmatched grants. | tests/test_credit.py:79 |
| test7018 | `test_7018_credit_router_close_request` | TEST7018: CreditRouter close_request closes and removes every gate of the request, releasing their waiters. | tests/test_credit.py:107 |
| test7019 | `test_7019_drop_counters_record_and_snapshot` | TEST7019: Drop counters record per-reason exactly once per drop, and the snapshot omits zero-count reasons while totalling all of them. | tests/test_stats.py:12 |
| test7020 | `test_7020_writer_gate_drops_post_terminal_flow_frames` | TEST7020: A flow frame reaching the writer after the flow's END has been written is dropped with a counted post_terminal drop — END is the last flow frame on the wire. | tests/test_cartridge_runtime.py:2430 |
| test7021 | `test_7021_writer_gate_precision` | TEST7021: The writer gate is precise — flow frames before END are written, non-flow frames (heartbeat, credit) still pass after a flow's terminal, and only that flow is gated. | tests/test_cartridge_runtime.py:2461 |
| test7025 | `test_7025_unroutable_flow_frame_is_counted_drop` | TEST7025: A flow frame for a request with no routing state is a counted no_route drop — not a protocol error and not a silent loss — observable in the protocol stats snapshot. (The reference builds a switch with ZERO masters; this mirror's constructor requires at least one — see TEST432 — so this uses a single connected, healthy master instead. The drop-counting behavior under test is unaffected by that setup difference.) | tests/test_relay_switch.py:1619 |
| test7026 | `test_7026_reorder_flushes_pre_terminal_before_cleanup` | TEST7026: An out-of-order terminal is buffered until the gap fills; buffered pre-terminal frames flush ahead of it in seq order, and only then may the flow be cleaned up | tests/test_cbor_frame.py:1656 |
| test7027 | `test_7027_channel_closed_sends_are_counted` | TEST7027: A frame sent through a writer whose sink is gone is a counted channel_closed drop, never a silent loss. | tests/test_cartridge_runtime.py:2497 |
| test7029 | `test_7029_terminated_flows_capacity_and_eviction` | TEST7029: TerminatedFlows membership is exact up to capacity and evicts strictly oldest-first beyond it. | tests/test_stats.py:37 |
| test7030 | `test_7030_register_once_terminate_once` | TEST7030: A request registers exactly once and terminates exactly once — duplicate registration and double termination are rejected, and after terminate zero state remains for the key. | tests/test_request_state.py:159 |
| test7031 | `test_7031_rid_index_consistency` | TEST7031: The rid index and the entry table never disagree across register/terminate cycles, and a terminated rid is immediately reusable. | tests/test_request_state.py:187 |
| test7032 | `test_7032_record_frame_stats_and_phase` | TEST7032: record_frame accumulates per-stream frame/byte/chunk counters by direction, flips phase Created->Streaming on the first flow frame, and tracks unbounded/ended/credit stream markers. | tests/test_request_state.py:208 |
| test7033 | `test_7033_terminated_summaries_ring` | TEST7033: Terminated requests leave a bounded ring of summaries carrying kind, lifetime, and flow totals, and the ring evicts oldest-first at capacity. | tests/test_request_state.py:247 |
| test7035 | `test_7035_end_terminates_and_releases_all_state` | TEST7035: After END, the switch holds zero state for the request — entry, rid index, and response channel all released atomically, with the terminal delivered and a terminated summary recorded. | tests/test_relay_switch.py:1644 |
| test7036 | `test_7036_err_terminates_and_releases_all_state` | TEST7036: After ERR, the same total-cleanup invariant holds as after END, with kind err. | tests/test_relay_switch.py:1681 |
| test7037 | `test_7037_cancel_cascades_to_children_and_cleans_all_state` | TEST7037: Cancelling a request terminates it AND its recursively-linked peer children — Cancel frames reach the destination, waiting channels get ERR CANCELLED, and zero state remains for parent or child. | tests/test_relay_switch.py:1705 |
| test7038 | `test_7038_master_death_terminates_pending_requests` | TEST7038: Master death terminates every request routed to it with kind master_died, delivering synthetic MASTER_DIED ERRs to waiting channels and leaving zero state. | tests/test_relay_switch.py:1767 |
| test7050 | `test_7050_sender_stalls_at_window_and_resumes_on_grant` | TEST7050: A credited sender emits exactly its window of chunks then stalls until a CREDIT grant arrives — observed on the frame channel. | tests/test_cartridge_runtime.py:2546 |
| test7052 | `test_7052_input_grants_are_batched` | TEST7052: Input consumption emits batched CREDIT grants — roughly one grant per half-window consumed, not one per chunk. | tests/test_cartridge_runtime.py:2636 |
| test7053 | `test_7053_over_window_chunk_is_credit_violation` | TEST7053: A chunk received beyond the granted window is a fatal CREDIT_VIOLATION surfaced to the consumer (L12). | tests/test_cartridge_runtime.py:2725 |
| test7062 | `test_7062_log_flows_while_window_exhausted` | TEST7062: LOG/progress frames flow while the data window is exhausted — control frames are never credited. | tests/test_cartridge_runtime.py:2598 |
| test7063 | `test_7063_pending_grants_flush_before_blocking` | TEST7063: A receiver flushes pending sub-batch grants before blocking on an empty input — progress is guaranteed even when the sender's window is smaller than the receiver's grant batch threshold. | tests/test_cartridge_runtime.py:2681 |
| test7070 | `test_7070_unbounded_input_consumed_live` | TEST7070: An unbounded input stream is consumed live — the handler observes early items while the producer is still emitting, and the stream reports itself unbounded. | tests/test_cartridge_runtime.py:2820 |
| test7073 | `test_7073_collect_refuses_unbounded_streams` | TEST7073: Buffering collectors refuse unbounded streams with a hard error instead of buffering without bound. | tests/test_cartridge_runtime.py:2853 |
| test7085 | `test_7085_relay_notify_carries_host_protocol_stats` | TEST7085: The RelayNotify capabilities payload carries the host's protocol stats snapshot, surviving the wire round-trip. (Adapted: this mirror has no typed RelayNotifyCapabilitiesPayload — it builds/parses the manifest dict directly via `_parse_relay_notify_payload`.) | tests/test_relay_switch.py:1883 |
| test7086 | `test_7086_drop_snapshot_matches_induced_drops` | TEST7086: One runtime's drop counters aggregate every drop source — post-terminal writer drops and closed-channel sends — each counted exactly once, and the snapshot totals match the induced drops. | tests/test_cartridge_runtime.py:2520 |
| test7087 | `test_7087_snapshot_field_names_are_stable` | TEST7087: Protocol stats snapshots serialize with stable field names — the snapshot shape is the mirror contract. | tests/test_request_state.py:67 |
| test7088 | `test_7088_last_activity_monotonic` | TEST7088: last_activity is monotonic non-decreasing across a long-lived streaming request — idle time resets on every recorded frame and never runs backwards. | tests/test_request_state.py:128 |
| test7089 | `test_7089_hello_failed_stays_in_inventory_with_error` | TEST7089: A cartridge whose HELLO permanently failed stays IN the inventory advertisement carrying a handshake_failed attachment error and no cap groups — failure is named, never silently absent; a roster-retired cartridge disappears entirely. | tests/test_cartridge_host.py:1276 |
| test7090 | `test_7090_heartbeat_drops_total_reaches_inventory_stats` | TEST7090: The cartridge's cumulative protocol drop counter (`drops_total` heartbeat meta, L8) is ingested by the host and surfaces on the cartridge's inventory runtime stats as `protocol_drops_total` — absent until the first reading, then tracking the running total as-is. | tests/test_cartridge_host.py:1363 |
| test7091 | `test_7091_switch_retains_host_protocol_stats_from_relay_notify` | TEST7091: Host protocol stats carried by a master's RelayNotify are RETAINED by the switch (not parsed-and-discarded) and surface in `protocol_stats().hosts` keyed by master id; a master that has not yet advertised stats is absent from the map — never a zeroed placeholder. | tests/test_relay_switch.py:1918 |
| test7092 | `test_7092_cap_urn_attribution_survives_lifecycle` | TEST7092: A request registered with its originating REQ's cap URN carries that identity through the ACTIVE snapshot and into the terminated ring — observability surfaces can always NAME a request (background chatter vs run traffic), never just show a bare rid. A request registered without one (pre-attribution mirror, unknown origin) snapshots with cap_urn null — absent, never invented. | tests/test_request_state.py:46 |
| test7093 | `test_7093_dead_consumer_cancels_upstream` | TEST7093: A response frame for a LIVE request whose external consumer is gone (dropped/timed-out caller callback) is a counted channel_closed drop AND cancels the request upstream — the destination receives Cancel, the entry terminates as cancelled, and the cartridge stops producing for a dead channel instead of running to completion against it. | tests/test_relay_switch.py:1791 |
| test7094 | `test_7094_decode_frame_rejects_missing_id` | TEST7094: decode_frame rejects a CBOR map missing the required id field (key 2) — matches Rust test228_decode_missing_id | tests/test_cbor_io.py:1169 |
| test7097 | `test_7097_decode_frame_accepts_valid_id_variants` | TEST7097: A well-formed id (16-byte UUID or non-negative uint) still decodes correctly after the strict-decode change — the fix rejects only malformed input, not valid frames | tests/test_cbor_io.py:1266 |
| test7098 | `test_7098_decode_frame_rejects_negative_int_id` | TEST7098: decode_frame rejects a negative-integer id — the uint variant is unsigned on the wire (Go's `case uint64`); a negative id is a hard InvalidFrameError, never a wrapped/fabricated value, and must not leak a raw ValueError outside the CborError family | tests/test_cbor_io.py:1252 |
| test8101 | `test_8101_cap_to_dict_wire_shape` | TEST8101: (py-specific) Cap.to_dict emits the full wire shape including args and output. Behavior beyond the shared cross-mirror set, kept here as implementation-specific coverage. | tests/test_cap.py:125 |
| test8102 | `test_8102_cap_arg_stream_urn_falls_back_to_media_urn_without_stdin_source` | TEST8102: (py-specific) CapArg.stream_urn() falls back to the declared slot media URN when the arg declares no Stdin source at all — a producer-fed arg may be delivered by its declared URN without ever appearing on stdin. | tests/test_cap.py:498 |
| test8103 | `test_8103_cap_arg_stream_urn_uses_stdin_source_urn_when_present` | TEST8103: (py-specific) CapArg.stream_urn() returns the Stdin source's URN, not the declared slot media URN, when the two differ — e.g. a file-path slot whose piped content is actually a pdf-stream. | tests/test_cap.py:510 |
| test8104 | `test_8104_cap_arg_is_main_input_true_when_stdin_urn_equivalent_to_in_spec` | TEST8104: (py-specific) CapArg.is_main_input() is True when the arg's Stdin source URN is order-theoretically equivalent to the cap's in= spec — even when the two strings list their tags in a different order. Compared by tagged-URN equivalence, never as strings. | tests/test_cap.py:524 |
| test8105 | `test_8105_cap_arg_is_main_input_false_without_matching_stdin_source` | TEST8105: (py-specific) CapArg.is_main_input() is False when the arg has no Stdin source, and False when it has a Stdin source whose URN does not match in_spec. | tests/test_cap.py:540 |
| test8106 | `test_8106_cap_arg_is_main_input_false_on_unparseable_stdin_urn` | TEST8106: (py-specific) A malformed Stdin source URN must not raise out of is_main_input — mirrors the Rust reference's `unwrap_or(false)` fail-soft on MediaUrn parse failure. | tests/test_cap.py:561 |
| test8107 | `test_8107_realize_strand_single_edge_produces_one_cap_step` | TEST8107: (py-specific) realize_strand converts a single-edge MachineStrand into a one-cap-step Strand, inferring the runtime output media through the cap's effect and preserving the resolved edge's token_id. | tests/test_machine.py:1259 |
| test8108 | `test_8108_realize_strand_inserts_foreach_for_loop_edge` | TEST8108: (py-specific) realize_strand inserts a ForEach step before the cap edge the resolver marked is_loop, reading the resolver's cardinality decision rather than recomputing it. | tests/test_machine.py:1286 |
| test8109 | `test_8109_realize_strand_non_producer_secondary_arg_fails_hard` | TEST8109: (py-specific) realize_strand fails hard when a non-primary (convergence) argument is fed by a raw input anchor rather than another cap's output — a raw value feeding a non-main arg must be delivered as an argument value, never wired. | tests/test_machine.py:1315 |
| test8110 | `test_8110_realize_strand_disconnected_strand_fails_hard` | TEST8110: (py-specific) realize_strand fails hard when an edge's source never becomes available (a structurally disconnected strand) rather than silently skipping it. | tests/test_machine.py:1353 |
| | | | |
| unnumbered | `test_capacity_handle_get_set` | CapacityHandle (set_capacity/queue) — no dedicated numbered Rust unit test in this diff (capacity queueing is exercised at the E2E/interop level); covered here at the unit level. | tests/test_cartridge_runtime.py:2783 |
| unnumbered | `test_cartridge_runtime_set_capacity_and_handle_share_state` |  | tests/test_cartridge_runtime.py:2790 |
| unnumbered | `test_death_cleanup_helper_clears_v3_terminal_markers` |  | tests/test_cartridge_host_runtime.py:591 |
| unnumbered | `test_end_carries_handler_declared_final_progress` | END-carries-final-progress (L3/L5) — not individually numbered in the Rust diff (covered there at the E2E/interop level), exercised here at the unit level since `ThreadSafeEmitter.finalize()` is the mirror's direct equivalent of the Rust reference's spawn_handler END construction. | tests/test_cartridge_runtime.py:2758 |
| unnumbered | `test_end_defaults_to_progress_one_without_finish` |  | tests/test_cartridge_runtime.py:2768 |
| unnumbered | `test_protocol_drops_snapshot_starts_empty` |  | tests/test_cartridge_runtime.py:2798 |
| unnumbered | `test_protocol_stats_reflects_tables_drops_and_gc_totals` |  | tests/test_cartridge_host_runtime.py:609 |
| unnumbered | `test_route_continuation_frame_credit_direction_selects_side` |  | tests/test_cartridge_host_runtime.py:545 |
| unnumbered | `test_route_continuation_frame_credit_without_direction_is_counted_drop` |  | tests/test_cartridge_host_runtime.py:566 |
| unnumbered | `test_route_continuation_frame_data_then_terminal_stays_alive_for_response` |  | tests/test_cartridge_host_runtime.py:466 |
| unnumbered | `test_route_continuation_frame_no_route_is_counted_drop` |  | tests/test_cartridge_host_runtime.py:579 |
| unnumbered | `test_route_continuation_frame_response_first_race_releases_on_body_end` |  | tests/test_cartridge_host_runtime.py:494 |
| unnumbered | `test_route_continuation_frame_self_loop_peer_response_after_body_done` |  | tests/test_cartridge_host_runtime.py:516 |
| unnumbered | `test_set_static_inventory_records_stores_records` |  | tests/test_cartridge_host_runtime.py:631 |
---

## Unnumbered Tests

The following tests are cataloged but do not currently participate in numeric test indexing.

- `test_capacity_handle_get_set` — tests/test_cartridge_runtime.py:2783
- `test_cartridge_runtime_set_capacity_and_handle_share_state` — tests/test_cartridge_runtime.py:2790
- `test_death_cleanup_helper_clears_v3_terminal_markers` — tests/test_cartridge_host_runtime.py:591
- `test_end_carries_handler_declared_final_progress` — tests/test_cartridge_runtime.py:2758
- `test_end_defaults_to_progress_one_without_finish` — tests/test_cartridge_runtime.py:2768
- `test_protocol_drops_snapshot_starts_empty` — tests/test_cartridge_runtime.py:2798
- `test_protocol_stats_reflects_tables_drops_and_gc_totals` — tests/test_cartridge_host_runtime.py:609
- `test_route_continuation_frame_credit_direction_selects_side` — tests/test_cartridge_host_runtime.py:545
- `test_route_continuation_frame_credit_without_direction_is_counted_drop` — tests/test_cartridge_host_runtime.py:566
- `test_route_continuation_frame_data_then_terminal_stays_alive_for_response` — tests/test_cartridge_host_runtime.py:466
- `test_route_continuation_frame_no_route_is_counted_drop` — tests/test_cartridge_host_runtime.py:579
- `test_route_continuation_frame_response_first_race_releases_on_body_end` — tests/test_cartridge_host_runtime.py:494
- `test_route_continuation_frame_self_loop_peer_response_after_body_done` — tests/test_cartridge_host_runtime.py:516
- `test_set_static_inventory_records_stores_records` — tests/test_cartridge_host_runtime.py:631

---

## Numbering Mismatches

These tests have a numbering disagreement between the function name and the authoritative immediate TEST comment/docstring above the test. This is reported explicitly so comment sync does not silently overwrite a misnumbered test.

- `test001` / `test1` / `test_001_cap_urn_creation` — tests/test_cap_urn.py:31
- `test002` / `test2` / `test_002_direction_specs_default_to_wildcard` — tests/test_cap_urn.py:42
- `test003` / `test3` / `test_003_direction_matching` — tests/test_cap_urn.py:60
- `test004` / `test4` / `test_004_unquoted_values_lowercased` — tests/test_cap_urn.py:88
- `test005` / `test5` / `test_005_quoted_values_preserve_case` — tests/test_cap_urn.py:109
- `test006` / `test6` / `test_006_quoted_value_special_chars` — tests/test_cap_urn.py:127
- `test007` / `test7` / `test_007_quoted_value_escape_sequences` — tests/test_cap_urn.py:142
- `test008` / `test8` / `test_008_mixed_quoted_unquoted` — tests/test_cap_urn.py:157
- `test009` / `test9` / `test_009_unterminated_quote_error` — tests/test_cap_urn.py:164
- `test010` / `test10` / `test_010_invalid_escape_sequence_error` — tests/test_cap_urn.py:170
- `test011` / `test11` / `test_011_serialization_smart_quoting` — tests/test_cap_urn.py:180
- `test012` / `test12` / `test_012_round_trip_simple` — tests/test_cap_urn.py:199
- `test013` / `test13` / `test_013_round_trip_quoted` — tests/test_cap_urn.py:208
- `test014` / `test14` / `test_014_round_trip_escapes` — tests/test_cap_urn.py:218
- `test015` / `test15` / `test_015_cap_prefix_required` — tests/test_cap_urn.py:228
- `test016` / `test16` / `test_016_trailing_semicolon_equivalence` — tests/test_cap_urn.py:243
- `test017` / `test17` / `test_017_tag_matching` — tests/test_cap_urn.py:285
- `test018` / `test18` / `test_018_quoted_values_case_sensitive` — tests/test_cap_urn.py:310
- `test019` / `test19` / `test_019_missing_tag_handling` — tests/test_cap_urn.py:317
- `test021` / `test21` / `test_021_builder_creates_cap_urn` — tests/test_cap_urn.py:355
- `test022` / `test22` / `test_022_builder_requires_direction_specs` — tests/test_cap_urn.py:371
- `test023` / `test23` / `test_023_builder_preserves_case` — tests/test_cap_urn.py:386
- `test024` / `test24` / `test_024_directional_accepts` — tests/test_cap_urn.py:430
- `test025` / `test25` / `test_025_find_best_match` — tests/test_cap_urn.py:458
- `test026` / `test26` / `test_026_merge_and_subset` — tests/test_cap_urn.py:476
- `test027` / `test27` / `test_027_with_wildcard_tag` — tests/test_cap_urn.py:495
- `test029` / `test29` / `test_029_minimal_valid_cap_urn` — tests/test_cap_urn.py:518
- `test030` / `test30` / `test_030_extended_characters_in_values` — tests/test_cap_urn.py:526
- `test031` / `test31` / `test_031_wildcard_in_keys_and_values` — tests/test_cap_urn.py:533
- `test032` / `test32` / `test_032_duplicate_keys_rejected` — tests/test_cap_urn.py:545
- `test033` / `test33` / `test_033_numeric_keys` — tests/test_cap_urn.py:552
- `test034` / `test34` / `test_034_empty_values_rejected` — tests/test_cap_urn.py:567
- `test035` / `test35` / `test_035_has_tag_behavior` — tests/test_cap_urn.py:574
- `test036` / `test36` / `test_036_with_tag_preserves_case` — tests/test_cap_urn.py:593
- `test037` / `test37` / `test_037_with_tag_rejects_empty` — tests/test_cap_urn.py:600
- `test038` / `test38` / `test_038_semantic_equivalence_quoted_unquoted` — tests/test_cap_urn.py:607
- `test039` / `test39` / `test_039_get_tag_direction_specs` — tests/test_cap_urn.py:616
- `test040` / `test40` / `test_040_matching_semantics_exact_match` — tests/test_cap_urn.py:640
- `test041` / `test41` / `test_041_matching_semantics_cap_missing_tag` — tests/test_cap_urn.py:647
- `test042` / `test42` / `test_042_matching_semantics_cap_has_extra_tag` — tests/test_cap_urn.py:654
- `test043` / `test43` / `test_043_matching_semantics_request_has_wildcard` — tests/test_cap_urn.py:664
- `test044` / `test44` / `test_044_matching_semantics_cap_has_wildcard` — tests/test_cap_urn.py:671
- `test045` / `test45` / `test_045_matching_semantics_value_mismatch` — tests/test_cap_urn.py:678
- `test046` / `test46` / `test_046_matching_semantics_fallback_pattern` — tests/test_cap_urn.py:685
- `test047` / `test47` / `test_047_matching_semantics_thumbnail_void_input` — tests/test_cap_urn.py:693
- `test048` / `test48` / `test_048_matching_semantics_direction_mismatch` — tests/test_cap_urn.py:717
- `test049` / `test49` / `test_049_matching_semantics_cross_dimension` — tests/test_cap_urn.py:708
- `test050` / `test50` / `test_050_matching_semantics_test10_direction_mismatch` — tests/test_cap_urn.py:726
- `test051` / `test51` / `test_051_input_validation_success` — tests/test_validation.py:44
- `test052` / `test52` / `test_052_input_validation_missing_required` — tests/test_validation.py:69
- `test053` / `test53` / `test_053_input_validation_wrong_type` — tests/test_validation.py:118
- `test060` / `test60` / `test_060_wrong_prefix_fails` — tests/test_media_urn.py:39
- `test062` / `test62` / `test_062_is_record` — tests/test_media_urn.py:51
- `test063` / `test63` / `test_063_is_scalar` — tests/test_media_urn.py:65
- `test064` / `test64` / `test_064_is_list` — tests/test_media_urn.py:76
- `test065` / `test65` / `test_065_is_opaque` — tests/test_media_urn.py:89
- `test066` / `test66` / `test_066_is_json` — tests/test_media_urn.py:100
- `test067` / `test67` / `test_067_is_text` — tests/test_media_urn.py:110
- `test068` / `test68` / `test_068_is_void` — tests/test_media_urn.py:123
- `test071` / `test71` / `test_071_to_string_roundtrip` — tests/test_media_urn.py:133
- `test072` / `test72` / `test_072_all_constants_parse` — tests/test_media_urn.py:142
- `test073` / `test73` / `test_073_extension_helpers` — tests/test_media_urn.py:163
- `test074` / `test74` / `test_074_media_urn_matching` — tests/test_media_urn.py:188
- `test075` / `test75` / `test_075_matching` — tests/test_media_urn.py:207
- `test076` / `test76` / `test_076_specificity` — tests/test_media_urn.py:220
- `test077` / `test77` / `test_077_serde_roundtrip` — tests/test_media_urn.py:237
- `test078` / `test78` / `test_078_object_does_not_conform_to_string` — tests/test_media_urn.py:246
- `test088` / `test88` / `test_088_resolve_seeded_spec` — tests/test_media_def.py:44
- `test089` / `test89` / `test_089_resolve_seeded_record_spec` — tests/test_media_def.py:58
- `test0090` / `test90` / `test_0090_absent_scan_root_yields_empty_roster` — tests/test_cartridge_discovery.py:78
- `test0091` / `test91` / `test_0091_missing_cartridge_json_is_manifest_invalid` — tests/test_cartridge_discovery.py:84
- `test0092` / `test92` / `test_0092_channel_mismatch_is_bad_installation` — tests/test_cartridge_discovery.py:91
- `test093` / `test93` / `test_093_resolve_unresolvable_fails_hard` — tests/test_media_def.py:79
- `test0094` / `test94` / `test_0094_fabric_manifest_mismatch_is_flagged` — tests/test_cartridge_discovery.py:100
- `test095` / `test95` / `test_095_media_def_def_serialize` — tests/test_media_def.py:93
- `test096` / `test96` / `test_096_media_def_def_deserialize` — tests/test_media_def.py:117
- `test097` / `test97` / `test_097_validate_no_duplicate_urns_catches_duplicates` — tests/test_media_def.py:136
- `test098` / `test98` / `test_098_validate_no_duplicate_urns_passes_for_unique` — tests/test_media_def.py:155
- `test099` / `test99` / `test_099_resolved_is_binary` — tests/test_media_def.py:178
- `test0120` / `test120` / `test_0120_registry_url_under_dev_slug_is_rejected` — tests/test_cartridge_discovery.py:108
- `test0125` / `test125` / `test_0125_effect_none_preserves_runtime_media` — tests/test_cap_urn.py:1092
- `test0126` / `test126` / `test_0126_effect_declared_uses_declared_output` — tests/test_cap_urn.py:1101
- `test0128` / `test128` / `test_0128_effect_dispatch_requires_explicit_wildcard` — tests/test_cap_urn.py:1108
- `test0136` / `test136` / `test_0136_all_masters_ready_false_when_expected_count_unset` — tests/test_relay_switch.py:1049
- `test0137` / `test137` / `test_0137_all_masters_ready_false_when_partially_connected` — tests/test_relay_switch.py:1091
- `test0139` / `test139` / `test_0139_all_masters_ready_true_when_masters_connected_but_capless` — tests/test_relay_switch.py:1107
- `test0140` / `test140` / `test_0140_all_masters_ready_does_not_overshoot` — tests/test_relay_switch.py:1125
- `test144` / `test1899` / `test_144_custom_registry_url` — tests/test_registry.py:252
- `test1899` / `test0144` / `test_1899_media_def_resolves_to_versioned_object_path_under_manifest` — tests/test_registry.py:326

---

*Generated from CapDag-Py source tree*
*Total tests: 1192*
*Total numbered tests: 1178*
*Total unnumbered tests: 14*
*Total numbered tests missing descriptions: 0*
*Total numbering mismatches: 89*
