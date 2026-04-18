# CapDag-Py Test Catalog

**Total Tests:** 888

**Numbered Tests:** 859

**Unnumbered Tests:** 29

**Numbered Tests Missing Descriptions:** 2

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
| test051 | `test_051_input_validation_success` | TEST051: Test input validation succeeds with valid positional argument | tests/test_validation.py:30 |
| test052 | `test_052_input_validation_missing_required` | TEST052: Test input validation fails with MissingRequiredArgument when required arg missing | tests/test_validation.py:44 |
| test053 | `test_053_input_validation_wrong_type` | TEST053: Test input validation fails with InvalidArgumentType when wrong type provided | tests/test_validation.py:98 |
| test054 | `test_054_xv5_inline_spec_redefinition_detected` | TEST054: XV5 - Test inline media spec redefinition of existing registry spec is detected and rejected | tests/test_validation.py:120 |
| test055 | `test_055_xv5_new_inline_spec_allowed` | TEST055: XV5 - Test new inline media spec (not in registry) is allowed | tests/test_validation.py:142 |
| test056 | `test_056_xv5_empty_media_specs_allowed` | TEST056: XV5 - Test empty media_specs (no inline specs) passes XV5 validation | tests/test_validation.py:162 |
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
| test118 | `test_118_best_cap_set_selection` | TEST118: Test selecting best cap set based on specificity ranking With is_dispatchable semantics: - Provider must satisfy ALL request constraints - General request matches specific provider (provider refines request) - Specific request does NOT match general provider (provider lacks constraints) | tests/test_cap_matrix.py:62 |
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
| test135 | `test_135_registry_creation` | TEST135: Test registry creation with temporary cache directory succeeds | tests/test_registry.py:32 |
| test136 | `test_136_cache_key_generation` | TEST136: Test cache key generation produces consistent hashes for same URN | tests/test_registry.py:44 |
| test137 | `test_137_parse_registry_json` | TEST137: Test parsing registry JSON without stdin args verifies cap structure | tests/test_registry.py:69 |
| test138 | `test_138_parse_registry_json_with_stdin` | TEST138: Test parsing registry JSON with stdin args verifies stdin media URN extraction | tests/test_registry.py:114 |
| test139 | `test_139_url_keeps_cap_prefix_literal` | TEST139: Test URL construction keeps cap prefix literal and only encodes tags part | tests/test_registry.py:137 |
| test140 | `test_140_url_encodes_quoted_media_urns` | TEST140: Test URL encodes media URNs with proper percent encoding for special characters | tests/test_registry.py:154 |
| test141 | `test_141_exact_url_format` | TEST141: Test exact URL format contains properly encoded media URN components | tests/test_registry.py:174 |
| test142 | `test_142_normalize_handles_different_tag_orders` | TEST142: Test normalize handles different tag orders producing same canonical form | tests/test_registry.py:191 |
| test143 | `test_143_default_config` | TEST143: Test default config uses capdag.com or environment variable values | tests/test_registry.py:204 |
| test144 | `test_144_custom_registry_url` | TEST144: Test custom registry URL updates both registry and schema base URLs | tests/test_registry.py:214 |
| test145 | `test_145_custom_registry_and_schema_url` | TEST145: Test custom registry and schema URLs set independently | tests/test_registry.py:259 |
| test146 | `test_146_schema_url_not_overwritten_when_explicit` | TEST146: Test schema URL not overwritten when set explicitly before registry URL | tests/test_registry.py:270 |
| test147 | `test_147_registry_for_test_with_config` | TEST147: Test registry for test with custom config creates registry with specified URLs | tests/test_registry.py:282 |
| test148 | `test_148_cap_manifest_creation` | TEST148: Test creating cap manifest with name, version, description, and caps | tests/test_manifest.py:20 |
| test149 | `test_149_cap_manifest_with_author` | TEST149: Test cap manifest with author field sets author correctly | tests/test_manifest.py:39 |
| test150 | `test_150_cap_manifest_json_serialization` | TEST150: Test cap manifest JSON serialization and deserialization roundtrip | tests/test_manifest.py:54 |
| test151 | `test_151_cap_manifest_required_fields` | TEST151: Test cap manifest deserialization fails when required fields are missing | tests/test_manifest.py:91 |
| test152 | `test_152_cap_manifest_with_multiple_caps` | TEST152: Test cap manifest with multiple caps stores and retrieves all capabilities | tests/test_manifest.py:103 |
| test153 | `test_153_cap_manifest_with_page_url` | TEST153: Test cap manifest with empty caps list serializes and deserializes correctly | tests/test_manifest.py:128 |
| test154 | `test_154_cap_manifest_optional_fields` | TEST154: Test cap manifest optional author field skipped in serialization when None | tests/test_manifest.py:143 |
| test155 | `test_155_cap_manifest_complex_roundtrip` | TEST155: Test ComponentMetadata trait provides manifest and caps accessor methods | tests/test_manifest.py:167 |
| test156 | `test_156_stdin_source_data_creation` | TEST156: Test creating StdinSource Data variant with byte vector | tests/test_caller.py:33 |
| test157 | `test_157_stdin_source_file_reference_creation` | TEST157: Test creating StdinSource FileReference variant with all required fields | tests/test_caller.py:42 |
| test158 | `test_158_stdin_source_data_empty` | TEST158: Test StdinSource Data with empty vector stores and retrieves correctly | tests/test_caller.py:62 |
| test159 | `test_159_stdin_source_data_binary` | TEST159: Test StdinSource Data with binary content like PNG header bytes | tests/test_caller.py:69 |
| test160 | `test_160_stdin_source_data_clone` | TEST160: Test StdinSource Data clone creates independent copy with same data | tests/test_caller.py:80 |
| test161 | `test_161_stdin_source_file_reference_clone` | TEST161: Test StdinSource FileReference clone creates independent copy with same fields | tests/test_caller.py:98 |
| test162 | `test_162_stdin_source_debug_format` | TEST162: Test StdinSource Debug format displays variant type and relevant fields | tests/test_caller.py:118 |
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
| test205 | `test_205_encode_frame_produces_cbor_with_integer_keys` | TEST205: Test REQ frame encode/decode roundtrip preserves all fields | tests/test_cbor_io.py:36 |
| test206 | `test_206_decode_frame_parses_cbor_correctly` | TEST206: Test HELLO frame encode/decode roundtrip preserves max_frame, max_chunk, max_reorder_buffer | tests/test_cbor_io.py:54 |
| test207 | `test_207_decode_frame_fails_on_invalid_cbor` | TEST207: Test ERR frame encode/decode roundtrip preserves error code and message | tests/test_cbor_io.py:66 |
| test208 | `test_208_decode_frame_fails_on_non_map` | TEST208: Test LOG frame encode/decode roundtrip preserves level and message | tests/test_cbor_io.py:72 |
| test210 | `test_210_read_frame_reads_length_prefixed` | TEST210: Test END frame encode/decode roundtrip preserves eof marker and optional payload | tests/test_cbor_io.py:97 |
| test211 | `test_211_read_frame_returns_none_on_eof` | TEST211: Test HELLO with manifest encode/decode roundtrip preserves manifest bytes and limits | tests/test_cbor_io.py:114 |
| test212 | `test_212_read_frame_fails_on_incomplete_length_prefix` | TEST212: Test chunk_with_offset encode/decode roundtrip preserves offset, len, eof (with stream_id) | tests/test_cbor_io.py:123 |
| test213 | `test_213_read_frame_fails_on_incomplete_frame_data` | TEST213: Test heartbeat frame encode/decode roundtrip preserves ID with no extra fields | tests/test_cbor_io.py:132 |
| test214 | `test_214_write_read_frame_io_roundtrip` | TEST214: Test write_frame/read_frame IO roundtrip through length-prefixed wire format | tests/test_cbor_io.py:142 |
| test215 | `test_215_frame_reader_reads_multiple_frames` | TEST215: Test reading multiple sequential frames from a single buffer | tests/test_cbor_io.py:163 |
| test216 | `test_216_write_frame_rejects_oversized_frame` | TEST216: Test write_frame rejects frames exceeding max_frame limit | tests/test_cbor_io.py:200 |
| test217 | `test_217_read_frame_rejects_oversized_incoming_frame` | TEST217: Test read_frame rejects incoming frames exceeding the negotiated max_frame limit | tests/test_cbor_io.py:216 |
| test218 | `test_218_write_chunked_splits_and_reconstructs` | TEST218: Test write_chunked splits data into chunks respecting max_chunk and reconstructs correctly Chunks from write_chunked have seq=0. SeqAssigner at the output stage assigns final seq. Chunk ordering within a stream is tracked by chunk_index (chunk_index field). | tests/test_cbor_io.py:235 |
| test219 | `test_219_write_chunked_empty_data` | TEST219: Test write_chunked with empty data produces a single EOF chunk | tests/test_cbor_io.py:280 |
| test220 | `test_220_write_chunked_exact_fit` | TEST220: Test write_chunked with data exactly equal to max_chunk produces exactly one chunk | tests/test_cbor_io.py:300 |
| test221 | `test_221_read_frame_returns_none_on_eof` | TEST221: Test read_frame returns Ok(None) on clean EOF (empty stream) | tests/test_cbor_io.py:320 |
| test222 | `test_222_read_frame_fails_on_truncated_length_prefix` | TEST222: Test read_frame handles truncated length prefix (fewer than 4 bytes available) | tests/test_cbor_io.py:326 |
| test223 | `test_223_read_frame_fails_on_truncated_frame_body` | TEST223: Test read_frame returns error on truncated frame body (length prefix says more bytes than available) | tests/test_cbor_io.py:333 |
| test224 | `test_224_handshake_negotiates_to_minimum_limits` | TEST224: Test MessageId::Uint roundtrips through encode/decode | tests/test_cbor_io.py:489 |
| test225 | `test_225_handshake_function_full_handshake` | TEST225: Test decode_frame rejects non-map CBOR values (e.g., array, integer, string) | tests/test_cbor_io.py:525 |
| test226 | `test_226_handshake_accept_receives_first` | TEST226: Test decode_frame rejects CBOR map missing required version field | tests/test_cbor_io.py:555 |
| test227 | `test_227_handshake_fails_if_cartridge_missing_manifest` | TEST227: Test decode_frame rejects CBOR map with invalid frame_type value | tests/test_cbor_io.py:586 |
| test228 | `test_228_read_frame_enforces_limit` | TEST228: Test decode_frame rejects CBOR map missing required id field | tests/test_cbor_io.py:611 |
| test229 | `test_229_frame_with_zero_length_payload` | TEST229: Test FrameReader/FrameWriter set_limits updates the negotiated limits | tests/test_cbor_io.py:629 |
| test230 | `test_230_frame_roundtrip_preserves_fields` | TEST230: Test async handshake exchanges HELLO frames and negotiates minimum limits | tests/test_cbor_io.py:644 |
| test231 | `test_231_multiple_readers_on_same_stream` | TEST231: Test handshake fails when peer sends non-HELLO frame | tests/test_cbor_io.py:666 |
| test232 | `test_232_writer_flushes_after_each_frame` | TEST232: Test handshake fails when cartridge HELLO is missing required manifest | tests/test_cbor_io.py:691 |
| test233 | `test_233_frame_encoding_preserves_binary_data` | TEST233: Test binary payload with all 256 byte values roundtrips through encode/decode | tests/test_cbor_io.py:704 |
| test234 | `test_234_handshake_with_very_small_limits` | TEST234: Test decode_frame handles garbage CBOR bytes gracefully with an error | tests/test_cbor_io.py:717 |
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
| test248 | `test_248_register_and_find_handler` | TEST248: Test register_op and find_handler by exact cap URN | tests/test_cartridge_runtime.py:87 |
| test249 | `test_249_raw_handler` | TEST249: Test register_op handler echoes bytes directly | tests/test_cartridge_runtime.py:101 |
| test250 | `test_250_typed_handler_deserialization` | TEST250: Test Op handler collects input and processes it | tests/test_cartridge_runtime.py:132 |
| test251 | `test_251_typed_handler_rejects_invalid_json` | TEST251: Test Op handler propagates errors through RuntimeError::Handler | tests/test_cartridge_runtime.py:165 |
| test252 | `test_252_find_handler_unknown_cap` | TEST252: Test find_handler returns None for unregistered cap URNs | tests/test_cartridge_runtime.py:195 |
| test253 | `test_253_handler_is_send_sync` | TEST253: Test OpFactory can be cloned via Arc and sent across tasks (Send + Sync) | tests/test_cartridge_runtime.py:226 |
| test254 | `test_254_no_peer_invoker` | TEST254: Test NoPeerInvoker always returns PeerRequest error | tests/test_cartridge_runtime.py:257 |
| test255 | `test_255_no_peer_invoker_with_arguments` | TEST255: Test NoPeerInvoker call_with_bytes also returns error | tests/test_cartridge_runtime.py:267 |
| test256 | `test_256_with_manifest_json` | TEST256: Test CartridgeRuntime::with_manifest_json stores manifest data and parses when valid | tests/test_cartridge_runtime.py:276 |
| test257 | `test_257_new_with_invalid_json` | TEST257: Test CartridgeRuntime::new with invalid JSON still creates runtime (manifest is None) | tests/test_cartridge_runtime.py:287 |
| test258 | `test_258_with_manifest_struct` | TEST258: Test CartridgeRuntime::with_manifest creates runtime with valid manifest data | tests/test_cartridge_runtime.py:294 |
| test259 | `test_259_extract_effective_payload_non_cbor` | TEST259: Test extract_effective_payload with non-CBOR content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:303 |
| test260 | `test_260_extract_effective_payload_no_content_type` | TEST260: Test extract_effective_payload with None content_type returns raw payload unchanged | tests/test_cartridge_runtime.py:313 |
| test261 | `test_261_extract_effective_payload_cbor_match` | TEST261: Test extract_effective_payload with CBOR content extracts matching argument value | tests/test_cartridge_runtime.py:322 |
| test262 | `test_262_extract_effective_payload_cbor_no_match` | TEST262: Test extract_effective_payload with CBOR content fails when no argument matches expected input | tests/test_cartridge_runtime.py:339 |
| test263 | `test_263_extract_effective_payload_invalid_cbor` | TEST263: Test extract_effective_payload with invalid CBOR bytes returns deserialization error | tests/test_cartridge_runtime.py:364 |
| test264 | `test_264_extract_effective_payload_cbor_not_array` | TEST264: Test extract_effective_payload with CBOR non-array (e.g. map) returns error | tests/test_cartridge_runtime.py:376 |
| test266 | `test_266_cli_stream_emitter_construction` | TEST266: Test CliFrameSender wraps CliStreamEmitter correctly (basic construction) | tests/test_cartridge_runtime.py:403 |
| test268 | `test_268_runtime_error_display` | TEST268: Test RuntimeError variants display correct messages | tests/test_cartridge_runtime.py:412 |
| test270 | `test_270_multiple_handlers` | TEST270: Test registering multiple Op handlers for different caps and finding each independently | tests/test_cartridge_runtime.py:433 |
| test271 | `test_271_handler_replacement` | TEST271: Test Op handler replacing an existing registration for the same cap URN | tests/test_cartridge_runtime.py:460 |
| test272 | `test_272_extract_effective_payload_multiple_args` | TEST272: Test extract_effective_payload CBOR with multiple arguments selects the correct one | tests/test_cartridge_runtime.py:491 |
| test273 | `test_273_extract_effective_payload_binary_value` | TEST273: Test extract_effective_payload with binary data in CBOR value (not just text) | tests/test_cartridge_runtime.py:514 |
| test274 | `test_274_cap_argument_value_new` | TEST274: Test CapArgumentValue::new stores media_urn and raw byte value | tests/test_caller.py:145 |
| test275 | `test_275_cap_argument_value_from_str` | TEST275: Test CapArgumentValue::from_str converts string to UTF-8 bytes | tests/test_caller.py:156 |
| test276 | `test_276_cap_argument_value_as_str_success` | TEST276: Test CapArgumentValue::value_as_str succeeds for UTF-8 data | tests/test_caller.py:168 |
| test277 | `test_277_cap_argument_value_as_str_fails_binary` | TEST277: Test CapArgumentValue::value_as_str fails for non-UTF-8 binary data | tests/test_caller.py:174 |
| test278 | `test_278_cap_argument_value_empty` | TEST278: Test CapArgumentValue::new with empty value stores empty vec | tests/test_caller.py:184 |
| test279 | `test_279_cap_argument_value_clone` | TEST279: Test CapArgumentValue Clone produces independent copy with same data | tests/test_caller.py:192 |
| test280 | `test_280_cap_argument_value_debug` | TEST280: Test CapArgumentValue Debug format includes media_urn and value | tests/test_caller.py:207 |
| test281 | `test_281_cap_argument_value_media_urn_types` | TEST281: Test CapArgumentValue::new accepts Into<String> for media_urn (String and &str) | tests/test_caller.py:225 |
| test282 | `test_282_cap_argument_value_unicode` | TEST282: Test CapArgumentValue::from_str with Unicode string preserves all characters | tests/test_caller.py:238 |
| test283 | `test_283_cap_argument_value_large_binary` | TEST283: Test CapArgumentValue with large binary payload preserves all bytes | tests/test_caller.py:248 |
| test284 | `test_284_handshake_host_cartridge` | TEST284: Handshake exchanges HELLO frames, negotiates limits | tests/test_cbor_integration.py:52 |
| test285 | `test_285_request_response_simple` | TEST285: Simple request-response flow (REQ → END with payload) | tests/test_cbor_integration.py:87 |
| test286 | `test_286_streaming_chunks` | TEST286: Streaming response with multiple CHUNK frames | tests/test_cbor_integration.py:127 |
| test287 | `test_287_heartbeat_from_host` | TEST287: Host-initiated heartbeat | tests/test_cbor_integration.py:179 |
| test290 | `test_290_limits_negotiation` | TEST290: Limit negotiation picks minimum | tests/test_cbor_integration.py:217 |
| test291 | `test_291_binary_payload_roundtrip` | TEST291: Binary payload roundtrip (all 256 byte values) | tests/test_cbor_integration.py:249 |
| test292 | `test_292_message_id_uniqueness` | TEST292: Sequential requests get distinct MessageIds | tests/test_cbor_integration.py:294 |
| test293 | `test_293_cartridge_runtime_handler_registration` | TEST293: Test CartridgeRuntime Op registration and lookup by exact and non-existent cap URN | tests/test_cartridge_runtime.py:201 |
| test299 | `test_299_empty_payload_roundtrip` | TEST299: Empty payload request/response roundtrip | tests/test_cbor_integration.py:335 |
| test304 | `test_304_media_availability_output_constant` | TEST304: Test MEDIA_AVAILABILITY_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:257 |
| test305 | `test_305_media_path_output_constant` | TEST305: Test MEDIA_PATH_OUTPUT constant parses as valid media URN with correct tags | tests/test_media_urn.py:265 |
| test306 | `test_306_availability_and_path_output_distinct` | TEST306: Test MEDIA_AVAILABILITY_OUTPUT and MEDIA_PATH_OUTPUT are distinct URNs | tests/test_media_urn.py:273 |
| test307 | `test_307_model_availability_urn` | TEST307: Test model_availability_urn builds valid cap URN with correct op and media specs | tests/test_standard_caps.py:27 |
| test308 | `test_308_model_path_urn` | TEST308: Test model_path_urn builds valid cap URN with correct op and media specs | tests/test_standard_caps.py:35 |
| test309 | `test_309_model_availability_and_path_are_distinct` | TEST309: Test model_availability_urn and model_path_urn produce distinct URNs | tests/test_standard_caps.py:43 |
| test310 | `test_310_llm_generate_text_urn_tags` |  | tests/test_standard_caps.py:49 |
| test312 | `test_312_all_urn_builders_produce_valid_urns` | TEST312: Test all URN builders produce parseable cap URNs | tests/test_standard_caps.py:71 |
| test320 | `test_320_construct_cartridge_info_and_verify_fields` | TEST320: Construct CartridgeInfo and verify fields | tests/test_cartridge_repo.py:19 |
| test321 | `test_321_cartridge_info_is_signed` | TEST321: Verify is_signed() method | tests/test_cartridge_repo.py:60 |
| test322 | `test_322_cartridge_info_build_for_platform` | TEST322: Verify build_for_platform() method | tests/test_cartridge_repo.py:80 |
| test323 | `test_323_cartridge_repo_server_validate_registry` | TEST323: Validate registry schema version | tests/test_cartridge_repo.py:169 |
| test324 | `test_324_cartridge_repo_server_transform_to_array` | TEST324: Transform v3 registry to flat cartridge array | tests/test_cartridge_repo.py:190 |
| test325 | `test_325_cartridge_repo_server_get_cartridges` | TEST325: Get all cartridges via get_cartridges() | tests/test_cartridge_repo.py:230 |
| test326 | `test_326_cartridge_repo_server_get_cartridge_by_id` | TEST326: Get cartridge by ID | tests/test_cartridge_repo.py:244 |
| test327 | `test_327_cartridge_repo_server_search_cartridges` | TEST327: Search cartridges by text query | tests/test_cartridge_repo.py:260 |
| test328 | `test_328_cartridge_repo_server_get_by_category` | TEST328: Filter cartridges by category | tests/test_cartridge_repo.py:282 |
| test329 | `test_329_cartridge_repo_server_get_by_cap` | TEST329: Find cartridges by cap URN | tests/test_cartridge_repo.py:304 |
| test330 | `test_330_cartridge_repo_client_update_cache` | TEST330: CartridgeRepoClient cache update | tests/test_cartridge_repo.py:333 |
| test331 | `test_331_cartridge_repo_client_get_suggestions` | TEST331: Get suggestions for missing cap | tests/test_cartridge_repo.py:355 |
| test332 | `test_332_cartridge_repo_client_get_cartridge` | TEST332: Get cartridge by ID from client | tests/test_cartridge_repo.py:388 |
| test333 | `test_333_cartridge_repo_client_get_all_caps` | TEST333: Get all available caps | tests/test_cartridge_repo.py:404 |
| test334 | `test_334_cartridge_repo_client_needs_sync` | TEST334: Check if client needs sync | tests/test_cartridge_repo.py:435 |
| test335 | `test_335_cartridge_repo_server_client_integration` | TEST335: Server creates response, client consumes it | tests/test_cartridge_repo.py:446 |
| test336 | `test_336_file_path_reads_file_passes_bytes` | TEST336: Single file-path arg with stdin source reads file and passes bytes to handler | tests/test_cartridge_runtime.py:556 |
| test337 | `test_337_file_path_without_stdin_passes_string` | TEST337: file-path arg without stdin source passes path as string (no conversion) | tests/test_cartridge_runtime.py:624 |
| test338 | `test_338_file_path_via_cli_flag` | TEST338: file-path arg reads file via --file CLI flag | tests/test_cartridge_runtime.py:654 |
| test339 | `test_339_file_path_array_glob_expansion` | TEST339: file-path-array reads multiple files with glob pattern | tests/test_cartridge_runtime.py:685 |
| test340 | `test_340_file_not_found_clear_error` | TEST340: File not found error provides clear message | tests/test_cartridge_runtime.py:732 |
| test341 | `test_341_stdin_precedence_over_file_path` | TEST341: stdin takes precedence over file-path in source order | tests/test_cartridge_runtime.py:765 |
| test342 | `test_342_file_path_position_zero_reads_first_arg` | TEST342: file-path with position 0 reads first positional arg as file | tests/test_cartridge_runtime.py:800 |
| test343 | `test_343_non_file_path_args_unaffected` | TEST343: Non-file-path args are not affected by file reading | tests/test_cartridge_runtime.py:832 |
| test344 | `test_344_file_path_array_invalid_json_fails` | TEST344: file-path-array with nonexistent path fails clearly | tests/test_cartridge_runtime.py:863 |
| test345 | `test_345_file_path_array_one_file_missing_fails_hard` | TEST345: file-path-array with literal nonexistent path fails hard | tests/test_cartridge_runtime.py:897 |
| test346 | `test_346_large_file_reads_successfully` | TEST346: Large file (1MB) reads successfully | tests/test_cartridge_runtime.py:940 |
| test347 | `test_347_empty_file_reads_as_empty_bytes` | TEST347: Empty file reads as empty bytes | tests/test_cartridge_runtime.py:975 |
| test348 | `test_348_file_path_conversion_respects_source_order` | TEST348: file-path conversion respects source order | tests/test_cartridge_runtime.py:1006 |
| test349 | `test_349_file_path_multiple_sources_fallback` | TEST349: file-path arg with multiple sources tries all in order | tests/test_cartridge_runtime.py:1041 |
| test350 | `test_350_full_cli_mode_with_file_path_integration` | TEST350: Integration test - full CLI mode invocation with file-path | tests/test_cartridge_runtime.py:1074 |
| test351 | `test_351_file_path_array_empty_array` | TEST351: file-path array with empty CBOR array returns empty (CBOR mode) | tests/test_cartridge_runtime.py:1146 |
| test352 | `test_352_file_permission_denied_clear_error` | TEST352: file permission denied error is clear (Unix-specific) | tests/test_cartridge_runtime.py:1178 |
| test353 | `test_353_cbor_payload_format_consistency` | TEST353: CBOR payload format matches between CLI and CBOR mode | tests/test_cartridge_runtime.py:1221 |
| test354 | `test_354_glob_pattern_no_matches_empty_array` | TEST354: Glob pattern with no matches fails hard (NO FALLBACK) | tests/test_cartridge_runtime.py:1255 |
| test355 | `test_355_glob_pattern_skips_directories` | TEST355: Glob pattern skips directories | tests/test_cartridge_runtime.py:1290 |
| test356 | `test_356_multiple_glob_patterns_combined` | TEST356: Multiple glob patterns combined | tests/test_cartridge_runtime.py:1336 |
| test357 | `test_357_symlinks_followed` | TEST357: Symlinks are followed when reading files | tests/test_cartridge_runtime.py:1385 |
| test358 | `test_358_binary_file_non_utf8` | TEST358: Binary file with non-UTF8 data reads correctly | tests/test_cartridge_runtime.py:1422 |
| test359 | `test_359_invalid_glob_pattern_fails` | TEST359: Invalid glob pattern fails with clear error | tests/test_cartridge_runtime.py:1456 |
| test360 | `test_360_extract_effective_payload_with_file_data` | TEST360: Extract effective payload handles file-path data correctly | tests/test_cartridge_runtime.py:1492 |
| test361 | `test_361_cli_mode_file_path` | TEST361: CLI mode with file path - pass file path as command-line argument | tests/test_cartridge_runtime.py:1534 |
| test362 | `test_362_cli_mode_piped_binary` | TEST362: CLI mode with binary piped in - pipe binary data via stdin This test simulates real-world conditions: - Pure binary data piped to stdin (NOT CBOR) - CLI mode detected (command arg present) - Cap accepts stdin source - Binary is chunked on-the-fly and accumulated - Handler receives complete CBOR payload | tests/test_cartridge_runtime.py:1578 |
| test363 | `test_363_cbor_mode_chunked_content` | TEST363: CBOR mode with chunked content - send file content streaming as chunks | tests/test_cartridge_runtime.py:1625 |
| test364 | `test_364_cbor_mode_file_path` | TEST364: CBOR mode with file path - send file path in CBOR arguments (auto-conversion) | tests/test_cartridge_runtime.py:1711 |
| test365 | `test_365_stream_start_frame` | TEST365: Frame::stream_start stores request_id, stream_id, and media_urn | tests/test_cbor_frame.py:422 |
| test366 | `test_366_stream_end_frame` | TEST366: Frame::stream_end stores request_id and stream_id | tests/test_cbor_frame.py:437 |
| test367 | `test_367_stream_start_with_empty_stream_id` | TEST367: StreamStart frame with empty stream_id still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:453 |
| test368 | `test_368_stream_start_with_empty_media_urn` | TEST368: StreamStart frame with empty media_urn still constructs (validation happens elsewhere) | tests/test_cbor_frame.py:464 |
| test389 | `test_389_stream_start_roundtrip` | TEST389: StreamStart encode/decode roundtrip preserves stream_id and media_urn | tests/test_cbor_io.py:882 |
| test390 | `test_390_stream_end_roundtrip` | TEST390: StreamEnd encode/decode roundtrip preserves stream_id, no media_urn | tests/test_cbor_io.py:898 |
| test395 | `test_395_build_payload_small` | TEST395: Small payload (< max_chunk) produces correct CBOR arguments | tests/test_cartridge_runtime.py:1746 |
| test396 | `test_396_build_payload_large` | TEST396: Large payload (> max_chunk) accumulates across chunks correctly | tests/test_cartridge_runtime.py:1778 |
| test397 | `test_397_build_payload_empty` | TEST397: Empty reader produces valid empty CBOR arguments | tests/test_cartridge_runtime.py:1805 |
| test398 | `test_398_build_payload_io_error` | TEST398: IO error from reader propagates as RuntimeError::Io | tests/test_cartridge_runtime.py:1836 |
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
| test413 | `test_413_register_cartridge_adds_cap_table` | TEST413: Register cartridge adds entries to cap_table | tests/test_cartridge_host.py:308 |
| test414 | `test_414_capabilities_empty_initially` | TEST414: capabilities() returns empty JSON initially (no running cartridges) | tests/test_cartridge_host.py:323 |
| test415 | `test_415_req_triggers_spawn` | TEST415: REQ for known cap triggers spawn attempt (verified by expected spawn error for non-existent binary) | tests/test_cartridge_host.py:331 |
| test416 | `test_416_attach_cartridge_handshake` | TEST416: Attach cartridge performs HELLO handshake, extracts manifest, updates capabilities | tests/test_cartridge_host.py:361 |
| test417 | `test_417_route_req_by_cap_urn` | TEST417: Route REQ to correct cartridge by cap_urn (with two attached cartridges) | tests/test_cartridge_host.py:388 |
| test418 | `test_418_route_continuation_by_req_id` | TEST418: Route STREAM_START/CHUNK/STREAM_END/END by req_id (not cap_urn) Verifies that after the initial REQ→cartridge routing, all subsequent continuation frames with the same req_id are routed to the same cartridge — even though no cap_urn is present on those frames. | tests/test_cartridge_host.py:449 |
| test419 | `test_419_heartbeat_local_handling` | TEST419: Cartridge HEARTBEAT handled locally (not forwarded to relay) | tests/test_cartridge_host.py:508 |
| test420 | `test_420_cartridge_frames_forwarded_to_relay` | TEST420: Cartridge non-HELLO/non-HB frames forwarded to relay (pass-through) | tests/test_cartridge_host.py:570 |
| test421 | `test_421_cartridge_death_updates_caps` | TEST421: Cartridge death updates capability list (caps removed) | tests/test_cartridge_host.py:628 |
| test422 | `test_422_cartridge_death_sends_err` | TEST422: Cartridge death sends ERR for all pending requests via relay | tests/test_cartridge_host.py:669 |
| test423 | `test_423_multi_cartridge_distinct_caps` | TEST423: Multiple cartridges registered with distinct caps route independently | tests/test_cartridge_host.py:717 |
| test424 | `test_424_concurrent_requests_same_cartridge` | TEST424: Concurrent requests to the same cartridge are handled independently | tests/test_cartridge_host.py:798 |
| test425 | `test_425_find_cartridge_for_cap_unknown` | TEST425: find_cartridge_for_cap returns None for unregistered cap | tests/test_cartridge_host.py:865 |
| test426 | `test_426_single_master_req_response` | TEST426: Single master REQ/response routing | tests/test_relay_switch.py:70 |
| test427 | `test_427_multi_master_cap_routing` | TEST427: Multi-master cap routing | tests/test_relay_switch.py:120 |
| test428 | `test_428_unknown_cap_returns_error` | TEST428: Unknown cap returns error | tests/test_relay_switch.py:204 |
| test429 | `test_429_find_master_for_cap` | TEST429: Cap routing logic (find_master_for_cap) | tests/test_relay_switch.py:239 |
| test430 | `test_430_tie_breaking_same_cap_multiple_masters` | TEST430: Tie-breaking (same cap on multiple masters - first match wins, routing is consistent) | tests/test_relay_switch.py:411 |
| test431 | `test_431_continuation_frame_routing` | TEST431: Continuation frame routing (CHUNK, END follow REQ) | tests/test_relay_switch.py:487 |
| test432 | `test_432_empty_masters_list_error` | TEST432: Empty masters list creates empty switch, add_master works | tests/test_relay_switch.py:549 |
| test433 | `test_433_capability_aggregation_deduplicates` | TEST433: Capability aggregation deduplicates caps | tests/test_relay_switch.py:557 |
| test434 | `test_434_limits_negotiation_minimum` | TEST434: Limits negotiation takes minimum | tests/test_relay_switch.py:613 |
| test435 | `test_435_urn_matching_exact_and_accepts` | TEST435: URN matching (exact vs accepts()) | tests/test_relay_switch.py:658 |
| test436 | `test_436_compute_checksum` | TEST436: Verify FNV-1a checksum function produces consistent results | tests/test_cbor_frame.py:567 |
| test437 | `test_437_preferred_cap_routes_to_generic` | TEST437: find_master_for_cap with preferred_cap routes to generic handler With is_dispatchable semantics: - Generic provider (in=media:) CAN dispatch specific request (in="media:pdf") because media: (wildcard) accepts any input type - Preference routes to preferred among dispatchable candidates | tests/test_relay_switch.py:290 |
| test438 | `test_438_preferred_cap_falls_back_when_not_comparable` | TEST438: find_master_for_cap with preference falls back to closest-specificity when preferred cap is not in the comparable set | tests/test_relay_switch.py:330 |
| test439 | `test_439_generic_provider_can_dispatch_specific_request` | TEST439: Generic provider CAN dispatch specific request (but only matches if no more specific provider exists) With is_dispatchable: generic provider (in=media:) CAN handle specific request (in="media:pdf") because media: accepts any input type. With preference, can route to generic even when more specific exists. | tests/test_relay_switch.py:370 |
| test440 | `test_440_chunk_index_checksum_roundtrip` | TEST440: CHUNK frame with chunk_index and checksum roundtrips through encode/decode | tests/test_cbor_io.py:947 |
| test441 | `test_441_stream_end_chunk_count_roundtrip` | TEST441: STREAM_END frame with chunk_count roundtrips through encode/decode | tests/test_cbor_io.py:967 |
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
| test461 | `test_461_write_chunked_seq_zero` | TEST461: write_chunked produces frames with seq=0; SeqAssigner assigns at output stage | tests/test_cbor_io.py:340 |
| test472 | `test_472_handshake_negotiates_reorder_buffer` | TEST472: Handshake negotiates max_reorder_buffer (minimum of both sides) | tests/test_cbor_io.py:367 |
| test473 | `test_473_cap_discard_parses_as_valid_urn` | TEST473: CAP_DISCARD parses as valid CapUrn with in=media: and out=media:void | tests/test_standard_caps.py:91 |
| test474 | `test_474_cap_discard_accepts_specific_void_cap` | TEST474: CAP_DISCARD accepts specific-input/void-output caps | tests/test_standard_caps.py:98 |
| test475 | `test_475_validate_passes_with_identity` | TEST475: CapManifest::validate() passes when CAP_IDENTITY is present | tests/test_manifest.py:203 |
| test476 | `test_476_validate_fails_without_identity` | TEST476: CapManifest::validate() fails when CAP_IDENTITY is missing | tests/test_manifest.py:214 |
| test478 | `test_478_auto_registers_identity_and_discard_handlers` | TEST478: CartridgeRuntime auto-registers identity and discard handlers on construction | tests/test_cartridge_runtime.py:1857 |
| test479 | `test_479_custom_identity_overrides_default` | TEST479: Custom identity Op overrides auto-registered default | tests/test_cartridge_runtime.py:1866 |
| test480 | `test_480_parse_caps_rejects_manifest_without_identity` | TEST480: parse_caps_from_manifest rejects manifest without CAP_IDENTITY | tests/test_cartridge_host.py:119 |
| test481 | `test_481_verify_identity_succeeds` | TEST481: verify_identity succeeds with standard identity echo handler | tests/test_cbor_io.py:395 |
| test482 | `test_482_verify_identity_fails_on_err` | TEST482: verify_identity fails when cartridge returns ERR on identity call | tests/test_cbor_io.py:433 |
| test483 | `test_483_verify_identity_fails_on_close` | TEST483: verify_identity fails when connection closes before response | tests/test_cbor_io.py:462 |
| test485 | `test_485_attach_cartridge_identity_verification_succeeds` | TEST485: attach_cartridge completes identity verification with working cartridge | tests/test_cartridge_host.py:129 |
| test486 | `test_486_attach_cartridge_identity_verification_fails` | TEST486: attach_cartridge rejects cartridge that fails identity verification | tests/test_cartridge_host.py:150 |
| test487 | `test_487_relay_switch_identity_verification_succeeds` | TEST487: RelaySwitch construction verifies identity through relay chain | tests/test_relay_switch.py:712 |
| test488 | `test_488_relay_switch_identity_verification_fails` | TEST488: RelaySwitch construction fails when master's identity verification fails | tests/test_relay_switch.py:729 |
| test489 | `test_489_full_path_identity_verification` | TEST489: Full path identity verification: engine → host (attach_cartridge) → cartridge | tests/test_cartridge_host.py:177 |
| test490 | `test_490_identity_verification_multiple_cartridges` | TEST490: Identity verification with multiple cartridges through single relay | tests/test_cartridge_host.py:228 |
| test491 | `test_491_chunk_requires_chunk_index_and_checksum` | TEST491: Frame::chunk constructor requires and sets chunk_index and checksum | tests/test_cbor_frame.py:958 |
| test492 | `test_492_stream_end_requires_chunk_count` | TEST492: Frame::stream_end constructor requires and sets chunk_count | tests/test_cbor_frame.py:972 |
| test493 | `test_493_compute_checksum_fnv1a_test_vectors` | TEST493: compute_checksum produces correct FNV-1a hash for known test vectors | tests/test_cbor_frame.py:982 |
| test494 | `test_494_compute_checksum_deterministic` | TEST494: compute_checksum is deterministic | tests/test_cbor_frame.py:989 |
| test495 | `test_495_cbor_rejects_chunk_without_chunk_index` | TEST495: CBOR decode REJECTS CHUNK frame missing chunk_index field | tests/test_cbor_frame.py:999 |
| test496 | `test_496_cbor_rejects_chunk_without_checksum` | TEST496: CBOR decode REJECTS CHUNK frame missing checksum field | tests/test_cbor_frame.py:1018 |
| test497 | `test_497_chunk_corrupted_payload_rejected` | TEST497: Verify CHUNK frame with corrupted payload is rejected by checksum | tests/test_cbor_io.py:982 |
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
| test529 | `test_529_input_stream_recv_order` | TEST529: InputStream recv yields chunks in order | tests/test_cartridge_runtime.py:1948 |
| test530 | `test_530_input_stream_collect_bytes` | TEST530: InputStream::collect_bytes concatenates byte chunks | tests/test_cartridge_runtime.py:1962 |
| test531 | `test_531_input_stream_collect_bytes_text` | TEST531: InputStream::collect_bytes handles text chunks | tests/test_cartridge_runtime.py:1968 |
| test532 | `test_532_input_stream_empty` | TEST532: InputStream empty stream produces empty bytes | tests/test_cartridge_runtime.py:1974 |
| test533 | `test_533_input_stream_error_propagation` | TEST533: InputStream propagates errors | tests/test_cartridge_runtime.py:1980 |
| test534 | `test_534_input_stream_media_urn` | TEST534: InputStream::media_urn returns correct URN | tests/test_cartridge_runtime.py:1988 |
| test535 | `test_535_input_package_iteration` | TEST535: InputPackage recv yields streams | tests/test_cartridge_runtime.py:1994 |
| test536 | `test_536_input_package_collect_all_bytes` | TEST536: InputPackage::collect_all_bytes aggregates all streams | tests/test_cartridge_runtime.py:2019 |
| test537 | `test_537_input_package_empty` | TEST537: InputPackage empty package produces empty bytes | tests/test_cartridge_runtime.py:2030 |
| test538 | `test_538_input_package_error_propagation` | TEST538: InputPackage propagates stream errors | tests/test_cartridge_runtime.py:2036 |
| test539 | `test_539_output_stream_sends_stream_start` | TEST539: OutputStream sends STREAM_START on first write | tests/test_cartridge_runtime.py:2053 |
| test540 | `test_540_output_stream_close_sends_stream_end` | TEST540: OutputStream::close sends STREAM_END with correct chunk_count | tests/test_cartridge_runtime.py:2073 |
| test541 | `test_541_output_stream_chunks_large_data` | TEST541: OutputStream chunks large data correctly | tests/test_cartridge_runtime.py:2095 |
| test542 | `test_542_output_stream_empty` | TEST542: OutputStream empty stream sends STREAM_START and STREAM_END only | tests/test_cartridge_runtime.py:2115 |
| test543 | `test_543_peer_call_arg_creates_stream` | TEST543: PeerCall::arg creates OutputStream with correct stream_id | tests/test_cartridge_runtime.py:2135 |
| test544 | `test_544_peer_invoker_sends_end_frame` | TEST544: PeerCall::finish sends END frame | tests/test_cartridge_runtime.py:2150 |
| test545 | `test_545_peer_response_returns_data` | TEST545: PeerCall::finish returns PeerResponse with data | tests/test_cartridge_runtime.py:2175 |
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
| test578 | `test_578_rule1_duplicate_media_urns` | TEST578: RULE1 - duplicate media_urns rejected | tests/test_validation.py:169 |
| test579 | `test_579_rule2_empty_sources` | TEST579: RULE2 - empty sources rejected | tests/test_validation.py:182 |
| test580 | `test_580_rule3_different_stdin_urns` | TEST580: RULE3 - multiple stdin sources with different URNs rejected | tests/test_validation.py:194 |
| test581 | `test_581_rule3_same_stdin_urns_ok` | TEST581: RULE3 - multiple stdin sources with same URN is OK | tests/test_validation.py:207 |
| test582 | `test_582_rule4_duplicate_source_type` | TEST582: RULE4 - duplicate source type in single arg rejected | tests/test_validation.py:218 |
| test583 | `test_583_rule5_duplicate_position` | TEST583: RULE5 - duplicate position across args rejected | tests/test_validation.py:230 |
| test584 | `test_584_rule6_position_gap` | TEST584: RULE6 - position gap rejected (0, 2 without 1) | tests/test_validation.py:243 |
| test585 | `test_585_rule6_sequential_ok` | TEST585: RULE6 - sequential positions (0, 1, 2) pass | tests/test_validation.py:256 |
| test586 | `test_586_rule7_position_and_cli_flag` | TEST586: RULE7 - arg with both position and cli_flag rejected | tests/test_validation.py:267 |
| test587 | `test_587_rule9_duplicate_cli_flag` | TEST587: RULE9 - duplicate cli_flag across args rejected | tests/test_validation.py:279 |
| test588 | `test_588_rule10_reserved_cli_flags` | TEST588: RULE10 - reserved cli_flags rejected | tests/test_validation.py:292 |
| test589 | `test_589_all_rules_pass` | TEST589: valid cap args with mixed sources pass all rules | tests/test_validation.py:306 |
| test590 | `test_590_cli_flag_only_args` | TEST590: validate_cap_args accepts cap with only cli_flag sources (no positions) | tests/test_validation.py:317 |
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
| test605 | `test_605_all_coercion_paths_build_valid_urns` | TEST605: all_coercion_paths each entry builds a valid parseable CapUrn | tests/test_standard_caps.py:114 |
| test606 | `test_606_coercion_urn_specs` | TEST606: coercion_urn in/out specs match the type's media URN constant | tests/test_standard_caps.py:131 |
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
| test630 | `test_630_cartridge_repo_creation` | TEST630: Verify CartridgeRepo creation starts with empty cartridge list | tests/test_cartridge_repo.py:480 |
| test631 | `test_631_needs_sync_empty_cache` | TEST631: Verify needs_sync returns true with empty cache and non-empty URLs | tests/test_cartridge_repo.py:486 |
| test632 | `test_632_deserialize_cap_summary_with_null_description` | TEST632: Verify CartridgeCapSummary deserializes null description as empty string | tests/test_cartridge_repo.py:492 |
| test633 | `test_633_deserialize_cap_summary_with_missing_description` | TEST633: Verify CartridgeCapSummary deserializes missing description as empty string | tests/test_cartridge_repo.py:506 |
| test634 | `test_634_deserialize_cap_summary_with_present_description` | TEST634: Verify CartridgeCapSummary deserializes present description correctly | tests/test_cartridge_repo.py:517 |
| test635 | `test_635_deserialize_cartridge_info_with_null_fields` | TEST635: Verify CartridgeInfo deserializes null version/description/author as empty strings | tests/test_cartridge_repo.py:529 |
| test636 | `test_636_deserialize_registry_with_null_descriptions` | TEST636: Verify CartridgeRegistryResponse deserializes with mixed null/present descriptions | tests/test_cartridge_repo.py:553 |
| test637 | `test_637_deserialize_full_cartridge_with_signature` | TEST637: Verify full CartridgeInfo deserialization with signature and package fields | tests/test_cartridge_repo.py:582 |
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
| test661 | `test_661_cartridge_death_keeps_known_caps_advertised` | TEST661: Cartridge death keeps known_caps advertised for on-demand respawn | tests/test_cartridge_host.py:878 |
| test662 | `test_662_rebuild_capabilities_includes_non_running_cartridges` | TEST662: rebuild_capabilities includes non-running cartridges' known_caps | tests/test_cartridge_host.py:903 |
| test663 | `test_663_hello_failed_cartridge_removed_from_capabilities` | TEST663: Cartridge with hello_failed is permanently removed from capabilities | tests/test_cartridge_host.py:918 |
| test664 | `test_664_running_cartridge_uses_manifest_caps` | TEST664: Running cartridge uses manifest caps, not known_caps | tests/test_cartridge_host.py:936 |
| test665 | `test_665_cap_table_mixed_running_and_non_running` | TEST665: Cap table uses manifest caps for running, known_caps for non-running | tests/test_cartridge_host.py:957 |
| test666 | `test_666_preferred_cap_routing` | TEST666: Preferred cap routing - routes to exact equivalent when multiple masters match | tests/test_relay_switch.py:751 |
| test667 | `test_667_verify_chunk_checksum_detects_corruption` | TEST667: verify_chunk_checksum detects corrupted payload | tests/test_cbor_frame.py:538 |
| test668 | `test_668_resolve_slot_with_populated_byte_slot_values` | TEST668: resolve_slot_with_populated_byte_slot_values | tests/test_planner_argument_binding.py:37 |
| test669 | `test_669_resolve_slot_falls_back_to_default` | TEST669: resolve_slot_falls_back_to_default | tests/test_planner_argument_binding.py:54 |
| test670 | `test_670_resolve_required_slot_no_value_returns_err` | TEST670: resolve_required_slot_no_value_returns_err | tests/test_planner_argument_binding.py:63 |
| test671 | `test_671_resolve_optional_slot_no_value_returns_none` | TEST671: resolve_optional_slot_no_value_returns_none | tests/test_planner_argument_binding.py:71 |
| test675 | `test_675_build_request_frames_preserves_media_urn_in_stream_start` | TEST675: build_request_frames with full media URN preserves it in STREAM_START frame | tests/test_caller.py:288 |
| test676 | `test_676_build_request_frames_round_trip_find_stream_succeeds` | TEST676: Full round-trip: build_request_frames → extract streams → find_stream succeeds | tests/test_caller.py:300 |
| test677 | `test_677_base_urn_does_not_match_full_urn_in_find_stream` | TEST677: build_request_frames with BASE URN → find_stream with FULL URN FAILS This documents the root cause of the cartridge_client.rs bug: sender used "media:llm-generation-request" (base), receiver looked for "media:llm-generation-request;json;record" (full). is_equivalent requires exact tag set match, so base != full. | tests/test_caller.py:314 |
| test678 | `test_678_find_stream_equivalent_urn` | TEST678: find_stream with exact equivalent URN (same tags, different order) succeeds | tests/test_cartridge_runtime.py:2312 |
| test679 | `test_679_find_stream_base_vs_full_fails` | TEST679: find_stream with base URN vs full URN fails — is_equivalent is strict This is the root cause of the cartridge_client.rs bug. Sender sent "media:llm-generation-request" but receiver looked for "media:llm-generation-request;json;record". | tests/test_cartridge_runtime.py:2321 |
| test680 | `test_680_require_stream_missing_fails` | TEST680: require_stream with missing URN returns hard StreamError | tests/test_cartridge_runtime.py:2330 |
| test681 | `test_681_find_stream_multiple` | TEST681: find_stream with multiple streams returns the correct one | tests/test_cartridge_runtime.py:2340 |
| test682 | `test_682_require_stream_returns_data` | TEST682: require_stream_str returns UTF-8 string for text data | tests/test_cartridge_runtime.py:2352 |
| test683 | `test_683_find_stream_invalid_urn_returns_none` | TEST683: find_stream returns None for invalid media URN string (not a parse error — just None) | tests/test_cartridge_runtime.py:2361 |
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
| test771 | `test_771_rejects_collect` | TEST771: plan_to_resolved_graph rejects plans containing Collect nodes | tests/test_orchestrator_plan_converter.py:73 |
| test772 | `test_772_find_paths_finds_multi_step_paths` | TEST772: Tests find_paths_to_exact_target() finds multi-step paths Verifies that paths through intermediate nodes are found correctly | tests/test_live_cap_graph.py:49 |
| test773 | `test_773_find_paths_returns_empty_when_no_path` | TEST773: Tests find_paths_to_exact_target() returns empty when no path exists Verifies that pathfinding returns no paths when target is unreachable | tests/test_live_cap_graph.py:63 |
| test774 | `test_774_get_reachable_targets_finds_all_targets` | TEST774: Tests get_reachable_targets() returns all reachable targets Verifies that reachable targets include direct cap targets and cardinality variants (list versions via Collect) | tests/test_live_cap_graph.py:73 |
| test777 | `test_777_type_mismatch_pdf_cap_does_not_match_png_input` | TEST777: Tests type checking prevents using PDF-specific cap with PNG input Verifies that media type compatibility is enforced during pathfinding | tests/test_live_cap_graph.py:84 |
| test778 | `test_778_type_mismatch_png_cap_does_not_match_pdf_input` | TEST778: Tests type checking prevents using PNG-specific cap with PDF input Verifies that media type compatibility is enforced during pathfinding | tests/test_live_cap_graph.py:100 |
| test779 | `test_779_get_reachable_targets_respects_type_matching` | TEST779: Tests get_reachable_targets() only returns targets reachable via type-compatible caps Verifies that PNG and PDF inputs reach different cap targets (not each other's) | tests/test_live_cap_graph.py:116 |
| test780 | `test_780_split_integer_array` | TEST780: split_cbor_array splits a simple array of integers | tests/test_cbor_util.py:18 |
| test781 | `test_781_find_paths_respects_type_chain` | TEST781: Tests find_paths_to_exact_target() enforces type compatibility across multi-step chains Verifies that paths are only found when all intermediate types are compatible | tests/test_live_cap_graph.py:131 |
| test782 | `test_782_split_non_array` | TEST782: split_cbor_array rejects non-array input | tests/test_cbor_util.py:27 |
| test783 | `test_783_split_empty_array` | TEST783: split_cbor_array rejects empty array | tests/test_cbor_util.py:34 |
| test784 | `test_784_split_invalid_cbor` | TEST784: split_cbor_array rejects invalid CBOR bytes | tests/test_cbor_util.py:41 |
| test785 | `test_785_assemble_integer_array` | TEST785: assemble_cbor_array creates array from individual items | tests/test_cbor_util.py:47 |
| test786 | `test_786_roundtrip_split_assemble` | TEST786: split then assemble roundtrip preserves data | tests/test_cbor_util.py:54 |
| test787 | `test_787_find_paths_sorting_prefers_shorter` | TEST787: Tests find_paths_to_exact_target() sorts paths by length, preferring shorter ones Verifies that among multiple paths, the shortest is ranked first | tests/test_live_cap_graph.py:157 |
| test788 | `test_788_foreach_only_with_sequence_input` | TEST788: ForEach is only synthesized when is_sequence=true | tests/test_live_cap_graph.py:177 |
| test789 | `test_789_cap_from_json_has_valid_specs` | TEST789: Tests that caps loaded from JSON have correct in_spec/out_spec | tests/test_live_cap_graph.py:209 |
| test790 | `test_790_identity_urn_is_specific` | TEST790: Tests identity_urn is specific and doesn't match everything | tests/test_live_cap_graph.py:231 |
| test791 | `test_791_sync_from_cap_urns_adds_edges` | TEST791: Tests sync_from_cap_urns actually adds edges | tests/test_live_cap_graph.py:244 |
| test792 | `test_792_argument_binding_requires_input` | TEST792: Tests ArgumentBinding requires_input distinguishes Slots from Literals Verifies Slot returns true (needs user input) while Literal returns false | tests/test_planner_argument_binding.py:203 |
| test793 | `test_793_argument_binding_serialization` | TEST793: Tests ArgumentBinding PreviousOutput serializes/deserializes correctly Verifies JSON round-trip preserves node_id and output_field values | tests/test_planner_argument_binding.py:209 |
| test794 | `test_794_argument_bindings_add_file_path` | TEST794: Tests ArgumentBindings add_file_path adds InputFilePath binding Verifies add_file_path() creates binding map entry with InputFilePath variant | tests/test_planner_argument_binding.py:221 |
| test795 | `test_795_argument_bindings_unresolved_slots` | TEST795: Tests ArgumentBindings identifies unresolved Slot bindings Verifies has_unresolved_slots() and get_unresolved_slots() detect Slots needing values | tests/test_planner_argument_binding.py:229 |
| test796 | `test_796_resolve_input_file_path` | TEST796: Tests resolve_binding resolves InputFilePath to current file path Verifies InputFilePath binding resolves to file path bytes with InputFile source | tests/test_planner_argument_binding.py:238 |
| test797 | `test_797_resolve_literal` | TEST797: Tests resolve_binding resolves Literal to JSON-encoded bytes Verifies Literal binding serializes value to bytes with Literal source | tests/test_planner_argument_binding.py:255 |
| test798 | `test_798_resolve_previous_output` | TEST798: Tests resolve_binding extracts value from previous node output Verifies PreviousOutput binding fetches field from earlier execution results | tests/test_planner_argument_binding.py:270 |
| test799 | `test_799_machine_input_single` | TEST799: Tests StrandInput single constructor creates valid Single cardinality input Verifies single() wraps one file with Single cardinality and validates correctly | tests/test_planner_argument_binding.py:286 |
| test800 | `test_800_machine_input_vector` | TEST800: Tests StrandInput sequence constructor creates valid Sequence cardinality input Verifies sequence() wraps multiple files with Sequence cardinality | tests/test_planner_argument_binding.py:295 |
| test801 | `test_801_cap_input_file_deserialization_from_dry_context` | TEST801: Tests CapInputFile deserializes from JSON with source metadata fields Verifies JSON with source_id and source_type deserializes to CapInputFile correctly | tests/test_planner_argument_binding.py:307 |
| test802 | `test_802_cap_input_file_deserialization_via_value` | TEST802: Tests CapInputFile deserializes from compact JSON via serde_json::Value Verifies deserialization through Value intermediate works correctly | tests/test_planner_argument_binding.py:322 |
| test803 | `test_803_machine_input_invalid_single` | TEST803: Tests StrandInput validation detects mismatched Single cardinality with multiple files Verifies is_valid() returns false when Single cardinality has more than one file | tests/test_planner_argument_binding.py:332 |
| test804 | `test_804_extract_json_path_simple` | TEST804: Tests basic JSON path extraction with dot notation for nested objects Verifies that simple paths like "data.message" correctly extract values from nested JSON structures | tests/test_executor.py:9 |
| test805 | `test_805_extract_json_path_with_array` | TEST805: Tests JSON path extraction with array indexing syntax Verifies that bracket notation like "items[0].name" correctly accesses array elements and their nested fields | tests/test_executor.py:15 |
| test806 | `test_806_extract_json_path_missing_field` | TEST806: Tests error handling when JSON path references non-existent fields Verifies that accessing missing fields returns an appropriate error message | tests/test_executor.py:21 |
| test807 | `test_807_apply_edge_type_direct` | TEST807: Tests EdgeType::Direct passes JSON values through unchanged Verifies that Direct edge type acts as a transparent passthrough without transformation | tests/test_executor.py:31 |
| test808 | `test_808_apply_edge_type_json_field` | TEST808: Tests EdgeType::JsonField extracts specific top-level fields from JSON objects Verifies that JsonField edge type correctly isolates a single named field from the source output | tests/test_executor.py:37 |
| test809 | `test_809_apply_edge_type_json_field_missing` | TEST809: Tests EdgeType::JsonField error handling for missing fields Verifies that attempting to extract a non-existent field returns an error | tests/test_executor.py:43 |
| test810 | `test_810_apply_edge_type_json_path` | TEST810: Tests EdgeType::JsonPath extracts values using nested path expressions Verifies that JsonPath edge type correctly navigates through multiple levels like "data.nested.value" | tests/test_executor.py:53 |
| test811 | `test_811_apply_edge_type_iteration` | TEST811: Tests EdgeType::Iteration preserves array values for iterative processing Verifies that Iteration edge type passes through arrays unchanged to enable ForEach patterns | tests/test_executor.py:59 |
| test812 | `test_812_apply_edge_type_collection` | TEST812: Tests EdgeType::Collection preserves collected values without transformation Verifies that Collection edge type maintains structure for aggregation patterns | tests/test_executor.py:65 |
| test813 | `test_813_extract_json_path_deeply_nested` | TEST813: Tests JSON path extraction through deeply nested object hierarchies (4+ levels) Verifies that paths can traverse multiple nested levels like "level1.level2.level3.level4.value" | tests/test_executor.py:71 |
| test814 | `test_814_extract_json_path_array_out_of_bounds` | TEST814: Tests error handling when array index exceeds available elements Verifies that out-of-bounds array access returns a descriptive error message | tests/test_executor.py:77 |
| test815 | `test_815_extract_json_path_single_segment` | TEST815: Tests JSON path extraction with single-level paths (no nesting) Verifies that simple field names without dots correctly extract top-level values | tests/test_executor.py:87 |
| test816 | `test_816_extract_json_path_with_special_characters` | TEST816: Tests JSON path extraction preserves special characters in string values Verifies that quotes, backslashes, and other special characters are correctly maintained | tests/test_executor.py:92 |
| test817 | `test_817_extract_json_path_with_null_value` | TEST817: Tests JSON path extraction correctly handles explicit null values Verifies that null is returned as serde_json::Value::Null rather than an error | tests/test_executor.py:98 |
| test818 | `test_818_extract_json_path_with_empty_array` | TEST818: Tests JSON path extraction correctly returns empty arrays Verifies that zero-length arrays are extracted as valid empty array values | tests/test_executor.py:104 |
| test819 | `test_819_extract_json_path_with_numeric_types` | TEST819: Tests JSON path extraction handles various numeric types correctly Verifies extraction of integers, floats, negative numbers, and zero | tests/test_executor.py:110 |
| test820 | `test_820_extract_json_path_with_boolean` | TEST820: Tests JSON path extraction correctly handles boolean values Verifies that true and false are extracted as proper boolean JSON values | tests/test_executor.py:119 |
| test821 | `test_821_extract_json_path_with_nested_arrays` | TEST821: Tests JSON path extraction with multi-dimensional arrays (matrix access) Verifies that nested array structures like "matrix[1]" correctly extract inner arrays | tests/test_executor.py:126 |
| test822 | `test_822_extract_json_path_invalid_array_index` | TEST822: Tests error handling for non-numeric array indices Verifies that invalid indices like "items[abc]" return a descriptive parse error | tests/test_executor.py:132 |
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
| test839 | `test_839_peer_response_delivers_logs_before_stream_start` | TEST839: LOG frames arriving BEFORE StreamStart are delivered immediately This tests the critical fix: during a peer call, the peer (e.g., modelcartridge) sends LOG frames for minutes during model download BEFORE sending any data (StreamStart + Chunk). The handler must receive these LOGs in real-time so it can re-emit progress and keep the engine's activity timer alive. Previously, demux_single_stream blocked on awaiting StreamStart before returning PeerResponse, which meant the handler couldn't call recv() until data arrived — causing 120s activity timeouts during long downloads. | tests/test_cartridge_runtime.py:2200 |
| test840 | `test_840_peer_response_collect_bytes_discards_logs` | TEST840: PeerResponse::collect_bytes discards LOG frames | tests/test_cartridge_runtime.py:2251 |
| test841 | `test_841_peer_response_collect_value_discards_logs` | TEST841: PeerResponse::collect_value discards LOG frames | tests/test_cartridge_runtime.py:2281 |
| test842 | `test_842_progress_sender_emits_frames` | TEST842: run_with_keepalive returns closure result (fast operation, no keepalive frames) | tests/test_cartridge_runtime.py:2374 |
| test843 | `test_843_progress_sender_from_background_thread` | TEST843: run_with_keepalive returns Ok/Err from closure | tests/test_cartridge_runtime.py:2391 |
| test844 | `test_844_progress_sender_multiple_threads` | TEST844: run_with_keepalive propagates errors from closure | tests/test_cartridge_runtime.py:2414 |
| test845 | `test_845_progress_sender_independent_of_emitter` | TEST845: ProgressSender emits progress and log frames independently of OutputStream | tests/test_cartridge_runtime.py:2439 |
| test846 | `test_846_progress_frame_roundtrip` | TEST846: Test progress LOG frame encode/decode roundtrip preserves progress float | tests/test_cbor_io.py:1003 |
| test847 | `test_847_progress_double_roundtrip` | TEST847: Double roundtrip (modelcartridge → relay → candlecartridge) | tests/test_cbor_io.py:1036 |
| test848 | `test_848_relay_notify_roundtrip` | TEST848: RelayNotify encode/decode roundtrip preserves manifest and limits | tests/test_cbor_io.py:913 |
| test849 | `test_849_relay_state_roundtrip` | TEST849: RelayState encode/decode roundtrip preserves resource payload | tests/test_cbor_io.py:935 |
| test850 | `test_850_all_format_conversion_paths_build_valid_urns` | TEST850: all_format_conversion_paths each entry builds a valid parseable CapUrn | tests/test_standard_format_conversion.py:9 |
| test851 | `test_851_format_conversion_urn_specs` | TEST851: format_conversion_urn in/out specs match the input constants | tests/test_standard_format_conversion.py:23 |
| test852 | `test_852_lub_identical` | TEST852: LUB of identical URNs returns the same URN | tests/test_media_urn.py:435 |
| test853 | `test_853_lub_no_common_tags` | TEST853: LUB of URNs with no common tags returns media: (universal) | tests/test_media_urn.py:442 |
| test854 | `test_854_lub_partial_overlap` | TEST854: LUB keeps common tags, drops differing ones | tests/test_media_urn.py:452 |
| test855 | `test_855_lub_list_vs_scalar` | TEST855: LUB of list and non-list drops list tag | tests/test_media_urn.py:462 |
| test856 | `test_856_lub_empty` | TEST856: LUB of empty input returns universal type | tests/test_media_urn.py:472 |
| test857 | `test_857_lub_single` | TEST857: LUB of single input returns that input | tests/test_media_urn.py:479 |
| test858 | `test_858_lub_three_inputs` | TEST858: LUB with three+ inputs narrows correctly | tests/test_media_urn.py:486 |
| test859 | `test_859_lub_valued_tags` | TEST859: LUB with valued tags (non-marker) that differ | tests/test_media_urn.py:497 |
| test860 | `test_860_seq_assigner_same_rid_different_xids_independent` | TEST860: Same RID with different XIDs get independent seq counters | tests/test_cbor_frame.py:687 |
| test880 | `test_880_no_duplicates_with_unique_caps` | TEST880: Tests duplicate detection passes for caps with unique URN combinations Verifies that check_for_duplicate_caps() correctly accepts caps with different op/in/out combinations | tests/test_plan_builder.py:167 |
| test886 | `test_886_optional_non_io_arg_with_default_has_default` | TEST886: Tests optional non-IO arguments with default values are marked as HasDefault Verifies that optional arguments with defaults behave the same as required ones with defaults | tests/test_plan_builder.py:316 |
| test890 | `test_890_direction_semantic_matching` | TEST890: Semantic direction matching - generic provider matches specific request | tests/test_cap_urn.py:1187 |
| test891 | `test_891_direction_semantic_specificity` | TEST891: Semantic direction specificity - more media URN tags = higher specificity | tests/test_cap_urn.py:1263 |
| test892 | `test_892_extensions_serialization` | TEST892: Test extensions serializes/deserializes correctly in MediaSpecDef | tests/test_media_spec.py:480 |
| test893 | `test_893_extensions_with_metadata_and_validation` | TEST893: Test extensions can coexist with metadata and validation | tests/test_media_spec.py:502 |
| test894 | `test_894_multiple_extensions` | TEST894: Test multiple extensions in a media spec | tests/test_media_spec.py:535 |
| test895 | `test_895_cap_output_media_specs_have_extensions` | TEST895: All cap output media specs must have file extensions defined. This is a regression guard: every media URN used as a cap output produces user-facing files. If a spec lacks extensions, save_cap_output and import flows will fail at runtime. | tests/test_media_spec.py:680 |
| test896 | `test_896_cap_input_media_specs_have_extensions` | TEST896: All cap input media specs that represent user files must have extensions. These are the entry points — the file types users can right-click on. | tests/test_media_spec.py:712 |
| test897 | `test_897_cap_output_extension_values_correct` | TEST897: Verify that specific cap output URNs resolve to the correct extension. This catches misconfigurations where a spec exists but has the wrong extension. | tests/test_media_spec.py:739 |
| test902 | `test_902_compute_checksum_empty` | TEST902: Verify FNV-1a checksum handles empty data | tests/test_cbor_frame.py:1514 |
| test903 | `test_903_chunk_with_chunk_index_and_checksum` | TEST903: Verify CHUNK frame can store chunk_index and checksum fields | tests/test_cbor_frame.py:1520 |
| test904 | `test_904_stream_end_with_chunk_count` | TEST904: Verify STREAM_END frame can store chunk_count field | tests/test_cbor_frame.py:1536 |
| test907 | `test_907_cbor_rejects_stream_end_without_chunk_count` | TEST907: Offline flag blocks fetch_from_registry without making HTTP request | tests/test_cbor_frame.py:1547 |
| test908 | `test_908_cached_caps_accessible_when_offline` | TEST908: Cached caps remain accessible when offline | tests/test_registry.py:224 |
| test909 | `test_909_set_offline_false_restores_fetch` | TEST909: set_offline(false) restores fetch ability (would fail with HTTP error, not NetworkBlocked) | tests/test_registry.py:241 |
| test920 | `test_920_cap_urn_total_order_basic` | TEST920: Tests creation of a simple execution plan with a single capability Verifies that single_cap() generates a valid plan with input_slot, cap node, and output node | tests/test_cap_urn.py:1288 |
| test921 | `test_921_cap_urn_order_consistent_with_equality` | TEST921: Tests creation of a linear chain of capabilities connected in sequence Verifies that linear_chain() correctly links multiple caps with proper edges and topological order | tests/test_cap_urn.py:1316 |
| test922 | `test_922_cap_urn_list_sortable` | TEST922: Tests creation and validation of an empty execution plan with no nodes Verifies that plans without capabilities are valid and handle zero nodes correctly | tests/test_cap_urn.py:1327 |
| test923 | `test_923_cap_urn_order_returns_not_implemented_for_non_cap` | TEST923: Tests storing and retrieving metadata attached to an execution plan Verifies that arbitrary JSON metadata can be associated with a plan for context preservation | tests/test_cap_urn.py:1345 |
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
| test953 | `test_953_linear_plan_still_works` | TEST953: Linear plans (no ForEach/Collect) still convert successfully | tests/test_orchestrator_plan_converter.py:111 |
| test954 | `test_954_standalone_collect_passthrough` | TEST954: Standalone Collect nodes are handled as pass-through | tests/test_orchestrator_plan_converter.py:140 |
| test955 | `test_955_split_map_array` | TEST955: split_cbor_array with nested maps | tests/test_cbor_util.py:67 |
| test956 | `test_956_roundtrip_assemble_split` | TEST956: assemble then split roundtrip preserves data | tests/test_cbor_util.py:76 |
| test957 | `test_957_cap_input_file_new` | TEST957: Tests CapInputFile constructor creates file with correct path and media URN Verifies new() initializes file_path, media_urn and leaves metadata/source_id as None | tests/test_planner_argument_binding.py:345 |
| test958 | `test_958_cap_input_file_from_listing` | TEST958: Tests CapInputFile from_listing sets source metadata correctly Verifies from_listing() populates source_id and source_type as Listing | tests/test_planner_argument_binding.py:354 |
| test959 | `test_959_cap_input_file_filename` | TEST959: Tests CapInputFile extracts filename from full path correctly Verifies filename() returns just the basename without directory path | tests/test_planner_argument_binding.py:361 |
| test960 | `test_960_argument_binding_literal_string` | TEST960: Tests ArgumentBinding literal_string creates Literal variant with string value Verifies literal_string() wraps string in JSON Value::String | tests/test_planner_argument_binding.py:367 |
| test961 | `test_961_assemble_empty` | TEST961: assemble empty list produces empty CBOR array | tests/test_cbor_util.py:84 |
| test962 | `test_962_assemble_invalid_item` | TEST962: assemble rejects invalid CBOR item | tests/test_cbor_util.py:89 |
| test963 | `test_963_split_binary_items` | TEST963: split preserves CBOR byte strings (binary data — the common case in bifaci) | tests/test_cbor_util.py:95 |
| test964 | `test_964_split_sequence_bytes` | TEST964: split_cbor_sequence splits concatenated CBOR Bytes values | tests/test_cbor_util.py:109 |
| test965 | `test_965_split_sequence_text` | TEST965: split_cbor_sequence splits concatenated CBOR Text values | tests/test_cbor_util.py:119 |
| test966 | `test_966_split_sequence_mixed` | TEST966: split_cbor_sequence handles mixed types | tests/test_cbor_util.py:128 |
| test967 | `test_967_split_sequence_single` | TEST967: split_cbor_sequence single-item sequence | tests/test_cbor_util.py:137 |
| test968 | `test_968_roundtrip_assemble_split_sequence` | TEST968: roundtrip — assemble then split preserves items | tests/test_cbor_util.py:145 |
| test969 | `test_969_roundtrip_split_assemble_sequence` | TEST969: roundtrip — split then assemble preserves byte-for-byte | tests/test_cbor_util.py:152 |
| test970 | `test_970_split_sequence_empty` | TEST970: split_cbor_sequence rejects empty data | tests/test_cbor_util.py:159 |
| test971 | `test_971_split_sequence_truncated` | TEST971: split_cbor_sequence rejects truncated CBOR | tests/test_cbor_util.py:165 |
| test972 | `test_972_assemble_sequence_invalid_item` | TEST972: assemble_cbor_sequence rejects invalid CBOR item | tests/test_cbor_util.py:174 |
| test973 | `test_973_assemble_sequence_empty` | TEST973: assemble_cbor_sequence with empty items list produces empty bytes | tests/test_cbor_util.py:180 |
| test974 | `test_974_sequence_is_not_array` | TEST974: CBOR sequence is NOT a CBOR array — split_cbor_array rejects a sequence | tests/test_cbor_util.py:185 |
| test975 | `test_975_single_value_sequence` | TEST975: split_cbor_sequence works on data that is also a valid CBOR array (single top-level value) | tests/test_cbor_util.py:192 |
| test976 | `test_976_cap_graph_find_best_path` | TEST976: CapGraph::find_best_path returns highest-specificity path over shortest | tests/test_cap_matrix.py:647 |
| test991 | `test_991_detects_duplicate_cap_urns` | TEST991: Tests duplicate detection identifies caps with identical URNs Verifies that check_for_duplicate_caps() returns an error when multiple caps share the same cap_urn | tests/test_plan_builder.py:150 |
| test992 | `test_992_different_ops_same_types_not_duplicates` | TEST992: Tests caps with different operations but same input/output types are not duplicates Verifies that only the complete URN (including op) is used for duplicate detection | tests/test_plan_builder.py:178 |
| test993 | `test_993_same_op_different_input_types_not_duplicates` | TEST993: Tests caps with same operation but different input types are not duplicates Verifies that input type differences distinguish caps with the same operation name | tests/test_plan_builder.py:188 |
| test994 | `test_994_input_arg_first_cap_auto_resolved_from_input` | TEST994: Tests first cap's input argument is automatically resolved from input file Verifies that determine_resolution_with_io_check() returns FromInputFile for the first cap in a chain | tests/test_plan_builder.py:198 |
| test995 | `test_995_input_arg_subsequent_cap_auto_resolved_from_previous` | TEST995: Tests subsequent caps' input arguments are automatically resolved from previous output Verifies that determine_resolution_with_io_check() returns FromPreviousOutput for caps after the first | tests/test_plan_builder.py:212 |
| test996 | `test_996_output_arg_auto_resolved` | TEST996: Tests output arguments are automatically resolved from previous cap's output Verifies that arguments matching the output spec are always resolved as FromPreviousOutput | tests/test_plan_builder.py:236 |
| test997 | `test_997_file_path_type_fallback_first_cap` | TEST997: Tests MEDIA_FILE_PATH argument type resolves to input file for first cap Verifies that generic file-path arguments are bound to input file in the first cap | tests/test_plan_builder.py:250 |
| test998 | `test_998_file_path_type_fallback_subsequent_cap` | TEST998: Tests MEDIA_FILE_PATH argument type resolves to previous output for subsequent caps Verifies that generic file-path arguments are bound to previous cap's output after the first cap | tests/test_plan_builder.py:264 |
| test999 | `test_999_file_path_array_fallback` | TEST999: Tests MEDIA_FILE_PATH_ARRAY argument type resolution for first and subsequent caps Verifies that file-path array arguments follow the same resolution pattern as single file paths | tests/test_plan_builder.py:278 |
| test1009 | `test_1009_non_io_arg_with_default_has_default` | TEST1009: Tests required non-IO arguments with default values are marked as HasDefault Verifies that arguments like integers with defaults don't require user input | tests/test_plan_builder.py:302 |
| test1012 | `test_1012_non_io_arg_without_default_requires_user_input` | TEST1012: Tests required non-IO arguments without defaults require user input Verifies that arguments like strings without defaults are marked as RequiresUserInput | tests/test_plan_builder.py:330 |
| test1015 | `test_1015_optional_non_io_arg_without_default_requires_user_input` | TEST1015: Tests optional non-IO arguments without defaults still require user input Verifies that optional arguments without defaults must be explicitly provided or skipped | tests/test_plan_builder.py:344 |
| test1019 | `test_1019_validation_to_json_none` | TEST1019: Tests validation_to_json() returns None for None input Verifies that missing validation metadata is converted to JSON None | tests/test_plan_builder.py:358 |
| test1100 | `test_1100_cap_urn_normalizes_media_urn_tag_order` | TEST1100: Tests that CapUrn normalizes media URN tags to canonical order This is the root cause fix for caps not matching when cartridges report URNs with different tag ordering than the registry | tests/test_cap_urn.py:1228 |
| test1103 | `test_1103_is_dispatchable_uses_correct_directionality` | TEST1103: Tests that is_dispatchable has correct directionality The available cap (provider) must be dispatchable for the requested cap (request) | tests/test_cap_urn.py:1242 |
| test1104 | `test_1104_is_dispatchable_rejects_non_dispatchable` | TEST1104: Tests that is_dispatchable rejects when provider cannot dispatch request | tests/test_cap_urn.py:1253 |
| test1105 | `test_1105_two_steps_same_cap_urn_different_slot_values` | TEST1105: Two steps with the same cap_urn get distinct slot values via different node_ids. This is the core disambiguation scenario that step-index keying was designed to solve. | tests/test_planner_argument_binding.py:84 |
| test1106 | `test_1106_slot_falls_through_to_cap_settings_shared` | TEST1106: Slot resolution falls through to cap_settings when no slot_value exists. cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value. | tests/test_planner_argument_binding.py:112 |
| test1107 | `test_1107_slot_value_overrides_cap_settings_per_step` | TEST1107: step_0 has a slot_value override, step_1 falls through to cap_settings. Proves per-step override works while shared settings remain as fallback. | tests/test_planner_argument_binding.py:133 |
| test1108 | `test_1108_resolve_all_passes_node_id` | TEST1108: ResolveAll with node_id threads correctly through to each binding. | tests/test_planner_argument_binding.py:160 |
| test1109 | `test_1109_slot_key_uses_node_id_not_cap_urn` | TEST1109: Slot key uses node_id, NOT cap_urn — a slot_value keyed by cap_urn must not match. | tests/test_planner_argument_binding.py:187 |
| test1110 | `test_1110_no_capability_steps_error_on_empty_wirings` |  | tests/test_machine.py:102 |
| test1111 | `test_1111_unknown_cap_error_when_not_in_registry` | TEST1111: ForEach works for user-provided list sources not in the graph. This is the original bug — media:list;textable;txt is a user import source, not a cap output. Previously, no ForEach edge existed for it because insert_cardinality_transitions() only pre-computed edges for cap outputs. With dynamic synthesis, ForEach is available for ANY list source. | tests/test_machine.py:112 |
| test1112 | `test_1112_single_edge_strand_resolves_correctly` | TEST1112: Collect is not synthesized during path finding. Reaching a list target type requires the cap itself to output a list type. | tests/test_machine.py:131 |
| test1113 | `test_1113_two_step_chain_shares_intermediate_node` | TEST1113: Multi-cap path without Collect — Collect is not synthesized | tests/test_machine.py:156 |
| test1114 | `test_1114_from_strand_produces_single_strand_machine` | TEST1114: Graph stores only Cap edges after sync | tests/test_machine.py:191 |
| test1115 | `test_1115_from_strands_keeps_strands_disjoint` | TEST1115: ForEach is synthesized when is_sequence=true AND caps can consume items | tests/test_machine.py:208 |
| test1116 | `test_1116_from_strands_empty_raises_no_capability_steps` | TEST1116: Collect is never synthesized during path finding | tests/test_machine.py:232 |
| test1117 | `test_1117_machine_is_equivalent_strict_positional_order_matters` | TEST1117: ForEach is NOT synthesized when is_sequence=false | tests/test_machine.py:242 |
| test1118 | `test_1118_strand_is_equivalent_consistent_node_bijection` | TEST1118: ForEach not synthesized without cap consumers even with is_sequence=true | tests/test_machine.py:266 |
| test1119 | `test_1119_match_sources_to_args_single_trivial` | TEST1119: Strand::knit returns a single-strand Machine via the new resolver. Smoke test the registry-threaded API end-to-end. | tests/test_machine.py:287 |
| test1120 | `test_1120_match_sources_more_specific_source_matches_general_arg` | TEST1120: Strand::knit fails hard when the cap is not in the registry — the planner produces strands referencing caps that must be present in the cap registry's cache for resolution to succeed. | tests/test_machine.py:303 |
| test1121 | `test_1121_match_sources_unmatched_source_fails_hard` | TEST1121: CBOR Array of file-paths in CBOR mode (validates new Array support) | tests/test_machine.py:316 |
| test1122 | `test_1122_match_sources_ambiguous_raises_ambiguous_error` | TEST1122: Full path: engine REQ → runtime → cartridge → response back through relay | tests/test_machine.py:333 |
| test1123 | `test_1123_cyclic_strand_fails_hard` | TEST1123: Cartridge ERR frame flows back to engine through relay | tests/test_machine.py:350 |
| test1124 | `test_1124_machine_parse_error_wraps_syntax_error` | TEST1124: CBOR decode REJECTS STREAM_END frame missing chunk_count field | tests/test_machine.py:379 |
| test1125 | `test_1125_parse_machine_unknown_cap_raises_parse_error_with_abstraction_cause` | TEST1125: map_progress clamps child to [0.0, 1.0] and maps to [base, base+weight] | tests/test_machine.py:394 |
| test1126 | `test_1126_parse_machine_single_wiring_one_strand` | TEST1126: map_progress is deterministic — same inputs always produce same output | tests/test_machine.py:415 |
| test1127 | `test_1127_parse_machine_disconnected_wirings_become_separate_strands` | TEST1127: Documentation field round-trips through JSON serialize/deserialize. The documentation field carries an arbitrary markdown body authored in the source TOML via the triple-quoted literal string syntax. The round-trip must preserve every character — including newlines, backticks, double quotes, and Unicode — because consumers (info panels, capdag.com, etc.) render it directly. JSON.stringify on the capgraph side and the Rust serializer on this side must agree on escaping; this test fails hard if they don't. | tests/test_machine.py:436 |
| test1128 | `test_1128_parse_machine_shared_node_name_yields_one_strand` | TEST1128: When documentation is None, the serializer must skip the field entirely. This matches the behaviour of the JS toJSON, the ObjC toDictionary, and the schema's "if present" semantics — there is no null sentinel, only absence. A bug here would silently start emitting `"documentation":null` and break consumers that distinguish between absent and explicit null. | tests/test_machine.py:460 |
| test1129 | `test_1129_binding_slot_identity_is_outer_media_urn` | TEST1129: A JSON document produced by capgraph (the canonical source) with a `documentation` field must deserialize into a Cap with the body intact. Models the actual on-disk shape — not a synthetic round-trip — to catch a mismatch between the JSON schema and the Rust struct field naming. | tests/test_machine.py:485 |
| test1130 | `test_1130_strand_equivalence_rejects_mismatched_node_urns` | TEST1130: documentation set/clear lifecycle parallels cap_description. Catches a regression where the setter or clearer is wired to the wrong field — for example, set_documentation accidentally writing to cap_description. | tests/test_machine.py:527 |
| test1131 | `test_1131_resolve_strand_foreach_sets_is_loop_on_next_cap` | TEST1131: Documentation propagates from MediaSpecDef through resolve_media_urn into ResolvedMediaSpec. This is the resolution path used by every consumer that asks the registry for a media spec — info panels, the cap navigator, the UI — so a regression here makes the new field invisible everywhere. | tests/test_machine.py:553 |
| test1132 | `test_1132_resolve_strand_no_cap_steps_raises_no_capability_steps` | TEST1132: MediaSpecDef serializes documentation only when present and round-trips losslessly. Mirrors TEST1127/1128 for the cap side. | tests/test_machine.py:588 |
| test1133 | `test_1133_machine_from_string_delegates_to_parse_machine` | TEST1133: MediaSpecDef set/clear lifecycle for documentation. Catches a regression where the setter or clearer accidentally writes to or reads from `description` (the short field) instead of `documentation` (the long markdown body). | tests/test_machine.py:614 |
| | | | |
| unnumbered | `test_abstraction_error_subclass_hierarchy` | TEST1134: All resolution error subclasses are instances of MachineAbstractionError. | tests/test_machine.py:635 |
| unnumbered | `test_array_schema_validation` | TEST: Schema validation with array schemas | tests/test_schema_validation.py:207 |
| unnumbered | `test_assignment_bindings_sorted_by_slot_urn` | Mirror-specific coverage: Assignment bindings are sorted by cap_arg_media_urn for canonical form | tests/test_machine.py:712 |
| unnumbered | `test_cap_caller_get_positional_arg_positions` |  | tests/test_caller.py:398 |
| unnumbered | `test_cap_caller_validate_arguments_missing_required` |  | tests/test_caller.py:363 |
| unnumbered | `test_cap_caller_validate_arguments_success` |  | tests/test_caller.py:346 |
| unnumbered | `test_cap_caller_validate_arguments_unknown` |  | tests/test_caller.py:380 |
| unnumbered | `test_chunk_corrupted_payload_rejected` | Mirror-specific coverage: chunk corrupted payload is detected by checksum mismatch (verify_chunk_checksum) | tests/test_cbor_frame.py:1035 |
| unnumbered | `test_chunking_data_integrity_3x` | Mirror-specific coverage: Test auto-chunking preserves data integrity across chunk boundaries for 3x max_chunk payload | tests/test_cbor_io.py:848 |
| unnumbered | `test_concatenated_vs_final_payload_divergence` | Mirror-specific coverage: Test that concatenated() returns full payload while final_payload() returns only last chunk | tests/test_cartridge_host_runtime.py:265 |
| unnumbered | `test_exact_max_chunk_stream_chunked` | Mirror-specific coverage: Test payload exactly equal to max_chunk produces STREAM_START + 1 CHUNK + STREAM_END + END | tests/test_cbor_io.py:781 |
| unnumbered | `test_extract_effective_payload_invalid_cap_urn` | Mirror-specific coverage: Test extract_effective_payload with invalid cap URN returns CapUrn error | tests/test_cartridge_runtime.py:392 |
| unnumbered | `test_input_validation_optional_arg` | Extra Python-specific validation coverage: optional argument omitted | tests/test_validation.py:61 |
| unnumbered | `test_input_validation_too_many_args` | Extra Python-specific validation coverage: too many positional arguments | tests/test_validation.py:75 |
| unnumbered | `test_llm_generate_text_urn_specs` | Mirror-specific coverage: Test llm_generate_text_urn in/out specs match the expected media URNs semantically | tests/test_standard_caps.py:57 |
| unnumbered | `test_max_chunk_plus_one_splits_into_two_chunks` | Mirror-specific coverage: Test payload of max_chunk + 1 produces STREAM_START + 2 CHUNK + STREAM_END + END | tests/test_cbor_io.py:812 |
| unnumbered | `test_nested_object_schema_validation` | TEST: Schema validation with nested object schemas | tests/test_schema_validation.py:154 |
| unnumbered | `test_normalize_urn_with_trailing_semicolon` |  | tests/test_registry.py:337 |
| unnumbered | `test_output_validation_with_details` | TEST: Output validation with error details | tests/test_schema_validation.py:335 |
| unnumbered | `test_parse_machine_undefined_alias_raises_syntax_error` | TEST1136: parse_machine with undefined cap alias raises MachineParseError wrapping UndefinedAliasError. | tests/test_machine.py:671 |
| unnumbered | `test_registry_add_caps_to_cache` | Additional integration tests for registry functionality | tests/test_registry.py:294 |
| unnumbered | `test_registry_cache_key_consistency` |  | tests/test_registry.py:311 |
| unnumbered | `test_registry_config_builder_pattern` |  | tests/test_registry.py:327 |
| unnumbered | `test_strand_node_urn_accessor` | TEST1135: MachineStrand.node_urn(id) returns the MediaUrn at that NodeId. | tests/test_machine.py:652 |
| unnumbered | `test_two_strand_machine_serializes_to_notation` | TEST1137: Machine with two strands serializes to a non-empty notation string. | tests/test_machine.py:687 |
| unnumbered | `test_type_constraint_validation` | TEST: Schema validation with type constraints | tests/test_schema_validation.py:251 |
| unnumbered | `test_validate_multiple_arguments` | TEST: Schema validation with multiple arguments | tests/test_schema_validation.py:286 |
| unnumbered | `test_write_frame_writes_length_prefixed` | Mirror-specific coverage: Test write_frame writes length-prefixed frame | tests/test_cbor_io.py:81 |
| unnumbered | `test_write_stream_chunked_reassembly` | Mirror-specific coverage: Test write_stream_chunked sends STREAM_START + CHUNK(s) + STREAM_END + END for payload larger than max_chunk, CHUNK frames + END frame, and reading them back reassembles the full original data | tests/test_cbor_io.py:739 |
---

## Unnumbered Tests

The following tests are cataloged but do not currently participate in numeric test indexing.

- `test_abstraction_error_subclass_hierarchy` — tests/test_machine.py:635
- `test_array_schema_validation` — tests/test_schema_validation.py:207
- `test_assignment_bindings_sorted_by_slot_urn` — tests/test_machine.py:712
- `test_cap_caller_get_positional_arg_positions` — tests/test_caller.py:398
- `test_cap_caller_validate_arguments_missing_required` — tests/test_caller.py:363
- `test_cap_caller_validate_arguments_success` — tests/test_caller.py:346
- `test_cap_caller_validate_arguments_unknown` — tests/test_caller.py:380
- `test_chunk_corrupted_payload_rejected` — tests/test_cbor_frame.py:1035
- `test_chunking_data_integrity_3x` — tests/test_cbor_io.py:848
- `test_concatenated_vs_final_payload_divergence` — tests/test_cartridge_host_runtime.py:265
- `test_exact_max_chunk_stream_chunked` — tests/test_cbor_io.py:781
- `test_extract_effective_payload_invalid_cap_urn` — tests/test_cartridge_runtime.py:392
- `test_input_validation_optional_arg` — tests/test_validation.py:61
- `test_input_validation_too_many_args` — tests/test_validation.py:75
- `test_llm_generate_text_urn_specs` — tests/test_standard_caps.py:57
- `test_max_chunk_plus_one_splits_into_two_chunks` — tests/test_cbor_io.py:812
- `test_nested_object_schema_validation` — tests/test_schema_validation.py:154
- `test_normalize_urn_with_trailing_semicolon` — tests/test_registry.py:337
- `test_output_validation_with_details` — tests/test_schema_validation.py:335
- `test_parse_machine_undefined_alias_raises_syntax_error` — tests/test_machine.py:671
- `test_registry_add_caps_to_cache` — tests/test_registry.py:294
- `test_registry_cache_key_consistency` — tests/test_registry.py:311
- `test_registry_config_builder_pattern` — tests/test_registry.py:327
- `test_strand_node_urn_accessor` — tests/test_machine.py:652
- `test_two_strand_machine_serializes_to_notation` — tests/test_machine.py:687
- `test_type_constraint_validation` — tests/test_schema_validation.py:251
- `test_validate_multiple_arguments` — tests/test_schema_validation.py:286
- `test_write_frame_writes_length_prefixed` — tests/test_cbor_io.py:81
- `test_write_stream_chunked_reassembly` — tests/test_cbor_io.py:739

---

## Numbered Tests Missing Descriptions

These tests still participate in numeric indexing, but the cataloger did not find an authoritative immediate comment/docstring description for them. This is reported explicitly so intentional blank-description parity and accidental comment drift are both visible.

- `test310` / `test_310_llm_generate_text_urn_tags` — tests/test_standard_caps.py:49
- `test1110` / `test_1110_no_capability_steps_error_on_empty_wirings` — tests/test_machine.py:102

---

*Generated from CapDag-Py source tree*
*Total tests: 888*
*Total numbered tests: 859*
*Total unnumbered tests: 29*
*Total numbered tests missing descriptions: 2*
