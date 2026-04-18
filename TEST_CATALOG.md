# CapDag-Py Test Catalog

**Total Tests:** 636

**Numbered Tests:** 606

**Unnumbered Tests:** 30

All numbered test numbers are unique.

This catalog lists all tests in the CapDag-Py codebase.

| Test # | Function Name | Description | File |
|--------|---------------|-------------|------|
| test001 | `test_001_cap_urn_creation` | TEST001: Test that cap URN is created with tags parsed correctly and direction specs accessible | tests/test_cap_urn.py:29 |
| test002 | `test_002_direction_specs_default_to_wildcard` | TEST002: Test that missing 'in' or 'out' defaults to media: wildcard | tests/test_cap_urn.py:40 |
| test003 | `test_003_direction_matching` | TEST003: Test that direction specs must match exactly, different in/out types don't match, wildcard matches any | tests/test_cap_urn.py:58 |
| test004 | `test_004_unquoted_values_lowercased` | TEST004: Test that unquoted keys and values are normalized to lowercase | tests/test_cap_urn.py:86 |
| test005 | `test_005_quoted_values_preserve_case` | TEST005: Test that quoted values preserve case while unquoted are lowercased | tests/test_cap_urn.py:106 |
| test006 | `test_006_quoted_value_special_chars` | TEST006: Test that quoted values can contain special characters (semicolons, equals, spaces) | tests/test_cap_urn.py:124 |
| test007 | `test_007_quoted_value_escape_sequences` | TEST007: Test that escape sequences in quoted values (\" and \\) are parsed correctly | tests/test_cap_urn.py:139 |
| test008 | `test_008_mixed_quoted_unquoted` | TEST008: Test that mixed quoted and unquoted values in same URN parse correctly | tests/test_cap_urn.py:154 |
| test009 | `test_009_unterminated_quote_error` | TEST009: Test that unterminated quote produces UnterminatedQuote error | tests/test_cap_urn.py:161 |
| test010 | `test_010_invalid_escape_sequence_error` | TEST010: Test that invalid escape sequences (like \n, \x) produce InvalidEscapeSequence error | tests/test_cap_urn.py:167 |
| test011 | `test_011_serialization_smart_quoting` | TEST011: Test that serialization uses smart quoting (no quotes for simple lowercase, quotes for special chars/uppercase) | tests/test_cap_urn.py:177 |
| test012 | `test_012_round_trip_simple` | TEST012: Test that simple cap URN round-trips (parse -> serialize -> parse equals original) | tests/test_cap_urn.py:196 |
| test013 | `test_013_round_trip_quoted` | TEST013: Test that quoted values round-trip preserving case and spaces | tests/test_cap_urn.py:205 |
| test014 | `test_014_round_trip_escapes` | TEST014: Test that escape sequences round-trip correctly | tests/test_cap_urn.py:215 |
| test015 | `test_015_cap_prefix_required` | TEST015: Test that cap: prefix is required and case-insensitive | tests/test_cap_urn.py:225 |
| test016 | `test_016_trailing_semicolon_equivalence` | TEST016: Test that trailing semicolon is equivalent (same hash, same string, matches) | tests/test_cap_urn.py:240 |
| test017 | `test_017_tag_matching` | TEST017: Test tag matching: exact match, subset match, wildcard match, value mismatch | tests/test_cap_urn.py:260 |
| test018 | `test_018_quoted_values_case_sensitive` | TEST018: Test that quoted values with different case do NOT match (case-sensitive) | tests/test_cap_urn.py:282 |
| test019 | `test_019_missing_tag_handling` | TEST019: Missing tag in instance causes rejection — pattern's tags are constraints | tests/test_cap_urn.py:289 |
| test020 | `test_020_specificity_calculation` | TEST020: Test specificity calculation (direction specs use MediaUrn tag count, wildcards don't count) | tests/test_cap_urn.py:307 |
| test021 | `test_021_builder_creates_cap_urn` | TEST021: Test builder creates cap URN with correct tags and direction specs | tests/test_cap_urn.py:321 |
| test022 | `test_022_builder_requires_direction_specs` | TEST022: Test builder requires both in_spec and out_spec | tests/test_cap_urn.py:337 |
| test023 | `test_023_builder_preserves_case` | TEST023: Test builder lowercases keys but preserves value case | tests/test_cap_urn.py:352 |
| test024 | `test_024_directional_accepts` | TEST024: Directional accepts — pattern's tags are constraints, instance must satisfy | tests/test_cap_urn.py:368 |
| test025 | `test_025_find_best_match` | TEST025: Test find_best_match returns most specific matching cap | tests/test_cap_urn.py:396 |
| test026 | `test_026_merge_and_subset` | TEST026: Test merge combines tags from both caps, subset keeps only specified tags | tests/test_cap_urn.py:413 |
| test027 | `test_027_with_wildcard_tag` | TEST027: Test with_wildcard_tag sets tag to wildcard, including in/out | tests/test_cap_urn.py:430 |
| test028 | `test_028_empty_cap_urn_defaults` | TEST028: Test empty cap URN defaults to media: wildcard | tests/test_cap_urn.py:447 |
| test029 | `test_029_minimal_valid_cap_urn` | TEST029: Test minimal valid cap URN has just in and out, empty tags | tests/test_cap_urn.py:455 |
| test030 | `test_030_extended_characters_in_values` | TEST030: Test extended characters (forward slashes, colons) in tag values | tests/test_cap_urn.py:463 |
| test031 | `test_031_wildcard_in_keys_and_values` | TEST031: Test wildcard rejected in keys but accepted in values | tests/test_cap_urn.py:470 |
| test032 | `test_032_duplicate_keys_rejected` | TEST032: Test duplicate keys are rejected with DuplicateKey error | tests/test_cap_urn.py:481 |
| test033 | `test_033_numeric_keys` | TEST033: Test pure numeric keys rejected, mixed alphanumeric allowed, numeric values allowed | tests/test_cap_urn.py:487 |
| test034 | `test_034_empty_values_rejected` | TEST034: Test empty values are rejected | tests/test_cap_urn.py:502 |
| test035 | `test_035_has_tag_behavior` | TEST035: Test has_tag is case-sensitive for values, case-insensitive for keys, works for in/out | tests/test_cap_urn.py:509 |
| test036 | `test_036_with_tag_preserves_case` | TEST036: Test with_tag preserves value case | tests/test_cap_urn.py:528 |
| test037 | `test_037_with_tag_rejects_empty` | TEST037: Test with_tag rejects empty value | tests/test_cap_urn.py:535 |
| test038 | `test_038_semantic_equivalence_quoted_unquoted` | TEST038: Test semantic equivalence of unquoted and quoted simple lowercase values | tests/test_cap_urn.py:542 |
| test039 | `test_039_get_tag_direction_specs` | TEST039: Test get_tag returns direction specs (in/out) with case-insensitive lookup | tests/test_cap_urn.py:551 |
| test040 | `test_040_matching_semantics_exact_match` | TEST040: Matching semantics - exact match succeeds | tests/test_cap_urn.py:575 |
| test041 | `test_041_matching_semantics_cap_missing_tag` | TEST041: Matching semantics - cap missing tag matches (implicit wildcard) | tests/test_cap_urn.py:582 |
| test042 | `test_042_matching_semantics_cap_has_extra_tag` | TEST042: Pattern rejects instance missing required tags | tests/test_cap_urn.py:589 |
| test043 | `test_043_matching_semantics_request_has_wildcard` | TEST043: Matching semantics - request wildcard matches specific cap value | tests/test_cap_urn.py:599 |
| test044 | `test_044_matching_semantics_cap_has_wildcard` | TEST044: Matching semantics - cap wildcard matches specific request value | tests/test_cap_urn.py:606 |
| test045 | `test_045_matching_semantics_value_mismatch` | TEST045: Matching semantics - value mismatch does not match | tests/test_cap_urn.py:613 |
| test046 | `test_046_matching_semantics_fallback_pattern` | TEST046: Matching semantics - fallback pattern (cap missing tag = implicit wildcard) | tests/test_cap_urn.py:620 |
| test047 | `test_047_matching_semantics_thumbnail_void_input` | TEST047: Matching semantics - thumbnail fallback with void input | tests/test_cap_urn.py:628 |
| test048 | `test_048_matching_semantics_wildcard_direction` | TEST048: Matching semantics - wildcard direction matches anything | tests/test_cap_urn.py:636 |
| test049 | `test_049_matching_semantics_cross_dimension` | TEST049: Non-overlapping tags — neither direction accepts | tests/test_cap_urn.py:643 |
| test050 | `test_050_matching_semantics_direction_mismatch` | TEST050: Matching semantics - direction mismatch prevents matching | tests/test_cap_urn.py:652 |
| test051 | `test_051_input_validation_success` | TEST051: Test input validation succeeds with valid positional argument | tests/test_validation.py:26 |
| test052 | `test_052_input_validation_missing_required` | TEST052: Test input validation fails with MissingRequiredArgument when required arg missing | tests/test_validation.py:40 |
| test060 | `test_060_wrong_prefix_fails` | TEST060: Test wrong prefix fails with InvalidPrefix error showing expected and actual prefix | tests/test_media_urn.py:40 |
| test061 | `test_061_is_binary` | TEST061: Test is_binary returns true when textable tag is absent (binary = not textable) | tests/test_media_urn.py:46 |
| test062 | `test_062_is_record` | TEST062: Test is_record returns true when record marker tag is present indicating key-value structure | tests/test_media_urn.py:59 |
| test063 | `test_063_is_scalar` | TEST063: Test is_scalar returns true when list marker tag is absent (scalar is default) | tests/test_media_urn.py:73 |
| test064 | `test_064_is_list` | TEST064: Test is_list returns true when list marker tag is present indicating ordered collection | tests/test_media_urn.py:84 |
| test065 | `test_065_is_opaque` | TEST065: Test is_opaque returns true when record marker is absent (opaque is default) | tests/test_media_urn.py:97 |
| test066 | `test_066_is_json` | TEST066: Test is_json returns true only when json marker tag is present for JSON representation | tests/test_media_urn.py:108 |
| test067 | `test_067_is_text` | TEST067: Test is_text returns true only when textable marker tag is present | tests/test_media_urn.py:118 |
| test068 | `test_068_is_void` | TEST068: Test is_void returns true when void flag or type=void tag is present | tests/test_media_urn.py:131 |
| test071 | `test_071_to_string_roundtrip` | TEST071: Test to_string roundtrip ensures serialization and deserialization preserve URN structure | tests/test_media_urn.py:141 |
| test072 | `test_072_all_constants_parse` | TEST072: Test all media URN constants parse successfully as valid media URNs | tests/test_media_urn.py:150 |
| test073 | `test_073_extension_helpers` | TEST073: Test extension helper functions create media URNs with ext tag and correct format | tests/test_media_urn.py:171 |
| test074 | `test_074_media_urn_matching` | TEST074: Test media URN conforms_to using tagged URN semantics with specific and generic requirements | tests/test_media_urn.py:195 |
| test075 | `test_075_matching` | TEST075: Test accepts with implicit wildcards where handlers with fewer tags can handle more requests | tests/test_media_urn.py:210 |
| test076 | `test_076_specificity` | TEST076: Test specificity increases with more tags for ranking conformance | tests/test_media_urn.py:223 |
| test077 | `test_077_serde_roundtrip` | TEST077: Test serde roundtrip serializes to JSON string and deserializes back correctly | tests/test_media_urn.py:237 |
| test078 | `test_078_object_does_not_conform_to_string` | TEST078: conforms_to behavior between MEDIA_OBJECT and MEDIA_STRING | tests/test_media_urn.py:246 |
| test088 | `test_088_resolve_from_registry_str` | TEST088: Test resolving string media URN from registry returns correct media type and profile | tests/test_media_spec.py:51 |
| test089 | `test_089_resolve_from_registry_obj` | TEST089: Test resolving JSON media URN from registry returns JSON media type | tests/test_media_spec.py:61 |
| test090 | `test_090_resolve_from_registry_binary` | TEST090: Test resolving binary media URN returns octet-stream and is_binary true | tests/test_media_spec.py:69 |
| test091 | `test_091_resolve_custom_media_spec` | TEST091: Test resolving custom media URN from local media_specs takes precedence over registry | tests/test_media_spec.py:91 |
| test092 | `test_092_resolve_custom_with_schema` | TEST092: Test resolving custom record media spec with schema from local media_specs | tests/test_media_spec.py:117 |
| test093 | `test_093_resolve_unresolvable_fails_hard` | TEST093: Test resolving unknown media URN fails with UnresolvableMediaUrn error | tests/test_media_spec.py:148 |
| test094 | `test_094_local_overrides_registry` | TEST094: Test local media_specs definition overrides registry definition for same URN | tests/test_media_spec.py:158 |
| test095 | `test_095_media_spec_def_serialize` | TEST095: Test MediaSpecDef serializes with required fields and skips None fields | tests/test_media_spec.py:187 |
| test096 | `test_096_media_spec_def_deserialize` | TEST096: Test deserializing MediaSpecDef from JSON object | tests/test_media_spec.py:211 |
| test097 | `test_097_validate_no_duplicate_urns_catches_duplicates` | TEST097: Test duplicate URN validation catches duplicates | tests/test_media_spec.py:230 |
| test098 | `test_098_validate_no_duplicate_urns_passes_for_unique` | TEST098: Test duplicate URN validation passes for unique URNs | tests/test_media_spec.py:249 |
| test099 | `test_099_resolved_is_binary` | TEST099: Test ResolvedMediaSpec is_binary returns true when textable tag is absent | tests/test_media_spec.py:272 |
| test100 | `test_100_resolved_is_record` | TEST100: Test ResolvedMediaSpec is_record returns true when record marker is present | tests/test_media_spec.py:290 |
| test101 | `test_101_resolved_is_scalar` | TEST101: Test ResolvedMediaSpec is_scalar returns true when list marker is absent | tests/test_media_spec.py:309 |
| test102 | `test_102_resolved_is_list` | TEST102: Test ResolvedMediaSpec is_list returns true when list marker is present | tests/test_media_spec.py:327 |
| test103 | `test_103_resolved_is_json` | TEST103: Test ResolvedMediaSpec is_json returns true when json tag is present | tests/test_media_spec.py:345 |
| test104 | `test_104_resolved_is_text` | TEST104: Test ResolvedMediaSpec is_text returns true when textable tag is present | tests/test_media_spec.py:363 |
| test105 | `test_105_metadata_propagation` | TEST105: Test metadata propagates from media spec def to resolved media spec | tests/test_media_spec.py:387 |
| test106 | `test_106_metadata_with_validation` | TEST106: Test metadata and validation can coexist in media spec definition | tests/test_media_spec.py:414 |
| test107 | `test_107_extensions_propagation` | TEST107: Test extensions field propagates from media spec def to resolved | tests/test_media_spec.py:459 |
| test108 | `test_108_cap_creation` | TEST108: Test creating new cap with URN, title, and command verifies correct initialization | tests/test_cap.py:19 |
| test109 | `test_109_cap_with_args` | TEST109: Test creating cap with metadata initializes and retrieves metadata correctly | tests/test_cap.py:30 |
| test110 | `test_110_cap_with_stdin` | TEST110: Test cap matching with subset semantics for request fulfillment | tests/test_cap.py:49 |
| test111 | `test_111_cap_without_stdin` | TEST111: Test getting and setting cap title updates correctly | tests/test_cap.py:65 |
| test112 | `test_112_cap_with_output` | TEST112: Test cap equality based on URN and title matching | tests/test_cap.py:81 |
| test113 | `test_113_cap_with_metadata` | TEST113: Test cap stdin support via args with stdin source and serialization roundtrip | tests/test_cap.py:97 |
| test114 | `test_114_cap_json_serialization` | TEST114: Test ArgSource type variants stdin, position, and cli_flag with their accessors | tests/test_cap.py:110 |
| test115 | `test_115_cap_json_roundtrip` | TEST115: Test CapArg serialization and deserialization with multiple sources | tests/test_cap.py:143 |
| test116 | `test_116_cap_arg_multiple_sources` | TEST116: Test CapArg constructor methods basic and with_description create args correctly | tests/test_cap.py:168 |
| test117 | `test_117_register_and_find_cap_set` | TEST117: Test registering cap set and finding by exact and subset matching | tests/test_cap_matrix.py:39 |
| test118 | `test_118_best_cap_set_selection` | TEST118: Test selecting best cap set based on specificity ranking  With is_dispatchable semantics: - Provider must satisfy ALL request constraints - General request matches specific provider (provider refines request) - Specific request does NOT match general provider (provider lacks constraints) | tests/test_cap_matrix.py:62 |
| test119 | `test_119_invalid_urn_handling` | TEST119: Test invalid URN returns InvalidUrn error | tests/test_cap_matrix.py:89 |
| test120 | `test_120_accepts_request` | TEST120: Test accepts_request checks if registry can handle a capability request | tests/test_cap_matrix.py:97 |
| test121 | `test_121_cap_block_more_specific_wins` | TEST121: Test CapBlock selects more specific cap over less specific regardless of registry order | tests/test_cap_matrix.py:380 |
| test122 | `test_122_cap_block_tie_goes_to_first` | TEST122: Test CapBlock breaks specificity ties by first registered registry | tests/test_cap_matrix.py:421 |
| test123 | `test_123_cap_block_polls_all` | TEST123: Test CapBlock polls all registries to find most specific match | tests/test_cap_matrix.py:448 |
| test124 | `test_124_cap_block_no_match` | TEST124: Test CapBlock returns error when no registries match the request | tests/test_cap_matrix.py:482 |
| test125 | `test_125_cap_block_fallback_scenario` | TEST125: Test CapBlock prefers specific cartridge over generic provider fallback | tests/test_cap_matrix.py:496 |
| test126 | `test_126_cap_block_accepts_request` | TEST126: Test composite can method returns CapCaller for capability execution | tests/test_cap_matrix.py:536 |
| test127 | `test_127_cap_graph_adds_nodes_and_edges` | TEST127: Test CapGraph adds nodes and edges from capability definitions | tests/test_cap_matrix.py:120 |
| test128 | `test_128_cap_graph_tracks_outgoing_and_incoming` | TEST128: Test CapGraph tracks outgoing and incoming edges for spec conversions | tests/test_cap_matrix.py:145 |
| test129 | `test_129_cap_graph_detects_conversion_paths` | TEST129: Test CapGraph detects direct and indirect conversion paths between specs | tests/test_cap_matrix.py:166 |
| test130 | `test_130_cap_graph_finds_shortest_path` | TEST130: Test CapGraph finds shortest path for spec conversion chain | tests/test_cap_matrix.py:193 |
| test131 | `test_131_cap_graph_finds_all_paths` | TEST131: Test CapGraph finds all conversion paths sorted by length | tests/test_cap_matrix.py:215 |
| test132 | `test_132_cap_graph_direct_edges_sorted_by_specificity` | TEST132: Test CapGraph returns direct edges sorted by specificity | tests/test_cap_matrix.py:239 |
| test133 | `test_133_cap_block_graph_integration` | TEST133: Test CapBlock graph integration with multiple registries and conversion paths | tests/test_cap_matrix.py:557 |
| test134 | `test_134_cap_graph_stats` | TEST134: Test CapGraph stats provides counts of nodes and edges | tests/test_cap_matrix.py:261 |
| test135 | `test_135_registry_creation` | TEST135: Test registry creation with temporary cache directory succeeds | tests/test_registry.py:31 |
| test136 | `test_136_cache_key_generation` | TEST136: Test cache key generation produces consistent hashes for same URN | tests/test_registry.py:43 |
| test137 | `test_137_parse_registry_json` | TEST137: Test parsing registry JSON without stdin args verifies cap structure | tests/test_registry.py:68 |
| test138 | `test_138_parse_registry_json_with_stdin` | TEST138: Test parsing registry JSON with stdin args verifies stdin media URN extraction | tests/test_registry.py:113 |
| test139 | `test_139_url_keeps_cap_prefix_literal` | TEST139: Test URL construction keeps cap prefix literal and only encodes tags part | tests/test_registry.py:136 |
| test140 | `test_140_url_encodes_quoted_media_urns` | TEST140: Test URL encodes media URNs with proper percent encoding for special characters | tests/test_registry.py:153 |
| test141 | `test_141_exact_url_format` | TEST141: Test exact URL format contains properly encoded media URN components | tests/test_registry.py:173 |
| test142 | `test_142_normalize_handles_different_tag_orders` | TEST142: Test normalize handles different tag orders producing same canonical form | tests/test_registry.py:190 |
| test143 | `test_143_default_config` | TEST143: Test default config uses capdag.com or environment variable values | tests/test_registry.py:203 |
| test144 | `test_144_custom_registry_url` | TEST144: Test custom registry URL updates both registry and schema base URLs | tests/test_registry.py:213 |
| test145 | `test_145_custom_registry_and_schema_url` | TEST145: Test custom registry and schema URLs set independently | tests/test_registry.py:222 |
| test146 | `test_146_schema_url_not_overwritten_when_explicit` | TEST146: Test schema URL not overwritten when set explicitly before registry URL | tests/test_registry.py:233 |
| test147 | `test_147_registry_for_test_with_config` | TEST147: Test registry for test with custom config creates registry with specified URLs | tests/test_registry.py:245 |
| test148 | `test_148_cap_manifest_creation` | TEST148: Test creating cap manifest with name, version, description, and caps | tests/test_manifest.py:20 |
| test149 | `test_149_cap_manifest_with_author` | TEST149: Test cap manifest with author field sets author correctly | tests/test_manifest.py:39 |
| test150 | `test_150_cap_manifest_json_serialization` | TEST150: Test cap manifest JSON serialization and deserialization roundtrip | tests/test_manifest.py:54 |
| test151 | `test_151_cap_manifest_required_fields` | TEST151: Test cap manifest deserialization fails when required fields are missing | tests/test_manifest.py:91 |
| test152 | `test_152_cap_manifest_with_multiple_caps` | TEST152: Test cap manifest with multiple caps stores and retrieves all capabilities | tests/test_manifest.py:103 |
| test153 | `test_153_cap_manifest_with_page_url` | TEST153: Test cap manifest with empty caps list serializes and deserializes correctly | tests/test_manifest.py:128 |
| test154 | `test_154_cap_manifest_optional_fields` | TEST154: Test cap manifest optional author field skipped in serialization when None | tests/test_manifest.py:143 |
| test155 | `test_155_cap_manifest_complex_roundtrip` | TEST155: Test ComponentMetadata trait provides manifest and caps accessor methods | tests/test_manifest.py:167 |
| test156 | `test_156_stdin_source_data_creation` | TEST156: Test creating StdinSource Data variant with byte vector | tests/test_caller.py:30 |
| test157 | `test_157_stdin_source_file_reference_creation` | TEST157: Test creating StdinSource FileReference variant with all required fields | tests/test_caller.py:39 |
| test158 | `test_158_stdin_source_data_empty` | TEST158: Test StdinSource Data with empty vector stores and retrieves correctly | tests/test_caller.py:59 |
| test159 | `test_159_stdin_source_data_binary` | TEST159: Test StdinSource Data with binary content like PNG header bytes | tests/test_caller.py:66 |
| test160 | `test_160_stdin_source_data_clone` | TEST160: Test StdinSource Data clone creates independent copy with same data | tests/test_caller.py:77 |
| test161 | `test_161_stdin_source_file_reference_clone` | TEST161: Test StdinSource FileReference clone creates independent copy with same fields | tests/test_caller.py:95 |
| test162 | `test_162_stdin_source_debug_format` | TEST162: Test StdinSource Debug format displays variant type and relevant fields | tests/test_caller.py:115 |
| test163 | `test_163_argument_schema_validation_success` | TEST163: Test argument schema validation succeeds with valid JSON matching schema | tests/test_schema_validation.py:25 |
| test164 | `test_164_argument_schema_validation_failure` | TEST164: Test argument schema validation fails with JSON missing required fields | tests/test_schema_validation.py:56 |
| test165 | `test_165_output_schema_validation_success` | TEST165: Test output schema validation succeeds with valid JSON matching schema | tests/test_schema_validation.py:89 |
| test166 | `test_166_skip_validation_without_schema` | TEST166: Test validation skipped when resolved media spec has no schema | tests/test_schema_validation.py:120 |
| test167 | `test_167_unresolved_media_urn_skips_validation` | TEST167: Test validation fails hard when media URN cannot be resolved from any source | tests/test_schema_validation.py:136 |
| test168 | `test_168_json_response` | TEST168: Test ResponseWrapper from JSON deserializes to correct structured type | tests/test_response.py:20 |
| test169 | `test_169_primitive_types` | TEST169: Test ResponseWrapper converts to primitive types integer, float, boolean, string | tests/test_response.py:31 |
| test170 | `test_170_binary_response` | TEST170: Test ResponseWrapper from binary stores and retrieves raw bytes correctly | tests/test_response.py:50 |
| test171 | `test_171_frame_type_roundtrip` | TEST171: Test all FrameType discriminants roundtrip through u8 conversion preserving identity | tests/test_cbor_frame.py:27 |
| test172 | `test_172_invalid_frame_type` | TEST172: Test FrameType::from_u8 returns None for values outside the valid discriminant range | tests/test_cbor_frame.py:51 |
| test173 | `test_173_frame_type_discriminant_values` | TEST173: Test FrameType discriminant values match the wire protocol specification exactly | tests/test_cbor_frame.py:62 |
| test174 | `test_174_message_id_uuid` | TEST174: Test MessageId::new_uuid generates valid UUID that roundtrips through string conversion | tests/test_cbor_frame.py:80 |
| test175 | `test_175_message_id_uuid_uniqueness` | TEST175: Test two MessageId::new_uuid calls produce distinct IDs (no collisions) | tests/test_cbor_frame.py:91 |
| test176 | `test_176_message_id_uint_has_no_uuid_string` | TEST176: Test MessageId::Uint does not produce a UUID string, to_uuid_string returns None | tests/test_cbor_frame.py:99 |
| test177 | `test_177_message_id_from_invalid_uuid_str` | TEST177: Test MessageId::from_uuid_str rejects invalid UUID strings | tests/test_cbor_frame.py:106 |
| test178 | `test_178_message_id_as_bytes` | TEST178: Test MessageId::as_bytes produces correct byte representations for Uuid and Uint variants | tests/test_cbor_frame.py:114 |
| test179 | `test_179_message_id_default_is_uuid` | TEST179: Test MessageId::default creates a UUID variant (not Uint) | tests/test_cbor_frame.py:127 |
| test180 | `test_180_hello_frame` | TEST180: Test Frame::hello without manifest produces correct HELLO frame for host side | tests/test_cbor_frame.py:134 |
| test181 | `test_181_hello_frame_with_manifest` | TEST181: Test Frame::hello_with_manifest produces HELLO with manifest bytes for cartridge side | tests/test_cbor_frame.py:148 |
| test182 | `test_182_req_frame` | TEST182: Test Frame::req stores cap URN, payload, and content_type correctly | tests/test_cbor_frame.py:161 |
| test184 | `test_184_chunk_frame` | TEST184: Test Frame::chunk stores seq and payload for streaming (with stream_id) | tests/test_cbor_frame.py:177 |
| test185 | `test_185_err_frame` | TEST185: Test Frame::err stores error code and message in metadata | tests/test_cbor_frame.py:193 |
| test186 | `test_186_log_frame` | TEST186: Test Frame::log stores level and message in metadata | tests/test_cbor_frame.py:203 |
| test187 | `test_187_end_frame_with_payload` | TEST187: Test Frame::end with payload sets eof and optional final payload | tests/test_cbor_frame.py:214 |
| test188 | `test_188_end_frame_without_payload` | TEST188: Test Frame::end without payload still sets eof marker | tests/test_cbor_frame.py:224 |
| test189 | `test_189_chunk_with_offset` | TEST189: Test chunk_with_offset sets offset on all chunks but len only on seq=0 (with stream_id) | tests/test_cbor_frame.py:234 |
| test190 | `test_190_heartbeat_frame` | TEST190: Test Frame::heartbeat creates minimal frame with no payload or metadata | tests/test_cbor_frame.py:263 |
| test191 | `test_191_error_accessors_on_non_err_frame` | TEST191: Test error_code and error_message return None for non-Err frame types | tests/test_cbor_frame.py:275 |
| test192 | `test_192_log_accessors_on_non_log_frame` | TEST192: Test log_level and log_message return None for non-Log frame types | tests/test_cbor_frame.py:286 |
| test193 | `test_193_hello_accessors_on_non_hello_frame` | TEST193: Test hello_max_frame and hello_max_chunk return None for non-Hello frame types | tests/test_cbor_frame.py:294 |
| test194 | `test_194_frame_new_defaults` | TEST194: Test Frame::new sets version and defaults correctly, optional fields are None | tests/test_cbor_frame.py:303 |
| test195 | `test_195_frame_default` | TEST195: Test Frame::default creates a Req frame (the documented default) | tests/test_cbor_frame.py:321 |
| test196 | `test_196_is_eof_when_none` | TEST196: Test is_eof returns false when eof field is None (unset) | tests/test_cbor_frame.py:329 |
| test197 | `test_197_is_eof_when_false` | TEST197: Test is_eof returns false when eof field is explicitly Some(false) | tests/test_cbor_frame.py:336 |
| test198 | `test_198_limits_default` | TEST198: Test Limits::default provides the documented default values | tests/test_cbor_frame.py:344 |
| test199 | `test_199_protocol_version_constant` | TEST199: Test PROTOCOL_VERSION is 2 | tests/test_cbor_frame.py:354 |
| test200 | `test_200_key_constants` | TEST200: Test integer key constants match the protocol specification | tests/test_cbor_frame.py:360 |
| test201 | `test_201_hello_manifest_binary_data` | TEST201: Test hello_with_manifest preserves binary manifest data (not just JSON text) | tests/test_cbor_frame.py:376 |
| test202 | `test_202_message_id_equality_and_hash` | TEST202: Test MessageId Eq/Hash semantics: equal UUIDs are equal, different ones are not | tests/test_cbor_frame.py:384 |
| test203 | `test_203_message_id_cross_variant_inequality` | TEST203: Test Uuid and Uint variants of MessageId are never equal even for coincidental byte values | tests/test_cbor_frame.py:407 |
| test204 | `test_204_req_frame_empty_payload` | TEST204: Test Frame::req with empty payload stores Some(empty vec) not None | tests/test_cbor_frame.py:415 |
| test205 | `test_205_encode_frame_produces_cbor_with_integer_keys` | TEST205: Test REQ frame encode/decode roundtrip preserves all fields | tests/test_cbor_io.py:35 |
| test206 | `test_206_decode_frame_parses_cbor_correctly` | TEST206: Test HELLO frame encode/decode roundtrip preserves max_frame, max_chunk, max_reorder_buffer | tests/test_cbor_io.py:53 |
| test207 | `test_207_decode_frame_fails_on_invalid_cbor` | TEST207: Test ERR frame encode/decode roundtrip preserves error code and message | tests/test_cbor_io.py:65 |
| test208 | `test_208_decode_frame_fails_on_non_map` | TEST208: Test LOG frame encode/decode roundtrip preserves level and message | tests/test_cbor_io.py:71 |
| test210 | `test_210_read_frame_reads_length_prefixed` | TEST210: Test END frame encode/decode roundtrip preserves eof marker and optional payload | tests/test_cbor_io.py:96 |
| test211 | `test_211_read_frame_returns_none_on_eof` | TEST211: Test HELLO with manifest encode/decode roundtrip preserves manifest bytes and limits | tests/test_cbor_io.py:113 |
| test212 | `test_212_read_frame_fails_on_incomplete_length_prefix` | TEST212: Test chunk_with_offset encode/decode roundtrip preserves offset, len, eof (with stream_id) | tests/test_cbor_io.py:122 |
| test213 | `test_213_read_frame_fails_on_incomplete_frame_data` | TEST213: Test heartbeat frame encode/decode roundtrip preserves ID with no extra fields | tests/test_cbor_io.py:131 |
| test214 | `test_214_write_frame_enforces_max_frame_size` | TEST214: Test write_frame/read_frame IO roundtrip through length-prefixed wire format | tests/test_cbor_io.py:141 |
| test215 | `test_215_frame_reader_reads_multiple_frames` | TEST215: Test reading multiple sequential frames from a single buffer | tests/test_cbor_io.py:154 |
| test216 | `test_216_frame_writer_writes_multiple_frames` | TEST216: Test write_frame rejects frames exceeding max_frame limit | tests/test_cbor_io.py:178 |
| test217 | `test_217_frame_reader_new_creates_with_default_limits` | TEST217: Test read_frame rejects incoming frames exceeding the negotiated max_frame limit | tests/test_cbor_io.py:201 |
| test218 | `test_218_frame_writer_new_creates_with_default_limits` | TEST218: Test write_chunked splits data into chunks respecting max_chunk and reconstructs correctly Chunks from write_chunked have seq=0. SeqAssigner at the output stage assigns final seq. Chunk ordering within a stream is tracked by chunk_index (chunk_index field). | tests/test_cbor_io.py:210 |
| test219 | `test_219_frame_reader_with_limits` | TEST219: Test write_chunked with empty data produces a single EOF chunk | tests/test_cbor_io.py:219 |
| test220 | `test_220_frame_writer_with_limits` | TEST220: Test write_chunked with data exactly equal to max_chunk produces exactly one chunk | tests/test_cbor_io.py:229 |
| test221 | `test_221_frame_reader_set_limits` | TEST221: Test read_frame returns Ok(None) on clean EOF (empty stream) | tests/test_cbor_io.py:239 |
| test222 | `test_222_frame_writer_set_limits` | TEST222: Test read_frame handles truncated length prefix (fewer than 4 bytes available) | tests/test_cbor_io.py:251 |
| test223 | `test_223_handshake_host_sends_hello_first` | TEST223: Test read_frame returns error on truncated frame body (length prefix says more bytes than available) | tests/test_cbor_io.py:263 |
| test224 | `test_224_handshake_negotiates_to_minimum_limits` | TEST224: Test MessageId::Uint roundtrips through encode/decode | tests/test_cbor_io.py:299 |
| test225 | `test_225_handshake_function_full_handshake` | TEST225: Test decode_frame rejects non-map CBOR values (e.g., array, integer, string) | tests/test_cbor_io.py:335 |
| test226 | `test_226_handshake_accept_receives_first` | TEST226: Test decode_frame rejects CBOR map missing required version field | tests/test_cbor_io.py:365 |
| test227 | `test_227_handshake_fails_if_cartridge_missing_manifest` | TEST227: Test decode_frame rejects CBOR map with invalid frame_type value | tests/test_cbor_io.py:396 |
| test228 | `test_228_read_frame_enforces_limit` | TEST228: Test decode_frame rejects CBOR map missing required id field | tests/test_cbor_io.py:421 |
| test229 | `test_229_frame_with_zero_length_payload` | TEST229: Test FrameReader/FrameWriter set_limits updates the negotiated limits | tests/test_cbor_io.py:439 |
| test230 | `test_230_frame_roundtrip_preserves_fields` | TEST230: Test async handshake exchanges HELLO frames and negotiates minimum limits | tests/test_cbor_io.py:454 |
| test231 | `test_231_multiple_readers_on_same_stream` | TEST231: Test handshake fails when peer sends non-HELLO frame | tests/test_cbor_io.py:476 |
| test232 | `test_232_writer_flushes_after_each_frame` | TEST232: Test handshake fails when cartridge HELLO is missing required manifest | tests/test_cbor_io.py:501 |
| test233 | `test_233_frame_encoding_preserves_binary_data` | TEST233: Test binary payload with all 256 byte values roundtrips through encode/decode | tests/test_cbor_io.py:514 |
| test234 | `test_234_handshake_with_very_small_limits` | TEST234: Test decode_frame handles garbage CBOR bytes gracefully with an error | tests/test_cbor_io.py:527 |
| test235 | `test_235_response_chunk` | TEST235: Test ResponseChunk stores payload, seq, offset, len, and eof fields correctly | tests/test_cartridge_host_runtime.py:26 |
| test236 | `test_236_response_chunk_with_all_fields` | TEST236: Test ResponseChunk with all fields populated preserves offset, len, and eof | tests/test_cartridge_host_runtime.py:43 |
| test237 | `test_237_cartridge_response_single` | TEST237: Test CartridgeResponse::Single final_payload returns the single payload slice | tests/test_cartridge_host_runtime.py:60 |
| test238 | `test_238_cartridge_response_single_empty` | TEST238: Test CartridgeResponse::Single with empty payload returns empty slice and empty vec | tests/test_cartridge_host_runtime.py:67 |
| test239 | `test_239_cartridge_response_streaming` | TEST239: Test CartridgeResponse::Streaming concatenated joins all chunk payloads in order | tests/test_cartridge_host_runtime.py:74 |
| test240 | `test_240_cartridge_response_streaming_final_payload` | TEST240: Test CartridgeResponse::Streaming final_payload returns the last chunk's payload | tests/test_cartridge_host_runtime.py:109 |
| test241 | `test_241_cartridge_response_streaming_empty` | TEST241: Test CartridgeResponse::Streaming with empty chunks vec returns empty concatenation | tests/test_cartridge_host_runtime.py:141 |
| test242 | `test_242_cartridge_response_streaming_large` | TEST242: Test CartridgeResponse::Streaming concatenated capacity is pre-allocated correctly for large payloads | tests/test_cartridge_host_runtime.py:148 |
| test243 | `test_243_async_host_error_variants` | TEST243: Test AsyncHostError variants display correct error messages | tests/test_cartridge_host_runtime.py:184 |
| test244 | `test_244_async_host_error_from_cbor` | TEST244: Test AsyncHostError::from converts CborError to Cbor variant | tests/test_cartridge_host_runtime.py:214 |
| test245 | `test_245_async_host_error_from_io` | TEST245: Test AsyncHostError::from converts io::Error to Io variant | tests/test_cartridge_host_runtime.py:222 |
| test246 | `test_246_async_host_error_equality` | TEST246: Test AsyncHostError Clone implementation produces equal values | tests/test_cartridge_host_runtime.py:229 |
| test247 | `test_247_response_chunk_copy` | TEST247: Test ResponseChunk Clone produces independent copy with same data | tests/test_cartridge_host_runtime.py:240 |
| test248 | `test_248_register_and_find_handler` | TEST248: Test register_op and find_handler by exact cap URN | tests/test_cartridge_runtime.py:82 |
| test249 | `test_249_raw_handler` | TEST249: Test register_op handler echoes bytes directly | tests/test_cartridge_runtime.py:96 |
| test250 | `test_250_typed_handler_deserialization` | TEST250: Test Op handler collects input and processes it | tests/test_cartridge_runtime.py:127 |
| test251 | `test_251_typed_handler_rejects_invalid_json` | TEST251: Test Op handler propagates errors through RuntimeError::Handler | tests/test_cartridge_runtime.py:160 |
| test252 | `test_252_find_handler_unknown_cap` | TEST252: Test find_handler returns None for unregistered cap URNs | tests/test_cartridge_runtime.py:190 |
| test253 | `test_253_handler_is_send_sync` | TEST253: Test OpFactory can be cloned via Arc and sent across tasks (Send + Sync) | tests/test_cartridge_runtime.py:196 |
| test254 | `test_254_no_peer_invoker` | TEST254: Test NoPeerInvoker always returns PeerRequest error | tests/test_cartridge_runtime.py:227 |
| test255 | `test_255_no_peer_invoker_with_arguments` | TEST255: Test NoPeerInvoker call_with_bytes also returns error | tests/test_cartridge_runtime.py:237 |
| test256 | `test_256_with_manifest_json` | TEST256: Test CartridgeRuntime::with_manifest_json stores manifest data and parses when valid | tests/test_cartridge_runtime.py:246 |
| test257 | `test_257_new_with_invalid_json` | TEST257: Test CartridgeRuntime::new with invalid JSON still creates runtime (manifest is None) | tests/test_cartridge_runtime.py:257 |
| test258 | `test_258_with_manifest_struct` | TEST258: Test CartridgeRuntime::with_manifest creates runtime with valid manifest data | tests/test_cartridge_runtime.py:264 |
| test259 | `test_259_extract_effective_payload_non_cbor` | TEST259: Test extract_effective_payload with non-CBOR content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:273 |
| test260 | `test_260_extract_effective_payload_no_content_type` | TEST260: Test extract_effective_payload with None content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:283 |
| test261 | `test_261_extract_effective_payload_cbor_match` | TEST261: Test extract_effective_payload with CBOR content extracts matching argument value | tests/test_cartridge_runtime.py:292 |
| test262 | `test_262_extract_effective_payload_cbor_no_match` | TEST262: Test extract_effective_payload with CBOR content fails when no argument matches expected input | tests/test_cartridge_runtime.py:309 |
| test263 | `test_263_extract_effective_payload_invalid_cbor` | TEST263: Test extract_effective_payload with invalid CBOR bytes returns deserialization error | tests/test_cartridge_runtime.py:334 |
| test264 | `test_264_extract_effective_payload_cbor_not_array` | TEST264: Test extract_effective_payload with CBOR non-array (e.g. map) returns error | tests/test_cartridge_runtime.py:346 |
| test266 | `test_266_cli_stream_emitter_construction` | TEST266: Test CliFrameSender wraps CliStreamEmitter correctly (basic construction) | tests/test_cartridge_runtime.py:373 |
| test268 | `test_268_runtime_error_display` | TEST268: Test RuntimeError variants display correct messages | tests/test_cartridge_runtime.py:382 |
| test270 | `test_270_multiple_handlers` | TEST270: Test registering multiple Op handlers for different caps and finding each independently | tests/test_cartridge_runtime.py:403 |
| test271 | `test_271_handler_replacement` | TEST271: Test Op handler replacing an existing registration for the same cap URN | tests/test_cartridge_runtime.py:430 |
| test272 | `test_272_extract_effective_payload_multiple_args` | TEST272: Test extract_effective_payload CBOR with multiple arguments selects the correct one | tests/test_cartridge_runtime.py:461 |
| test273 | `test_273_extract_effective_payload_binary_value` | TEST273: Test extract_effective_payload with binary data in CBOR value (not just text) | tests/test_cartridge_runtime.py:484 |
| test274 | `test_274_cap_argument_value_new` | TEST274: Test CapArgumentValue::new stores media_urn and raw byte value | tests/test_caller.py:142 |
| test275 | `test_275_cap_argument_value_from_str` | TEST275: Test CapArgumentValue::from_str converts string to UTF-8 bytes | tests/test_caller.py:153 |
| test276 | `test_276_cap_argument_value_as_str_success` | TEST276: Test CapArgumentValue::value_as_str succeeds for UTF-8 data | tests/test_caller.py:165 |
| test277 | `test_277_cap_argument_value_as_str_fails_binary` | TEST277: Test CapArgumentValue::value_as_str fails for non-UTF-8 binary data | tests/test_caller.py:171 |
| test278 | `test_278_cap_argument_value_empty` | TEST278: Test CapArgumentValue::new with empty value stores empty vec | tests/test_caller.py:181 |
| test279 | `test_279_cap_argument_value_clone` | TEST279: Test CapArgumentValue Clone produces independent copy with same data | tests/test_caller.py:189 |
| test280 | `test_280_cap_argument_value_debug` | TEST280: Test CapArgumentValue Debug format includes media_urn and value | tests/test_caller.py:204 |
| test281 | `test_281_cap_argument_value_media_urn_types` | TEST281: Test CapArgumentValue::new accepts Into<String> for media_urn (String and &str) | tests/test_caller.py:222 |
| test282 | `test_282_cap_argument_value_unicode` | TEST282: Test CapArgumentValue::from_str with Unicode string preserves all characters | tests/test_caller.py:235 |
| test283 | `test_283_cap_argument_value_large_binary` | TEST283: Test CapArgumentValue with large binary payload preserves all bytes | tests/test_caller.py:245 |
| test284 | `test_284_handshake_host_cartridge` | TEST284: Handshake exchanges HELLO frames, negotiates limits | tests/test_cbor_integration.py:52 |
| test285 | `test_285_request_response_simple` | TEST285: Simple request-response flow (REQ → END with payload) | tests/test_cbor_integration.py:87 |
| test286 | `test_286_streaming_chunks` | TEST286: Streaming response with multiple CHUNK frames | tests/test_cbor_integration.py:127 |
| test287 | `test_287_heartbeat_from_host` | TEST287: Host-initiated heartbeat | tests/test_cbor_integration.py:179 |
| test290 | `test_290_limits_negotiation` | TEST290: Limit negotiation picks minimum | tests/test_cbor_integration.py:217 |
| test291 | `test_291_binary_payload_roundtrip` | TEST291: Binary payload roundtrip (all 256 byte values) | tests/test_cbor_integration.py:249 |
| test292 | `test_292_message_id_uniqueness` | TEST292: Sequential requests get distinct MessageIds | tests/test_cbor_integration.py:294 |
| test299 | `test_299_empty_payload_roundtrip` | TEST299: Empty payload request/response roundtrip | tests/test_cbor_integration.py:335 |
| test304 | `test_304_media_availability_output_constant` | TEST304: Test MEDIA_AVAILABILITY_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:257 |
| test305 | `test_305_media_path_output_constant` | TEST305: Test MEDIA_PATH_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:265 |
| test306 | `test_306_availability_and_path_output_distinct` | TEST306: Test MEDIA_AVAILABILITY_OUTPUT and MEDIA_PATH_OUTPUT are distinct URNs | tests/test_media_urn.py:273 |
| test307 | `test_307_model_availability_urn` | TEST307: Test model_availability_urn builds valid cap URN with correct op and media specs | tests/test_standard_caps.py:27 |
| test308 | `test_308_model_path_urn` | TEST308: Test model_path_urn builds valid cap URN with correct op and media specs | tests/test_standard_caps.py:35 |
| test309 | `test_309_model_availability_and_path_are_distinct` | TEST309: Test model_availability_urn and model_path_urn produce distinct URNs | tests/test_standard_caps.py:43 |
| test310 | `test_310_llm_generate_text_urn_tags` | TEST310: Test llm_generate_text_urn uses llm and ml-model tags | tests/test_standard_caps.py:50 |
| test312 | `test_312_all_urn_builders_produce_valid_urns` | TEST312: Test all URN builders produce parseable cap URNs | tests/test_standard_caps.py:72 |
| test336 | `test_336_file_path_reads_file_passes_bytes` | TEST336: Single file-path arg with stdin source reads file and passes bytes to handler | tests/test_cartridge_runtime.py:526 |
| test337 | `test_337_file_path_without_stdin_passes_string` | TEST337: file-path arg without stdin source passes path as string (no conversion) | tests/test_cartridge_runtime.py:594 |
| test338 | `test_338_file_path_via_cli_flag` | TEST338: file-path arg reads file via --file CLI flag | tests/test_cartridge_runtime.py:624 |
| test339 | `test_339_file_path_array_glob_expansion` | TEST339: file-path-array reads multiple files with glob pattern | tests/test_cartridge_runtime.py:655 |
| test340 | `test_340_file_not_found_clear_error` | TEST340: File not found error provides clear message | tests/test_cartridge_runtime.py:702 |
| test341 | `test_341_stdin_precedence_over_file_path` | TEST341: stdin takes precedence over file-path in source order | tests/test_cartridge_runtime.py:735 |
| test342 | `test_342_file_path_position_zero_reads_first_arg` | TEST342: file-path with position 0 reads first positional arg as file | tests/test_cartridge_runtime.py:770 |
| test343 | `test_343_non_file_path_args_unaffected` | TEST343: Non-file-path args are not affected by file reading | tests/test_cartridge_runtime.py:802 |
| test344 | `test_344_file_path_array_invalid_json_fails` | TEST344: file-path-array with nonexistent path fails clearly | tests/test_cartridge_runtime.py:833 |
| test345 | `test_345_file_path_array_one_file_missing_fails_hard` | TEST345: file-path-array with literal nonexistent path fails hard | tests/test_cartridge_runtime.py:867 |
| test346 | `test_346_large_file_reads_successfully` | TEST346: Large file (1MB) reads successfully | tests/test_cartridge_runtime.py:910 |
| test347 | `test_347_empty_file_reads_as_empty_bytes` | TEST347: Empty file reads as empty bytes | tests/test_cartridge_runtime.py:945 |
| test348 | `test_348_file_path_conversion_respects_source_order` | TEST348: file-path conversion respects source order | tests/test_cartridge_runtime.py:976 |
| test349 | `test_349_file_path_multiple_sources_fallback` | TEST349: file-path arg with multiple sources tries all in order | tests/test_cartridge_runtime.py:1011 |
| test350 | `test_350_full_cli_mode_with_file_path_integration` | TEST350: Integration test - full CLI mode invocation with file-path | tests/test_cartridge_runtime.py:1044 |
| test351 | `test_351_file_path_array_empty_array` | TEST351: file-path array with empty CBOR array returns empty (CBOR mode) | tests/test_cartridge_runtime.py:1116 |
| test352 | `test_352_file_permission_denied_clear_error` | TEST352: file permission denied error is clear (Unix-specific) | tests/test_cartridge_runtime.py:1148 |
| test353 | `test_353_cbor_payload_format_consistency` | TEST353: CBOR payload format matches between CLI and CBOR mode | tests/test_cartridge_runtime.py:1191 |
| test354 | `test_354_glob_pattern_no_matches_empty_array` | TEST354: Glob pattern with no matches fails hard (NO FALLBACK) | tests/test_cartridge_runtime.py:1225 |
| test355 | `test_355_glob_pattern_skips_directories` | TEST355: Glob pattern skips directories | tests/test_cartridge_runtime.py:1260 |
| test356 | `test_356_multiple_glob_patterns_combined` | TEST356: Multiple glob patterns combined | tests/test_cartridge_runtime.py:1306 |
| test357 | `test_357_symlinks_followed` | TEST357: Symlinks are followed when reading files | tests/test_cartridge_runtime.py:1355 |
| test358 | `test_358_binary_file_non_utf8` | TEST358: Binary file with non-UTF8 data reads correctly | tests/test_cartridge_runtime.py:1392 |
| test359 | `test_359_invalid_glob_pattern_fails` | TEST359: Invalid glob pattern fails with clear error | tests/test_cartridge_runtime.py:1426 |
| test360 | `test_360_extract_effective_payload_with_file_data` | TEST360: Extract effective payload handles file-path data correctly | tests/test_cartridge_runtime.py:1462 |
| test361 | `test_361_cli_mode_file_path` | TEST361: CLI mode with file path - pass file path as command-line argument | tests/test_cartridge_runtime.py:1504 |
| test362 | `test_362_cli_mode_piped_binary` | TEST362: CLI mode with binary piped in - pipe binary data via stdin  This test simulates real-world conditions: - Pure binary data piped to stdin (NOT CBOR) - CLI mode detected (command arg present) - Cap accepts stdin source - Binary is chunked on-the-fly and accumulated - Handler receives complete CBOR payload | tests/test_cartridge_runtime.py:1548 |
| test363 | `test_363_cbor_mode_chunked_content` | TEST363: CBOR mode with chunked content - send file content streaming as chunks | tests/test_cartridge_runtime.py:1595 |
| test364 | `test_364_cbor_mode_file_path` | TEST364: CBOR mode with file path - send file path in CBOR arguments (auto-conversion) | tests/test_cartridge_runtime.py:1681 |
| test365 | `test_365_stream_start_frame` | TEST365: Frame::stream_start stores request_id, stream_id, and media_urn | tests/test_cbor_frame.py:422 |
| test366 | `test_366_stream_end_frame` | TEST366: Frame::stream_end stores request_id and stream_id | tests/test_cbor_frame.py:437 |
| test367 | `test_367_stream_start_with_empty_stream_id` | TEST367: StreamStart frame with empty stream_id still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:453 |
| test368 | `test_368_stream_start_with_empty_media_urn` | TEST368: StreamStart frame with empty media_urn still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:464 |
| test389 | `test_389_stream_start_roundtrip` | TEST389: StreamStart encode/decode roundtrip preserves stream_id and media_urn | tests/test_cbor_io.py:692 |
| test390 | `test_390_stream_end_roundtrip` | TEST390: StreamEnd encode/decode roundtrip preserves stream_id, no media_urn | tests/test_cbor_io.py:708 |
| test395 | `test_395_build_payload_small` | TEST395: Small payload (< max_chunk) produces correct CBOR arguments | tests/test_cartridge_runtime.py:1716 |
| test396 | `test_396_build_payload_large` | TEST396: Large payload (> max_chunk) accumulates across chunks correctly | tests/test_cartridge_runtime.py:1748 |
| test397 | `test_397_build_payload_empty` | TEST397: Empty reader produces valid empty CBOR arguments | tests/test_cartridge_runtime.py:1775 |
| test398 | `test_398_build_payload_io_error` | TEST398: IO error from reader propagates as RuntimeError::Io | tests/test_cartridge_runtime.py:1806 |
| test399 | `test_399_relay_notify_discriminant_roundtrip` | TEST399: Verify RelayNotify frame type discriminant roundtrips through u8 (value 10) | tests/test_cbor_frame.py:475 |
| test400 | `test_400_relay_state_discriminant_roundtrip` | TEST400: Verify RelayState frame type discriminant roundtrips through u8 (value 11) | tests/test_cbor_frame.py:484 |
| test401 | `test_401_relay_notify_factory_and_accessors` | TEST401: Verify relay_notify factory stores manifest and limits, and accessors extract them | tests/test_cbor_frame.py:493 |
| test402 | `test_402_relay_state_factory_and_payload` | TEST402: Verify relay_state factory stores resource payload in frame payload field | tests/test_cbor_frame.py:521 |
| test403 | `test_403_frame_type_one_past_cancel` | TEST403: Verify from_u8 returns None for values past the last valid frame type | tests/test_cbor_frame.py:532 |
| test404 | `test_404_slave_sends_relay_notify_on_connect` | TEST404: Slave sends RelayNotify on connect (initial_notify parameter) | tests/test_cartridge_relay.py:22 |
| test405 | `test_405_master_reads_relay_notify` | TEST405: Master reads RelayNotify and extracts manifest + limits | tests/test_cartridge_relay.py:56 |
| test406 | `test_406_slave_stores_relay_state` | TEST406: Slave stores RelayState from master | tests/test_cartridge_relay.py:84 |
| test407 | `test_407_protocol_frames_pass_through` | TEST407: Protocol frames pass through slave transparently (both directions) | tests/test_cartridge_relay.py:121 |
| test408 | `test_408_relay_frames_not_forwarded` | TEST408: RelayNotify/RelayState are NOT forwarded through relay | tests/test_cartridge_relay.py:210 |
| test409 | `test_409_slave_injects_relay_notify_midstream` | TEST409: Slave can inject RelayNotify mid-stream (cap change) | tests/test_cartridge_relay.py:277 |
| test410 | `test_410_master_receives_updated_relay_notify` | TEST410: Master receives updated RelayNotify (cap change callback via read_frame) | tests/test_cartridge_relay.py:326 |
| test411 | `test_411_socket_close_detection` | TEST411: Socket close detection (both directions) | tests/test_cartridge_relay.py:387 |
| test412 | `test_412_bidirectional_concurrent_flow` | TEST412: Bidirectional concurrent frame flow through relay | tests/test_cartridge_relay.py:421 |
| test413 | `test_413_register_cartridge_adds_cap_table` | TEST413: Register cartridge adds entries to cap_table | tests/test_cartridge_host.py:81 |
| test414 | `test_414_capabilities_empty_initially` | TEST414: capabilities() returns empty JSON initially (no running cartridges) | tests/test_cartridge_host.py:96 |
| test415 | `test_415_req_triggers_spawn` | TEST415: REQ for known cap triggers spawn attempt (verified by expected spawn error for non-existent binary) | tests/test_cartridge_host.py:104 |
| test416 | `test_416_attach_cartridge_handshake` | TEST416: Attach cartridge performs HELLO handshake, extracts manifest, updates capabilities | tests/test_cartridge_host.py:134 |
| test417 | `test_417_route_req_by_cap_urn` | TEST417: Route REQ to correct cartridge by cap_urn (with two attached cartridges) | tests/test_cartridge_host.py:161 |
| test418 | `test_418_route_continuation_by_req_id` | TEST418: Route STREAM_START/CHUNK/STREAM_END/END by req_id (not cap_urn) Verifies that after the initial REQ→cartridge routing, all subsequent continuation frames with the same req_id are routed to the same cartridge — even though no cap_urn is present on those frames. | tests/test_cartridge_host.py:222 |
| test419 | `test_419_heartbeat_local_handling` | TEST419: Cartridge HEARTBEAT handled locally (not forwarded to relay) | tests/test_cartridge_host.py:281 |
| test420 | `test_420_cartridge_frames_forwarded_to_relay` | TEST420: Cartridge non-HELLO/non-HB frames forwarded to relay (pass-through) | tests/test_cartridge_host.py:343 |
| test421 | `test_421_cartridge_death_updates_caps` | TEST421: Cartridge death updates capability list (caps removed) | tests/test_cartridge_host.py:401 |
| test422 | `test_422_cartridge_death_sends_err` | TEST422: Cartridge death sends ERR for all pending requests via relay | tests/test_cartridge_host.py:442 |
| test423 | `test_423_multi_cartridge_distinct_caps` | TEST423: Multiple cartridges registered with distinct caps route independently | tests/test_cartridge_host.py:490 |
| test424 | `test_424_concurrent_requests_same_cartridge` | TEST424: Concurrent requests to the same cartridge are handled independently | tests/test_cartridge_host.py:571 |
| test425 | `test_425_find_cartridge_for_cap_unknown` | TEST425: find_cartridge_for_cap returns None for unregistered cap | tests/test_cartridge_host.py:638 |
| test426 | `test_426_single_master_req_response` | TEST426: Single master REQ/response routing | tests/test_relay_switch.py:28 |
| test427 | `test_427_multi_master_cap_routing` | TEST427: Multi-master cap routing | tests/test_relay_switch.py:77 |
| test428 | `test_428_unknown_cap_returns_error` | TEST428: Unknown cap returns error | tests/test_relay_switch.py:159 |
| test429 | `test_429_find_master_for_cap` | TEST429: Cap routing logic (find_master_for_cap) | tests/test_relay_switch.py:192 |
| test430 | `test_430_tie_breaking_same_cap_multiple_masters` | TEST430: Tie-breaking (same cap on multiple masters - first match wins, routing is consistent) | tests/test_relay_switch.py:238 |
| test431 | `test_431_continuation_frame_routing` | TEST431: Continuation frame routing (CHUNK, END follow REQ) | tests/test_relay_switch.py:312 |
| test432 | `test_432_empty_masters_list_error` | TEST432: Empty masters list creates empty switch, add_master works | tests/test_relay_switch.py:373 |
| test433 | `test_433_capability_aggregation_deduplicates` | TEST433: Capability aggregation deduplicates caps | tests/test_relay_switch.py:381 |
| test434 | `test_434_limits_negotiation_minimum` | TEST434: Limits negotiation takes minimum | tests/test_relay_switch.py:436 |
| test435 | `test_435_urn_matching_exact_and_accepts` | TEST435: URN matching (exact vs accepts()) | tests/test_relay_switch.py:477 |
| test436 | `test_436_compute_checksum` | TEST436: Verify FNV-1a checksum function produces consistent results | tests/test_cbor_frame.py:567 |
| test440 | `test_440_chunk_index_checksum_roundtrip` | TEST440: CHUNK frame with chunk_index and checksum roundtrips through encode/decode | tests/test_cbor_io.py:757 |
| test441 | `test_441_stream_end_chunk_count_roundtrip` | TEST441: STREAM_END frame with chunk_count roundtrips through encode/decode | tests/test_cbor_io.py:777 |
| test442 | `test_442_seq_assigner_monotonic_same_rid` | TEST442: SeqAssigner assigns seq 0,1,2,3 for consecutive frames with same RID | tests/test_cbor_frame.py:587 |
| test443 | `test_443_seq_assigner_independent_rids` | TEST443: SeqAssigner maintains independent counters for different RIDs | tests/test_cbor_frame.py:608 |
| test444 | `test_444_seq_assigner_skips_non_flow` | TEST444: SeqAssigner skips non-flow frames (Heartbeat, RelayNotify, RelayState, Hello) | tests/test_cbor_frame.py:633 |
| test445 | `test_445_seq_assigner_remove_by_flow_key` | TEST445: SeqAssigner.remove with FlowKey(rid, None) resets that flow; FlowKey(rid, Some(xid)) is unaffected | tests/test_cbor_frame.py:647 |
| test446 | `test_446_seq_assigner_mixed_types` | TEST446: SeqAssigner handles mixed frame types (REQ, CHUNK, LOG, END) for same RID | tests/test_cbor_frame.py:716 |
| test447 | `test_447_flow_key_with_xid` | TEST447: FlowKey::from_frame extracts (rid, Some(xid)) when routing_id present | tests/test_cbor_frame.py:737 |
| test448 | `test_448_flow_key_without_xid` | TEST448: FlowKey::from_frame extracts (rid, None) when routing_id absent | tests/test_cbor_frame.py:750 |
| test449 | `test_449_flow_key_equality` | TEST449: FlowKey equality: same rid+xid equal, different xid different key | tests/test_cbor_frame.py:760 |
| test450 | `test_450_flow_key_hash_lookup` | TEST450: FlowKey hash: same keys hash equal (HashMap lookup) | tests/test_cbor_frame.py:773 |
| test451 | `test_451_reorder_buffer_in_order` | TEST451: ReorderBuffer in-order delivery: seq 0,1,2 delivered immediately | tests/test_cbor_frame.py:797 |
| test452 | `test_452_reorder_buffer_out_of_order` | TEST452: ReorderBuffer out-of-order: seq 1 then 0 delivers both in order | tests/test_cbor_frame.py:812 |
| test453 | `test_453_reorder_buffer_gap_fill` | TEST453: ReorderBuffer gap fill: seq 0,2,1 delivers 0, buffers 2, then delivers 1+2 | tests/test_cbor_frame.py:828 |
| test454 | `test_454_reorder_buffer_stale_seq` | TEST454: ReorderBuffer stale seq is hard error | tests/test_cbor_frame.py:845 |
| test455 | `test_455_reorder_buffer_overflow` | TEST455: ReorderBuffer overflow triggers protocol error | tests/test_cbor_frame.py:858 |
| test456 | `test_456_reorder_buffer_independent_flows` | TEST456: Multiple concurrent flows reorder independently | tests/test_cbor_frame.py:871 |
| test457 | `test_457_reorder_buffer_cleanup` | TEST457: cleanup_flow removes state; new frames start at seq 0 | tests/test_cbor_frame.py:890 |
| test458 | `test_458_reorder_buffer_non_flow_bypass` | TEST458: Non-flow frames bypass reorder entirely | tests/test_cbor_frame.py:908 |
| test459 | `test_459_reorder_buffer_end_frame` | TEST459: Terminal END frame flows through correctly | tests/test_cbor_frame.py:922 |
| test460 | `test_460_reorder_buffer_err_frame` | TEST460: Terminal ERR frame flows through correctly | tests/test_cbor_frame.py:936 |
| test473 | `test_473_cap_discard_parses_as_valid_urn` | TEST473: CAP_DISCARD parses as valid CapUrn with in=media: and out=media:void | tests/test_standard_caps.py:92 |
| test474 | `test_474_cap_discard_accepts_specific_void_cap` | TEST474: CAP_DISCARD accepts specific-input/void-output caps | tests/test_standard_caps.py:99 |
| test475 | `test_475_validate_passes_with_identity` | TEST475: CapManifest::validate() passes when CAP_IDENTITY is present | tests/test_manifest.py:203 |
| test476 | `test_476_validate_fails_without_identity` | TEST476: CapManifest::validate() fails when CAP_IDENTITY is missing | tests/test_manifest.py:214 |
| test479 | `test_479_custom_identity_overrides_default` | TEST479: Custom identity Op overrides auto-registered default | tests/test_cartridge_runtime.py:1827 |
| test491 | `test_491_chunk_requires_chunk_index_and_checksum` | TEST491: Frame::chunk constructor requires and sets chunk_index and checksum | tests/test_cbor_frame.py:958 |
| test492 | `test_492_stream_end_requires_chunk_count` | TEST492: Frame::stream_end constructor requires and sets chunk_count | tests/test_cbor_frame.py:972 |
| test493 | `test_493_compute_checksum_fnv1a_test_vectors` | TEST493: compute_checksum produces correct FNV-1a hash for known test vectors | tests/test_cbor_frame.py:982 |
| test494 | `test_494_compute_checksum_deterministic` | TEST494: compute_checksum is deterministic | tests/test_cbor_frame.py:989 |
| test495 | `test_495_cbor_rejects_chunk_without_chunk_index` | TEST495: CBOR decode REJECTS CHUNK frame missing chunk_index field | tests/test_cbor_frame.py:999 |
| test496 | `test_496_cbor_rejects_chunk_without_checksum` | TEST496: CBOR decode REJECTS CHUNK frame missing checksum field | tests/test_cbor_frame.py:1018 |
| test497 | `test_497_chunk_corrupted_payload_rejected` | TEST497: Verify CHUNK frame with corrupted payload is rejected by checksum | tests/test_cbor_io.py:792 |
| test498 | `test_498_routing_id_cbor_roundtrip` | TEST498: routing_id field roundtrips through CBOR encoding | tests/test_cbor_frame.py:1052 |
| test499 | `test_499_chunk_index_checksum_cbor_roundtrip` | TEST499: chunk_index and checksum roundtrip through CBOR encoding | tests/test_cbor_frame.py:1067 |
| test500 | `test_500_chunk_count_cbor_roundtrip` | TEST500: chunk_count roundtrips through CBOR encoding | tests/test_cbor_frame.py:1083 |
| test501 | `test_501_frame_new_initializes_optional_fields_none` | TEST501: Frame::new initializes new fields to None | tests/test_cbor_frame.py:1096 |
| test502 | `test_502_keys_module_new_field_constants` | TEST502: Keys module has constants for new fields | tests/test_cbor_frame.py:1106 |
| test503 | `test_503_compute_checksum_empty_data` | TEST503: compute_checksum handles empty data correctly | tests/test_cbor_frame.py:1114 |
| test504 | `test_504_compute_checksum_large_payload` | TEST504: compute_checksum handles large payloads without overflow | tests/test_cbor_frame.py:1120 |
| test505 | `test_505_chunk_with_offset_sets_chunk_index` | TEST505: chunk_with_offset sets chunk_index correctly | tests/test_cbor_frame.py:1130 |
| test506 | `test_506_compute_checksum_different_data_different_hash` | TEST506: Different data produces different checksums | tests/test_cbor_frame.py:1153 |
| test507 | `test_507_reorder_buffer_xid_isolation` | TEST507: ReorderBuffer isolates flows by XID (routing_id) - same RID different XIDs | tests/test_cbor_frame.py:1164 |
| test508 | `test_508_reorder_buffer_duplicate_buffered_seq` | TEST508: ReorderBuffer rejects duplicate seq already in buffer | tests/test_cbor_frame.py:1192 |
| test509 | `test_509_reorder_buffer_large_gap_rejected` | TEST509: ReorderBuffer handles large seq gaps without DOS | tests/test_cbor_frame.py:1205 |
| test510 | `test_510_reorder_buffer_multiple_gaps` | TEST510: ReorderBuffer with multiple interleaved gaps fills correctly | tests/test_cbor_frame.py:1221 |
| test511 | `test_511_reorder_buffer_cleanup_with_buffered_frames` | TEST511: ReorderBuffer cleanup with buffered frames discards them | tests/test_cbor_frame.py:1253 |
| test512 | `test_512_reorder_buffer_burst_delivery` | TEST512: ReorderBuffer delivers burst of consecutive buffered frames | tests/test_cbor_frame.py:1271 |
| test513 | `test_513_reorder_buffer_mixed_types_same_flow` | TEST513: ReorderBuffer different frame types in same flow maintain order | tests/test_cbor_frame.py:1288 |
| test514 | `test_514_reorder_buffer_xid_cleanup_isolation` | TEST514: ReorderBuffer with XID cleanup doesn't affect different XID | tests/test_cbor_frame.py:1311 |
| test515 | `test_515_reorder_buffer_overflow_error_details` | TEST515: ReorderBuffer overflow error includes diagnostic information | tests/test_cbor_frame.py:1341 |
| test516 | `test_516_reorder_buffer_stale_error_details` | TEST516: ReorderBuffer stale error includes diagnostic information | tests/test_cbor_frame.py:1359 |
| test517 | `test_517_flow_key_none_vs_some_xid` | TEST517: FlowKey with None XID differs from Some(xid) | tests/test_cbor_frame.py:1373 |
| test518 | `test_518_reorder_buffer_empty_ready_vec` | TEST518: ReorderBuffer handles zero-length ready vec correctly | tests/test_cbor_frame.py:1385 |
| test519 | `test_519_reorder_buffer_state_persistence` | TEST519: ReorderBuffer state persists across accept calls | tests/test_cbor_frame.py:1395 |
| test520 | `test_520_reorder_buffer_per_flow_limit` | TEST520: ReorderBuffer max_buffer_per_flow is per-flow not global | tests/test_cbor_frame.py:1412 |
| test521 | `test_521_relay_notify_cbor_roundtrip` | TEST521: RelayNotify CBOR roundtrip preserves manifest and limits | tests/test_cbor_frame.py:1435 |
| test522 | `test_522_relay_state_cbor_roundtrip` | TEST522: RelayState CBOR roundtrip preserves payload | tests/test_cbor_frame.py:1453 |
| test523 | `test_523_relay_notify_not_flow_frame` | TEST523: is_flow_frame returns false for RelayNotify | tests/test_cbor_frame.py:1466 |
| test524 | `test_524_relay_state_not_flow_frame` | TEST524: is_flow_frame returns false for RelayState | tests/test_cbor_frame.py:1472 |
| test525 | `test_525_relay_notify_empty_manifest` | TEST525: RelayNotify with empty manifest is valid | tests/test_cbor_frame.py:1478 |
| test526 | `test_526_relay_state_empty_payload` | TEST526: RelayState with empty payload is valid | tests/test_cbor_frame.py:1485 |
| test527 | `test_527_relay_notify_large_manifest` | TEST527: RelayNotify with large manifest roundtrips correctly | tests/test_cbor_frame.py:1492 |
| test528 | `test_528_relay_frames_use_uint_zero_id` | TEST528: RelayNotify and RelayState use MessageId::Uint(0) | tests/test_cbor_frame.py:1505 |
| test544 | `test_544_peer_invoker_sends_end_frame` | TEST544: PeerCall::finish sends END frame In Python, PeerInvokerImpl.invoke() sends END after all args. This test validates that the response queue receives frames including END. | tests/test_cartridge_runtime.py:1901 |
| test545 | `test_545_peer_response_returns_data` | TEST545: PeerCall::finish returns PeerResponse with data | tests/test_cartridge_runtime.py:1926 |
| test546 | `test_546_is_image` | TEST546: is_image returns true only when image marker tag is present | tests/test_media_urn.py:281 |
| test547 | `test_547_is_audio` | TEST547: is_audio returns true only when audio marker tag is present | tests/test_media_urn.py:292 |
| test548 | `test_548_is_video` | TEST548: is_video returns true only when video marker tag is present | tests/test_media_urn.py:303 |
| test549 | `test_549_is_numeric` | TEST549: is_numeric returns true only when numeric marker tag is present | tests/test_media_urn.py:313 |
| test550 | `test_550_is_bool` | TEST550: is_bool returns true only when bool marker tag is present | tests/test_media_urn.py:325 |
| test551 | `test_551_is_file_path` | TEST551: is_file_path returns true for scalar file-path, false for array | tests/test_media_urn.py:337 |
| test552 | `test_552_is_file_path_array` | TEST552: is_file_path_array returns true for list file-path, false for scalar | tests/test_media_urn.py:347 |
| test553 | `test_553_is_any_file_path` | TEST553: is_any_file_path returns true for both scalar and array file-path | tests/test_media_urn.py:356 |
| test555 | `test_555_with_tag_and_without_tag` | TEST555: with_tag adds a tag and without_tag removes it | tests/test_media_urn.py:365 |
| test556 | `test_556_image_media_urn_for_ext` | TEST556: image_media_urn_for_ext creates valid image media URN | tests/test_media_urn.py:381 |
| test557 | `test_557_audio_media_urn_for_ext` | TEST557: audio_media_urn_for_ext creates valid audio media URN | tests/test_media_urn.py:390 |
| test558 | `test_558_predicate_constant_consistency` | TEST558: predicates are consistent with constants — every constant triggers exactly the expected predicates | tests/test_media_urn.py:399 |
| test559 | `test_559_without_tag` | TEST559: without_tag removes tag, ignores in/out, case-insensitive for keys | tests/test_cap_urn.py:666 |
| test560 | `test_560_with_in_out_spec` | TEST560: with_in_spec and with_out_spec change direction specs | tests/test_cap_urn.py:690 |
| test561 | `test_561_in_out_media_urn` | TEST561: in_media_urn and out_media_urn parse direction specs into MediaUrn | tests/test_cap_urn.py:711 |
| test562 | `test_562_canonical_option` | TEST562: canonical_option returns None for None input, canonical string for Some | tests/test_cap_urn.py:731 |
| test563 | `test_563_find_all_matches` | TEST563: CapMatcher::find_all_matches returns all matching caps sorted by specificity | tests/test_cap_urn.py:768 |
| test564 | `test_564_are_compatible` | TEST564: CapMatcher::are_compatible detects bidirectional overlap | tests/test_cap_urn.py:786 |
| test565 | `test_565_tags_to_string` | TEST565: tags_to_string returns only tags portion without prefix | tests/test_cap_urn.py:809 |
| test566 | `test_566_with_tag_ignores_in_out` | TEST566: with_tag silently ignores in/out keys | tests/test_cap_urn.py:821 |
| test567 | `test_567_str_variants` | TEST567: conforms_to_str and accepts_str work with string arguments | tests/test_cap_urn.py:834 |
| test568 | `test_568_dispatch_output_tag_order` | TEST568: is_dispatchable with different tag order in output spec | tests/test_cap_urn.py:750 |
| test569 | `test_569_cap_matrix_unregister_cap_set` | TEST569: unregister_cap_set removes a host and returns true, false if not found | tests/test_cap_matrix.py:338 |
| test570 | `test_570_cap_matrix_clear` | TEST570: clear removes all registered sets | tests/test_cap_matrix.py:355 |
| test571 | `test_571_cap_matrix_get_all_capabilities` | TEST571: get_all_capabilities returns caps from all hosts | tests/test_cap_matrix.py:303 |
| test572 | `test_572_cap_matrix_get_capabilities_for_host` | TEST572: get_capabilities_for_host returns caps for specific host, None for unknown | tests/test_cap_matrix.py:318 |
| test573 | `test_573_cap_matrix_iter_hosts_and_caps` | TEST573: iter_hosts_and_caps iterates all hosts with their capabilities | tests/test_cap_matrix.py:691 |
| test574 | `test_574_cap_block_remove_registry` | TEST574: CapBlock::remove_registry removes by name, returns Arc | tests/test_cap_matrix.py:609 |
| test575 | `test_575_cap_block_get_registry` | TEST575: CapBlock::get_registry returns Arc clone by name | tests/test_cap_matrix.py:634 |
| test576 | `test_576_cap_matrix_get_host_names` | TEST576: CapBlock::get_registry_names returns names in insertion order | tests/test_cap_matrix.py:284 |
| test577 | `test_577_cap_graph_input_output_specs` | TEST577: CapGraph::get_input_specs and get_output_specs return correct sets | tests/test_cap_matrix.py:710 |
| test578 | `test_578_rule1_duplicate_media_urns` | TEST578: RULE1 - duplicate media_urns rejected | tests/test_validation.py:88 |
| test579 | `test_579_rule2_empty_sources` | TEST579: RULE2 - empty sources rejected | tests/test_validation.py:101 |
| test580 | `test_580_rule3_different_stdin_urns` | TEST580: RULE3 - multiple stdin sources with different URNs rejected | tests/test_validation.py:113 |
| test581 | `test_581_rule3_same_stdin_urns_ok` | TEST581: RULE3 - multiple stdin sources with same URN is OK | tests/test_validation.py:126 |
| test582 | `test_582_rule4_duplicate_source_type` | TEST582: RULE4 - duplicate source type in single arg rejected | tests/test_validation.py:137 |
| test583 | `test_583_rule5_duplicate_position` | TEST583: RULE5 - duplicate position across args rejected | tests/test_validation.py:149 |
| test584 | `test_584_rule6_position_gap` | TEST584: RULE6 - position gap rejected (0, 2 without 1) | tests/test_validation.py:162 |
| test585 | `test_585_rule6_sequential_ok` | TEST585: RULE6 - sequential positions (0, 1, 2) pass | tests/test_validation.py:175 |
| test586 | `test_586_rule7_position_and_cli_flag` | TEST586: RULE7 - arg with both position and cli_flag rejected | tests/test_validation.py:186 |
| test587 | `test_587_rule9_duplicate_cli_flag` | TEST587: RULE9 - duplicate cli_flag across args rejected | tests/test_validation.py:198 |
| test588 | `test_588_rule10_reserved_cli_flags` | TEST588: RULE10 - reserved cli_flags rejected | tests/test_validation.py:211 |
| test589 | `test_589_all_rules_pass` | TEST589: valid cap args with mixed sources pass all rules | tests/test_validation.py:225 |
| test590 | `test_590_cli_flag_only_args` | TEST590: validate_cap_args accepts cap with only cli_flag sources (no positions) | tests/test_validation.py:236 |
| test591 | `test_591_is_more_specific_than` | TEST591: is_more_specific_than returns true when self has more tags for same request | tests/test_cap.py:195 |
| test592 | `test_592_remove_metadata` | TEST592: remove_metadata adds then removes metadata correctly | tests/test_cap.py:224 |
| test593 | `test_593_registered_by_lifecycle` | TEST593: registered_by lifecycle — set, get, clear | tests/test_cap.py:243 |
| test594 | `test_594_metadata_json_lifecycle` | TEST594: metadata_json lifecycle — set, get, clear | tests/test_cap.py:264 |
| test595 | `test_595_with_args_constructor` | TEST595: with_args constructor stores args correctly | tests/test_cap.py:282 |
| test596 | `test_596_with_full_definition_constructor` | TEST596: with_full_definition constructor stores all fields | tests/test_cap.py:306 |
| test597 | `test_597_cap_arg_with_full_definition` | TEST597: CapArg::with_full_definition stores all fields including optional ones | tests/test_cap.py:338 |
| test598 | `test_598_cap_output_lifecycle` | TEST598: CapOutput lifecycle — set_output, set/clear metadata | tests/test_cap.py:367 |
| test599 | `test_599_is_empty` | TEST599: is_empty returns true for empty response, false for non-empty | tests/test_response.py:61 |
| test600 | `test_600_size` | TEST600: size returns exact byte count for all content types | tests/test_response.py:76 |
| test601 | `test_601_get_content_type` | TEST601: get_content_type returns correct MIME type for each variant | tests/test_response.py:91 |
| test602 | `test_602_as_type_binary_error` | TEST602: as_type on binary response returns error (cannot deserialize binary) | tests/test_response.py:103 |
| test603 | `test_603_as_bool_edge_cases` | TEST603: as_bool handles all accepted truthy/falsy variants and rejects garbage | tests/test_response.py:112 |
| test605 | `test_605_all_coercion_paths_build_valid_urns` | TEST605: all_coercion_paths each entry builds a valid parseable CapUrn | tests/test_standard_caps.py:115 |
| test606 | `test_606_coercion_urn_specs` | TEST606: coercion_urn in/out specs match the type's media URN constant | tests/test_standard_caps.py:132 |
| test607 | `test_607_media_urns_for_extension_unknown` | TEST607: media_urns_for_extension returns error for unknown extension | tests/test_media_spec.py:562 |
| test608 | `test_608_media_urns_for_extension_populated` | TEST608: media_urns_for_extension returns URNs after adding a spec with extensions | tests/test_media_spec.py:570 |
| test609 | `test_609_get_extension_mappings` | TEST609: get_extension_mappings returns all registered extension->URN pairs | tests/test_media_spec.py:593 |
| test610 | `test_610_get_cached_spec` | TEST610: get_cached_spec returns None for unknown and Some for known | tests/test_media_spec.py:614 |
| test611 | `test_611_is_embedded_profile_comprehensive` | TEST611: is_embedded_profile recognizes all 9 embedded profiles and rejects non-embedded | tests/test_media_profile.py:24 |
| test612 | `test_612_clear_cache` | TEST612: clear_cache empties all in-memory schemas | tests/test_media_profile.py:39 |
| test613 | `test_613_validate_cached` | TEST613: validate_cached validates against cached standard schemas | tests/test_media_profile.py:48 |
| test614 | `test_614_registry_creation` | TEST614: Verify registry creation succeeds and cache directory exists | tests/test_media_spec.py:635 |
| test615 | `test_615_cache_key_generation` | TEST615: Verify cache key generation is deterministic and distinct for different URNs | tests/test_media_spec.py:642 |
| test616 | `test_616_stored_media_spec_to_def` | TEST616: Verify StoredMediaSpec converts to MediaSpecDef preserving all fields | tests/test_media_spec.py:653 |
| test617 | `test_617_normalize_media_urn` | TEST617: Verify normalize_media_urn produces consistent non-empty results | tests/test_media_spec.py:672 |
| test618 | `test_618_registry_creation` | TEST618: Verify profile schema registry creation succeeds with temp cache | tests/test_media_profile.py:69 |
| test619 | `test_619_embedded_schemas_loaded` | TEST619: Verify all 9 embedded standard schemas are loaded on creation | tests/test_media_profile.py:76 |
| test620 | `test_620_string_validation` | TEST620: Verify string schema validates strings and rejects non-strings | tests/test_media_profile.py:87 |
| test621 | `test_621_integer_validation` | TEST621: Verify integer schema validates integers and rejects floats and strings | tests/test_media_profile.py:95 |
| test622 | `test_622_number_validation` | TEST622: Verify number schema validates integers and floats, rejects strings | tests/test_media_profile.py:105 |
| test623 | `test_623_boolean_validation` | TEST623: Verify boolean schema validates true/false and rejects string "true" | tests/test_media_profile.py:114 |
| test624 | `test_624_object_validation` | TEST624: Verify object schema validates objects and rejects arrays | tests/test_media_profile.py:123 |
| test625 | `test_625_string_array_validation` | TEST625: Verify string array schema validates string arrays and rejects mixed arrays | tests/test_media_profile.py:131 |
| test626 | `test_626_unknown_profile_skips_validation` | TEST626: Verify unknown profile URL skips validation and returns Ok | tests/test_media_profile.py:141 |
| test627 | `test_627_is_embedded_profile` | TEST627: Verify is_embedded_profile recognizes standard and rejects custom URLs | tests/test_media_profile.py:148 |
| test628 | `test_628_media_urn_constants_format` | TEST628: Verify media URN constants all start with "media:" prefix | tests/test_media_urn.py:507 |
| test629 | `test_629_profile_constants_format` | TEST629: Verify profile URL constants all start with capdag.com schema prefix | tests/test_media_urn.py:515 |
| test638 | `test_638_no_peer_router_rejects_all` | TEST638: Verify NoPeerRouter rejects all requests with PeerInvokeNotSupported | tests/test_router.py:9 |
| test639 | `test_639_wildcard_empty_cap_defaults` | TEST639: cap: (empty) defaults to in=media:;out=media: | tests/test_cap_urn.py:859 |
| test640 | `test_640_wildcard_in_only_defaults_out` | TEST640: cap:in defaults out to media: | tests/test_cap_urn.py:867 |
| test641 | `test_641_wildcard_out_only_defaults_in` | TEST641: cap:out defaults in to media: | tests/test_cap_urn.py:874 |
| test642 | `test_642_wildcard_in_out_no_values` | TEST642: cap:in;out both become media: | tests/test_cap_urn.py:881 |
| test643 | `test_643_wildcard_explicit_asterisk` | TEST643: cap:in=*;out=* becomes media: | tests/test_cap_urn.py:888 |
| test644 | `test_644_wildcard_specific_in_wildcard_out` | TEST644: cap:in=media:;out=* has specific in, wildcard out | tests/test_cap_urn.py:895 |
| test645 | `test_645_wildcard_in_specific_out` | TEST645: cap:in=*;out=media:text has wildcard in, specific out | tests/test_cap_urn.py:902 |
| test646 | `test_646_wildcard_invalid_in_spec` | TEST646: cap:in=foo fails (invalid media URN) | tests/test_cap_urn.py:909 |
| test647 | `test_647_wildcard_invalid_out_spec` | TEST647: cap:in=media:;out=bar fails (invalid media URN) | tests/test_cap_urn.py:915 |
| test648 | `test_648_wildcard_accepts_specific` | TEST648: Wildcard in/out match specific caps | tests/test_cap_urn.py:921 |
| test649 | `test_649_wildcard_specificity_scoring` | TEST649: Specificity - wildcard has 0, specific has tag count | tests/test_cap_urn.py:930 |
| test650 | `test_650_wildcard_preserve_other_tags` | TEST650: cap:in;out;op=test preserves other tags | tests/test_cap_urn.py:939 |
| test651 | `test_651_wildcard_identity_forms_equivalent` | TEST651: All identity forms produce the same CapUrn | tests/test_cap_urn.py:947 |
| test652 | `test_652_wildcard_cap_identity_constant` | TEST652: CAP_IDENTITY constant matches identity caps regardless of string form | tests/test_cap_urn.py:965 |
| test653 | `test_653_wildcard_identity_routing_isolation` | TEST653: Identity (no tags) does not match specific requests via routing | tests/test_cap_urn.py:978 |
| test667 | `test_667_verify_chunk_checksum_detects_corruption` | TEST667: verify_chunk_checksum detects corrupted payload | tests/test_cbor_frame.py:538 |
| test668 | `test_668_resolve_slot_with_populated_byte_slot_values` | TEST668: Resolve slot with populated byte slot_values using step-index key | tests/test_planner_argument_binding.py:40 |
| test669 | `test_669_resolve_slot_falls_back_to_default` | TEST669: Resolve slot falls back to default when no slot_value or cap_setting | tests/test_planner_argument_binding.py:58 |
| test670 | `test_670_resolve_required_slot_no_value_returns_err` | TEST670: Required slot with no value returns error | tests/test_planner_argument_binding.py:68 |
| test671 | `test_671_resolve_optional_slot_no_value_returns_none` | TEST671: Optional slot with no value returns None | tests/test_planner_argument_binding.py:77 |
| test678 | `test_678_find_stream_equivalent_urn` | TEST678: find_stream with exact equivalent URN (same tags, different order) succeeds | tests/test_cartridge_runtime.py:2068 |
| test679 | `test_679_find_stream_base_vs_full_fails` | TEST679: find_stream with base URN vs full URN fails — is_equivalent is strict This is the root cause of the cartridge_client.rs bug. Sender sent "media:llm-generation-request" but receiver looked for "media:llm-generation-request;json;record". | tests/test_cartridge_runtime.py:2077 |
| test680 | `test_680_require_stream_missing_fails` | TEST680: require_stream with missing URN returns hard StreamError | tests/test_cartridge_runtime.py:2086 |
| test681 | `test_681_find_stream_multiple` | TEST681: find_stream with multiple streams returns the correct one | tests/test_cartridge_runtime.py:2096 |
| test682 | `test_682_require_stream_returns_data` | TEST682: require_stream_str returns UTF-8 string for text data | tests/test_cartridge_runtime.py:2108 |
| test683 | `test_683_find_stream_invalid_urn_returns_none` | TEST683: find_stream returns None for invalid media URN string (not a parse error — just None) | tests/test_cartridge_runtime.py:2117 |
| test823 | `test_823_dispatch_exact_match` | TEST823: is_dispatchable — exact match provider dispatches request | tests/test_cap_urn.py:991 |
| test824 | `test_824_dispatch_contravariant_input` | TEST824: is_dispatchable — provider with broader input handles specific request (contravariance) | tests/test_cap_urn.py:1002 |
| test825 | `test_825_dispatch_request_unconstrained_input` | TEST825: is_dispatchable — request with unconstrained input dispatches to specific provider media: on the request input axis means "unconstrained" — vacuously true | tests/test_cap_urn.py:1013 |
| test826 | `test_826_dispatch_covariant_output` | TEST826: is_dispatchable — provider output must satisfy request output (covariance) | tests/test_cap_urn.py:1025 |
| test827 | `test_827_dispatch_generic_output_fails` | TEST827: is_dispatchable — provider with generic output cannot satisfy specific request | tests/test_cap_urn.py:1037 |
| test828 | `test_828_dispatch_wildcard_requires_tag_presence` | TEST828: is_dispatchable — wildcard * tag in request, provider missing tag → reject | tests/test_cap_urn.py:1049 |
| test829 | `test_829_dispatch_wildcard_with_tag_present` | TEST829: is_dispatchable — wildcard * tag in request, provider has tag → accept | tests/test_cap_urn.py:1061 |
| test830 | `test_830_dispatch_provider_extra_tags` | TEST830: is_dispatchable — provider extra tags are refinement, always OK | tests/test_cap_urn.py:1073 |
| test831 | `test_831_dispatch_cross_backend_mismatch` | TEST831: is_dispatchable — cross-backend mismatch prevented | tests/test_cap_urn.py:1085 |
| test832 | `test_832_dispatch_asymmetric` | TEST832: is_dispatchable is NOT symmetric | tests/test_cap_urn.py:1097 |
| test833 | `test_833_comparable_symmetric` | TEST833: is_comparable — both directions checked | tests/test_cap_urn.py:1116 |
| test834 | `test_834_comparable_unrelated` | TEST834: is_comparable — unrelated caps are NOT comparable | tests/test_cap_urn.py:1128 |
| test835 | `test_835_equivalent_identical` | TEST835: is_equivalent — identical caps | tests/test_cap_urn.py:1140 |
| test836 | `test_836_equivalent_non_equivalent` | TEST836: is_equivalent — non-equivalent comparable caps | tests/test_cap_urn.py:1152 |
| test837 | `test_837_dispatch_op_mismatch` | TEST837: is_dispatchable — op tag mismatch rejects | tests/test_cap_urn.py:1164 |
| test838 | `test_838_dispatch_request_wildcard_output` | TEST838: is_dispatchable — request with wildcard output accepts any provider output | tests/test_cap_urn.py:1175 |
| test839 | `test_839_peer_response_delivers_logs_before_stream_start` | TEST839: LOG frames arriving BEFORE StreamStart are delivered immediately  This tests the critical fix: during a peer call, the peer (e.g., modelcartridge) sends LOG frames for minutes during model download BEFORE sending any data (StreamStart + Chunk). The handler must receive these LOGs in real-time so it can re-emit progress and keep the engine's activity timer alive.  Previously, demux_single_stream blocked on awaiting StreamStart before returning PeerResponse, which meant the handler couldn't call recv() until data arrived — causing 120s activity timeouts during long downloads. | tests/test_cartridge_runtime.py:1956 |
| test840 | `test_840_peer_response_collect_bytes_discards_logs` | TEST840: PeerResponse::collect_bytes discards LOG frames | tests/test_cartridge_runtime.py:2007 |
| test841 | `test_841_peer_response_collect_value_discards_logs` | TEST841: PeerResponse::collect_value discards LOG frames | tests/test_cartridge_runtime.py:2037 |
| test842 | `test_842_progress_sender_emits_frames` | TEST842: run_with_keepalive returns closure result (fast operation, no keepalive frames) (Mirrors Rust run_with_keepalive returning closure result — Python doesn't have run_with_keepalive because blocking model loads are not done via tokio. Instead we test ProgressSender directly.) | tests/test_cartridge_runtime.py:2133 |
| test843 | `test_843_progress_sender_from_background_thread` | TEST843: run_with_keepalive returns Ok/Err from closure | tests/test_cartridge_runtime.py:2150 |
| test844 | `test_844_progress_sender_multiple_threads` | TEST844: run_with_keepalive propagates errors from closure | tests/test_cartridge_runtime.py:2173 |
| test845 | `test_845_progress_sender_independent_of_emitter` | TEST845: ProgressSender emits progress and log frames independently of OutputStream | tests/test_cartridge_runtime.py:2198 |
| test846 | `test_846_progress_frame_roundtrip` | TEST846: Test progress LOG frame encode/decode roundtrip preserves progress float | tests/test_cbor_io.py:813 |
| test847 | `test_847_progress_double_roundtrip` | TEST847: Double roundtrip (modelcartridge → relay → candlecartridge) | tests/test_cbor_io.py:846 |
| test848 | `test_848_relay_notify_roundtrip` | TEST848: RelayNotify encode/decode roundtrip preserves manifest and limits | tests/test_cbor_io.py:723 |
| test849 | `test_849_relay_state_roundtrip` | TEST849: RelayState encode/decode roundtrip preserves resource payload | tests/test_cbor_io.py:745 |
| test852 | `test_852_lub_identical` | TEST852: LUB of identical URNs returns the same URN | tests/test_media_urn.py:435 |
| test853 | `test_853_lub_no_common_tags` | TEST853: LUB of URNs with no common tags returns media: (universal) | tests/test_media_urn.py:442 |
| test854 | `test_854_lub_partial_overlap` | TEST854: LUB keeps common tags, drops differing ones | tests/test_media_urn.py:452 |
| test855 | `test_855_lub_list_vs_scalar` | TEST855: LUB of list and non-list drops list tag | tests/test_media_urn.py:462 |
| test856 | `test_856_lub_empty` | TEST856: LUB of empty input returns universal type | tests/test_media_urn.py:472 |
| test857 | `test_857_lub_single` | TEST857: LUB of single input returns that input | tests/test_media_urn.py:479 |
| test858 | `test_858_lub_three_inputs` | TEST858: LUB with three+ inputs narrows correctly | tests/test_media_urn.py:486 |
| test859 | `test_859_lub_valued_tags` | TEST859: LUB with valued tags (non-marker) that differ | tests/test_media_urn.py:497 |
| test890 | `test_890_direction_semantic_matching` | TEST890: Semantic direction matching - generic provider matches specific request | tests/test_cap_urn.py:1187 |
| test891 | `test_891_direction_semantic_specificity` | TEST891: Semantic direction specificity - more media URN tags = higher specificity | tests/test_cap_urn.py:1228 |
| test892 | `test_892_extensions_serialization` | TEST892: Test extensions serializes/deserializes correctly in MediaSpecDef | tests/test_media_spec.py:480 |
| test893 | `test_893_extensions_with_metadata_and_validation` | TEST893: Test extensions can coexist with metadata and validation | tests/test_media_spec.py:502 |
| test894 | `test_894_multiple_extensions` | TEST894: Test multiple extensions in a media spec | tests/test_media_spec.py:535 |
| test902 | `test_902_compute_checksum_empty` | TEST902: Verify FNV-1a checksum handles empty data | tests/test_cbor_frame.py:1514 |
| test903 | `test_903_chunk_with_chunk_index_and_checksum` | TEST903: Verify CHUNK frame can store chunk_index and checksum fields | tests/test_cbor_frame.py:1520 |
| test904 | `test_904_stream_end_with_chunk_count` | TEST904: Verify STREAM_END frame can store chunk_count field | tests/test_cbor_frame.py:1536 |
| test907 | `test_907_cbor_rejects_stream_end_without_chunk_count` | TEST907: Offline flag blocks fetch_from_registry without making HTTP request | tests/test_cbor_frame.py:1547 |
| test920 | `test_920_cap_urn_total_order_basic` | TEST920: Tests creation of a simple execution plan with a single capability Verifies that single_cap() generates a valid plan with input_slot, cap node, and output node The Rust Ord impl compares (in_urn, out_urn, tags) structurally. Python mirrors this via _cmp_key(). This test checks that URNs with different in/out/tag combinations sort in a deterministic, consistent order and that the ordering is self-consistent (not just accidentally True for one pair). | tests/test_cap_urn.py:1258 |
| test921 | `test_921_cap_urn_order_consistent_with_equality` | TEST921: Tests creation of a linear chain of capabilities connected in sequence Verifies that linear_chain() correctly links multiple caps with proper edges and topological order a == b must imply not (a < b) and not (b < a). A violation here would mean `sorted()` or `bisect` give wrong results for equal caps. | tests/test_cap_urn.py:1289 |
| test922 | `test_922_cap_urn_list_sortable` | TEST922: Tests creation and validation of an empty execution plan with no nodes Verifies that plans without capabilities are valid and handle zero nodes correctly The point of Ord is to support sorted collections. If `sorted()` raises or gives a non-deterministic result, the planner's path-ranking step would be order-dependent and non-reproducible across runs. | tests/test_cap_urn.py:1304 |
| test923 | `test_923_cap_urn_order_returns_not_implemented_for_non_cap` | TEST923: Tests storing and retrieving metadata attached to an execution plan Verifies that arbitrary JSON metadata can be associated with a plan for context preservation against a non-CapUrn, which lets Python fall back to the reflected operation or raise TypeError — the correct Python comparison protocol. | tests/test_cap_urn.py:1324 |
| test976 | `test_976_cap_graph_find_best_path` | TEST976: CapGraph::find_best_path returns highest-specificity path over shortest | tests/test_cap_matrix.py:647 |
| test1105 | `test_1105_two_steps_same_cap_urn_different_slot_values` | TEST1105: Two steps with the same cap_urn get distinct slot values via different node_ids. This is the core disambiguation scenario that step-index keying was designed to solve. | tests/test_planner_argument_binding.py:90 |
| test1106 | `test_1106_slot_falls_through_to_cap_settings_shared` | TEST1106: Slot resolution falls through to cap_settings when no slot_value exists. cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value. | tests/test_planner_argument_binding.py:118 |
| test1107 | `test_1107_slot_value_overrides_cap_settings_per_step` | TEST1107: step_0 has a slot_value override, step_1 falls through to cap_settings. Proves per-step override works while shared settings remain as fallback. | tests/test_planner_argument_binding.py:139 |
| test1108 | `test_1108_resolve_all_passes_node_id` | TEST1108: ResolveAll with node_id threads correctly through to each binding. | tests/test_planner_argument_binding.py:166 |
| test1109 | `test_1109_slot_key_uses_node_id_not_cap_urn` | TEST1109: Slot key uses node_id, NOT cap_urn — a slot_value keyed by cap_urn must not match. | tests/test_planner_argument_binding.py:193 |
| test1110 | `test_1110_no_capability_steps_error_on_empty_wirings` | TEST1110: resolve_pre_interned with empty wirings raises NoCapabilityStepsError. | tests/test_machine.py:106 |
| test1111 | `test_1111_unknown_cap_error_when_not_in_registry` | TEST1111: resolve_pre_interned raises UnknownCapError when cap is not cached. | tests/test_machine.py:117 |
| test1112 | `test_1112_single_edge_strand_resolves_correctly` | TEST1112: resolve_strand on a one-cap strand produces one edge, correct anchors. | tests/test_machine.py:137 |
| test1113 | `test_1113_two_step_chain_shares_intermediate_node` | TEST1113: resolve_strand on a two-cap chain shares the intermediate NodeId. | tests/test_machine.py:163 |
| test1114 | `test_1114_from_strand_produces_single_strand_machine` | TEST1114: Machine.from_strand always yields exactly one strand. | tests/test_machine.py:199 |
| test1115 | `test_1115_from_strands_keeps_strands_disjoint` | TEST1115: Machine.from_strands with two strands produces two disjoint MachineStrands. | tests/test_machine.py:217 |
| test1116 | `test_1116_from_strands_empty_raises_no_capability_steps` | TEST1116: Machine.from_strands([]) raises NoCapabilityStepsError. | tests/test_machine.py:242 |
| test1117 | `test_1117_machine_is_equivalent_strict_positional_order_matters` | TEST1117: Two machines with same strands in different order are NOT equivalent. | tests/test_machine.py:253 |
| test1118 | `test_1118_strand_is_equivalent_consistent_node_bijection` | TEST1118: ForEach not synthesized without cap consumers even with is_sequence=true | tests/test_machine.py:278 |
| test1119 | `test_1119_match_sources_to_args_single_trivial` | TEST1119: Single source matching single arg at distance 0 succeeds with correct pair. | tests/test_machine.py:299 |
| test1120 | `test_1120_match_sources_more_specific_source_matches_general_arg` | TEST1120: source media:txt;textable conforms to arg media:textable → matched with nonzero cost. | tests/test_machine.py:316 |
| test1121 | `test_1121_match_sources_unmatched_source_fails_hard` | TEST1121: Source that conforms to no arg raises UnmatchedSourceInCapArgsError. | tests/test_machine.py:330 |
| test1122 | `test_1122_match_sources_ambiguous_raises_ambiguous_error` | TEST1122: Two sources with identical URNs competing for two identical-cost args → ambiguous. | tests/test_machine.py:348 |
| test1123 | `test_1123_cyclic_strand_fails_hard` | TEST1123: Cartridge ERR frame flows back to engine through relay | tests/test_machine.py:366 |
| test1124 | `test_1124_machine_parse_error_wraps_syntax_error` | TEST1124: parse_machine on empty input raises MachineParseError wrapping MachineSyntaxError. | tests/test_machine.py:395 |
| test1125 | `test_1125_parse_machine_unknown_cap_raises_parse_error_with_abstraction_cause` | TEST1125: parse_machine with cap not in registry raises MachineParseError (abstraction). | tests/test_machine.py:411 |
| test1126 | `test_1126_parse_machine_single_wiring_one_strand` | TEST1126: parse_machine on a simple one-edge notation produces Machine with one strand. | tests/test_machine.py:433 |
| test1127 | `test_1127_parse_machine_disconnected_wirings_become_separate_strands` | TEST1127: Two wirings with no shared node names are separate strands. | tests/test_machine.py:455 |
| test1128 | `test_1128_parse_machine_shared_node_name_yields_one_strand` | TEST1128: Two wirings sharing a node name form one connected strand. | tests/test_machine.py:480 |
| test1129 | `test_1129_binding_slot_identity_is_outer_media_urn` | TEST1129: A JSON document produced by capgraph (the canonical source) with a `documentation` field must deserialize into a Cap with the body intact. Models the actual on-disk shape — not a synthetic round-trip — to catch a mismatch between the JSON schema and the Rust struct field naming. | tests/test_machine.py:506 |
| test1130 | `test_1130_strand_equivalence_rejects_mismatched_node_urns` | TEST1130: documentation set/clear lifecycle parallels cap_description. Catches a regression where the setter or clearer is wired to the wrong field — for example, set_documentation accidentally writing to cap_description. | tests/test_machine.py:548 |
| test1131 | `test_1131_resolve_strand_foreach_sets_is_loop_on_next_cap` | TEST1131: A strand with a ForEach step followed by a Cap step produces is_loop=True on the edge. | tests/test_machine.py:574 |
| test1132 | `test_1132_resolve_strand_no_cap_steps_raises_no_capability_steps` | TEST1132: A strand with only ForEach (no CAP step) raises NoCapabilityStepsError. | tests/test_machine.py:610 |
| test1133 | `test_1133_machine_from_string_delegates_to_parse_machine` | TEST1133: Machine.from_string(notation, registry) returns the same Machine as parse_machine. | tests/test_machine.py:637 |
| | | | |
| unnumbered | `test_abstraction_error_subclass_hierarchy` | TEST1134: All resolution error subclasses are instances of MachineAbstractionError. | tests/test_machine.py:659 |
| unnumbered | `test_array_schema_validation` | TEST: Schema validation with array schemas | tests/test_schema_validation.py:207 |
| unnumbered | `test_assignment_bindings_sorted_by_slot_urn` | Mirror-specific coverage: Assignment bindings are sorted by cap_arg_media_urn for canonical form | tests/test_machine.py:736 |
| unnumbered | `test_cap_caller_get_positional_arg_positions` |  | tests/test_caller.py:329 |
| unnumbered | `test_cap_caller_validate_arguments_missing_required` |  | tests/test_caller.py:294 |
| unnumbered | `test_cap_caller_validate_arguments_success` |  | tests/test_caller.py:277 |
| unnumbered | `test_cap_caller_validate_arguments_unknown` |  | tests/test_caller.py:311 |
| unnumbered | `test_chunk_corrupted_payload_rejected` | Mirror-specific coverage: chunk corrupted payload is detected by checksum mismatch (verify_chunk_checksum) | tests/test_cbor_frame.py:1035 |
| unnumbered | `test_chunking_data_integrity_3x` | Mirror-specific coverage: Test auto-chunking preserves data integrity across chunk boundaries for 3x max_chunk payload | tests/test_cbor_io.py:658 |
| unnumbered | `test_concatenated_vs_final_payload_divergence` | Mirror-specific coverage: Test that concatenated() returns full payload while final_payload() returns only last chunk | tests/test_cartridge_host_runtime.py:265 |
| unnumbered | `test_exact_max_chunk_stream_chunked` | Mirror-specific coverage: Test payload exactly equal to max_chunk produces STREAM_START + 1 CHUNK + STREAM_END + END | tests/test_cbor_io.py:591 |
| unnumbered | `test_extract_effective_payload_invalid_cap_urn` | Mirror-specific coverage: Test extract_effective_payload with invalid cap URN returns CapUrn error | tests/test_cartridge_runtime.py:362 |
| unnumbered | `test_input_validation_optional_arg` | Extra Python-specific validation coverage: optional argument omitted | tests/test_validation.py:57 |
| unnumbered | `test_input_validation_too_many_args` | Extra Python-specific validation coverage: too many positional arguments | tests/test_validation.py:71 |
| unnumbered | `test_llm_generate_text_urn_specs` | Mirror-specific coverage: Test llm_generate_text_urn in/out specs match the expected media URNs semantically | tests/test_standard_caps.py:58 |
| unnumbered | `test_max_chunk_plus_one_splits_into_two_chunks` | Mirror-specific coverage: Test payload of max_chunk + 1 produces STREAM_START + 2 CHUNK + STREAM_END + END | tests/test_cbor_io.py:622 |
| unnumbered | `test_nested_object_schema_validation` | TEST: Schema validation with nested object schemas | tests/test_schema_validation.py:154 |
| unnumbered | `test_normalize_urn_with_trailing_semicolon` |  | tests/test_registry.py:300 |
| unnumbered | `test_output_validation_with_details` | TEST: Output validation with error details | tests/test_schema_validation.py:335 |
| unnumbered | `test_parse_machine_undefined_alias_raises_syntax_error` | TEST1136: parse_machine with undefined cap alias raises MachineParseError wrapping UndefinedAliasError. | tests/test_machine.py:695 |
| unnumbered | `test_registry_add_caps_to_cache` | Additional integration tests for registry functionality | tests/test_registry.py:257 |
| unnumbered | `test_registry_cache_key_consistency` |  | tests/test_registry.py:274 |
| unnumbered | `test_registry_config_builder_pattern` |  | tests/test_registry.py:290 |
| unnumbered | `test_seq_assigner_same_rid_different_xids_independent` | Mirror-specific coverage: SeqAssigner same RID different XIDs are independent | tests/test_cbor_frame.py:687 |
| unnumbered | `test_strand_node_urn_accessor` | TEST1135: MachineStrand.node_urn(id) returns the MediaUrn at that NodeId. | tests/test_machine.py:676 |
| unnumbered | `test_two_strand_machine_serializes_to_notation` | TEST1137: Machine with two strands serializes to a non-empty notation string. | tests/test_machine.py:711 |
| unnumbered | `test_type_constraint_validation` | TEST: Schema validation with type constraints | tests/test_schema_validation.py:251 |
| unnumbered | `test_validate_multiple_arguments` | TEST: Schema validation with multiple arguments | tests/test_schema_validation.py:286 |
| unnumbered | `test_write_frame_writes_length_prefixed` | Mirror-specific coverage: Test write_frame writes length-prefixed frame | tests/test_cbor_io.py:80 |
| unnumbered | `test_write_stream_chunked_reassembly` | Mirror-specific coverage: Test write_stream_chunked sends STREAM_START + CHUNK(s) + STREAM_END + END for payload larger than max_chunk, CHUNK frames + END frame, and reading them back reassembles the full original data | tests/test_cbor_io.py:549 |
---

## Unnumbered Tests

The following tests are cataloged but do not currently participate in numeric test indexing.

- `test_abstraction_error_subclass_hierarchy` — tests/test_machine.py:659
- `test_array_schema_validation` — tests/test_schema_validation.py:207
- `test_assignment_bindings_sorted_by_slot_urn` — tests/test_machine.py:736
- `test_cap_caller_get_positional_arg_positions` — tests/test_caller.py:329
- `test_cap_caller_validate_arguments_missing_required` — tests/test_caller.py:294
- `test_cap_caller_validate_arguments_success` — tests/test_caller.py:277
- `test_cap_caller_validate_arguments_unknown` — tests/test_caller.py:311
- `test_chunk_corrupted_payload_rejected` — tests/test_cbor_frame.py:1035
- `test_chunking_data_integrity_3x` — tests/test_cbor_io.py:658
- `test_concatenated_vs_final_payload_divergence` — tests/test_cartridge_host_runtime.py:265
- `test_exact_max_chunk_stream_chunked` — tests/test_cbor_io.py:591
- `test_extract_effective_payload_invalid_cap_urn` — tests/test_cartridge_runtime.py:362
- `test_input_validation_optional_arg` — tests/test_validation.py:57
- `test_input_validation_too_many_args` — tests/test_validation.py:71
- `test_llm_generate_text_urn_specs` — tests/test_standard_caps.py:58
- `test_max_chunk_plus_one_splits_into_two_chunks` — tests/test_cbor_io.py:622
- `test_nested_object_schema_validation` — tests/test_schema_validation.py:154
- `test_normalize_urn_with_trailing_semicolon` — tests/test_registry.py:300
- `test_output_validation_with_details` — tests/test_schema_validation.py:335
- `test_parse_machine_undefined_alias_raises_syntax_error` — tests/test_machine.py:695
- `test_registry_add_caps_to_cache` — tests/test_registry.py:257
- `test_registry_cache_key_consistency` — tests/test_registry.py:274
- `test_registry_config_builder_pattern` — tests/test_registry.py:290
- `test_seq_assigner_same_rid_different_xids_independent` — tests/test_cbor_frame.py:687
- `test_strand_node_urn_accessor` — tests/test_machine.py:676
- `test_two_strand_machine_serializes_to_notation` — tests/test_machine.py:711
- `test_type_constraint_validation` — tests/test_schema_validation.py:251
- `test_validate_multiple_arguments` — tests/test_schema_validation.py:286
- `test_write_frame_writes_length_prefixed` — tests/test_cbor_io.py:80
- `test_write_stream_chunked_reassembly` — tests/test_cbor_io.py:549

---

*Generated from CapDag-Py source tree*
*Total tests: 636*
*Total numbered tests: 606*
*Total unnumbered tests: 30*
