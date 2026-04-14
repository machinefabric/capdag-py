"""Standard capability URN builders

This module provides standard capability URN builders used across
all MACINA providers. These are the single source of truth for URN construction.
"""

from dataclasses import dataclass
from typing import List, Tuple

from capdag.urn.cap_urn import CapUrn, CapUrnBuilder
from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.urn.media_urn import (
    # Primitives
    MEDIA_STRING,
    MEDIA_INTEGER,
    MEDIA_NUMBER,
    MEDIA_BOOLEAN,
    MEDIA_OBJECT,
    MEDIA_IDENTITY,
    MEDIA_VOID,
    # List types
    MEDIA_STRING_LIST,
    MEDIA_INTEGER_LIST,
    MEDIA_NUMBER_LIST,
    MEDIA_BOOLEAN_LIST,
    MEDIA_OBJECT_LIST,
    # Semantic media types
    MEDIA_PNG,
    # Document types
    MEDIA_PDF,
    MEDIA_EPUB,
    # Text format types
    MEDIA_MD,
    MEDIA_TXT,
    MEDIA_RST,
    MEDIA_LOG,
    # Semantic input types
    MEDIA_MODEL_SPEC,
    MEDIA_MODEL_REPO,
    MEDIA_JSON_SCHEMA,
    MEDIA_TEXTABLE_PAGE,
    # CAPDAG output types
    MEDIA_MODEL_DIM,
    MEDIA_DOWNLOAD_OUTPUT,
    MEDIA_LIST_OUTPUT,
    MEDIA_STATUS_OUTPUT,
    MEDIA_CONTENTS_OUTPUT,
    MEDIA_AVAILABILITY_OUTPUT,
    MEDIA_PATH_OUTPUT,
    MEDIA_EMBEDDING_VECTOR,
    MEDIA_JSON,
    MEDIA_LLM_INFERENCE_OUTPUT,
    MEDIA_DECISION,
    # Format conversion types (JSON, YAML, CSV variants)
    MEDIA_JSON_VALUE,
    MEDIA_JSON_RECORD,
    MEDIA_JSON_LIST,
    MEDIA_JSON_LIST_RECORD,
    MEDIA_YAML_VALUE,
    MEDIA_YAML_RECORD,
    MEDIA_YAML_LIST,
    MEDIA_YAML_LIST_RECORD,
    MEDIA_CSV,
    # Bare list types (no format tag)
    MEDIA_TEXTABLE_LIST,
)


# =============================================================================
# STANDARD CAP URN CONSTANTS
# =============================================================================

# Identity capability — the categorical identity morphism. MANDATORY in every capset.
# Accepts any media type as input and outputs any media type.
CAP_IDENTITY = "cap:"

# Discard capability — the terminal morphism. Standard, NOT mandatory.
# Accepts any media type as input and produces void output.
# The capdag lib provides a default implementation; cartridges may override.
CAP_DISCARD = "cap:in=media:;out=media:void"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def identity_urn() -> CapUrn:
    """Parse and return the canonical identity CapUrn from CAP_IDENTITY."""
    return CapUrn.from_string(CAP_IDENTITY)


def discard_urn() -> CapUrn:
    """Parse and return the canonical discard CapUrn from CAP_DISCARD."""
    return CapUrn.from_string(CAP_DISCARD)


def identity_cap() -> Cap:
    """Construct the canonical Identity Cap definition."""
    urn = identity_urn()
    cap = Cap.with_description(
        urn,
        "Identity",
        "identity",
        "The categorical identity morphism. Echoes input as output unchanged. Mandatory in every capability set.",
    )
    cap.add_arg(CapArg(
        media_urn="media:",
        required=True,
        sources=[StdinSource("media:")],
    ))
    cap.set_output(CapOutput("media:", "The input data, unchanged"))
    return cap


def discard_cap() -> Cap:
    """Construct the canonical Discard Cap definition."""
    urn = discard_urn()
    cap = Cap.with_description(
        urn,
        "Discard",
        "discard",
        "The terminal morphism. Consumes input and produces void output.",
    )
    cap.add_arg(CapArg(
        media_urn="media:",
        required=True,
        sources=[StdinSource("media:")],
    ))
    cap.set_output(CapOutput(MEDIA_VOID, "Void (no output)"))
    return cap


_MEDIA_URN_FOR_TYPE = {
    "string": MEDIA_STRING,
    "integer": MEDIA_INTEGER,
    "number": MEDIA_NUMBER,
    "boolean": MEDIA_BOOLEAN,
    "object": MEDIA_OBJECT,
    "string-list": MEDIA_STRING_LIST,
    "integer-list": MEDIA_INTEGER_LIST,
    "number-list": MEDIA_NUMBER_LIST,
    "boolean-list": MEDIA_BOOLEAN_LIST,
    "object-list": MEDIA_OBJECT_LIST,
}


def media_urn_for_type(type_name: str) -> str:
    """Map a type name to its media URN constant.

    Raises ValueError if type_name is unknown.
    """
    result = _MEDIA_URN_FOR_TYPE.get(type_name)
    if result is None:
        valid = ", ".join(sorted(_MEDIA_URN_FOR_TYPE.keys()))
        raise ValueError(f"Unknown media type: {type_name}. Valid types are: {valid}")
    return result


def coercion_urn(source_type: str, target_type: str) -> CapUrn:
    """Build a generic coercion URN given source and target types.

    Raises ValueError if source_type or target_type is not a known media type.
    """
    in_spec = media_urn_for_type(source_type)
    out_spec = media_urn_for_type(target_type)
    return (
        CapUrnBuilder()
        .tag("op", "coerce")
        .in_spec(in_spec)
        .out_spec(out_spec)
        .build()
    )


def all_coercion_paths() -> List[Tuple[str, str]]:
    """Get list of all valid coercion paths.

    Returns (source_type, target_type) pairs for all supported coercions.
    """
    return [
        # To string (from all textable types)
        ("integer", "string"),
        ("number", "string"),
        ("boolean", "string"),
        ("object", "string"),
        ("string-list", "string"),
        ("integer-list", "string"),
        ("number-list", "string"),
        ("boolean-list", "string"),
        ("object-list", "string"),
        # To integer
        ("string", "integer"),
        ("number", "integer"),
        ("boolean", "integer"),
        # To number
        ("string", "number"),
        ("integer", "number"),
        ("boolean", "number"),
        # To object (wrap in object)
        ("string", "object"),
        ("integer", "object"),
        ("number", "object"),
        ("boolean", "object"),
    ]


# =============================================================================
# URN BUILDER FUNCTIONS
# =============================================================================
# These are the SINGLE SOURCE OF TRUTH for URN construction.


# -----------------------------------------------------------------------------
# LLM URN BUILDERS
# -----------------------------------------------------------------------------


def llm_generate_text_urn() -> str:
    """Build URN for LLM text generation capability"""
    return (
        CapUrnBuilder()
        .tag("op", "generate_text")
        .tag("llm", "*")
        .tag("ml-model", "*")
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_STRING)
        .build()
        .to_string()
    )


def llm_multiplechoice_urn(lang_code: str) -> CapUrn:
    """Build URN for multiplechoice capability"""
    return (
        CapUrnBuilder()
        .tag("op", "multiplechoice")
        .tag("constrained", "*")
        .tag("language", lang_code)
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_LLM_INFERENCE_OUTPUT)
        .build()
    )


def llm_codegeneration_urn(lang_code: str) -> CapUrn:
    """Build URN for codegeneration capability"""
    return (
        CapUrnBuilder()
        .tag("op", "codegeneration")
        .tag("constrained", "*")
        .tag("language", lang_code)
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_LLM_INFERENCE_OUTPUT)
        .build()
    )


def llm_creative_urn(lang_code: str) -> CapUrn:
    """Build URN for creative capability"""
    return (
        CapUrnBuilder()
        .tag("op", "creative")
        .tag("constrained", "*")
        .tag("language", lang_code)
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_LLM_INFERENCE_OUTPUT)
        .build()
    )


def llm_summarization_urn(lang_code: str) -> CapUrn:
    """Build URN for summarization capability"""
    return (
        CapUrnBuilder()
        .tag("op", "summarization")
        .tag("constrained", "*")
        .tag("language", lang_code)
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_LLM_INFERENCE_OUTPUT)
        .build()
    )


# -----------------------------------------------------------------------------
# EMBEDDING URN BUILDERS
# -----------------------------------------------------------------------------


def embeddings_dimensions_urn() -> CapUrn:
    """Build URN for embeddings-dimensions capability"""
    return (
        CapUrnBuilder()
        .tag("op", "embeddings_dimensions")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_MODEL_DIM)
        .build()
    )


def embeddings_generation_urn() -> CapUrn:
    """Build URN for text embeddings-generation capability"""
    return (
        CapUrnBuilder()
        .tag("op", "generate_embeddings")
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_EMBEDDING_VECTOR)
        .build()
    )


def image_embeddings_generation_urn() -> CapUrn:
    """Build URN for image embeddings-generation capability"""
    return (
        CapUrnBuilder()
        .tag("op", "generate_image_embeddings")
        .tag("ml-model", "*")
        .tag("candle", "*")
        .in_spec(MEDIA_PNG)
        .out_spec(MEDIA_EMBEDDING_VECTOR)
        .build()
    )


# -----------------------------------------------------------------------------
# MODEL MANAGEMENT URN BUILDERS
# -----------------------------------------------------------------------------


def model_download_urn() -> CapUrn:
    """Build URN for model-download capability"""
    return (
        CapUrnBuilder()
        .tag("op", "download-model")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_DOWNLOAD_OUTPUT)
        .build()
    )


def model_list_urn() -> CapUrn:
    """Build URN for model-list capability"""
    return (
        CapUrnBuilder()
        .tag("op", "list-models")
        .in_spec(MEDIA_MODEL_REPO)
        .out_spec(MEDIA_LIST_OUTPUT)
        .build()
    )


def model_status_urn() -> CapUrn:
    """Build URN for model-status capability"""
    return (
        CapUrnBuilder()
        .tag("op", "model-status")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_STATUS_OUTPUT)
        .build()
    )


def model_contents_urn() -> CapUrn:
    """Build URN for model-contents capability"""
    return (
        CapUrnBuilder()
        .tag("op", "model-contents")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_CONTENTS_OUTPUT)
        .build()
    )


def model_availability_urn() -> CapUrn:
    """Build URN for model-availability capability"""
    return (
        CapUrnBuilder()
        .tag("op", "model-availability")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_AVAILABILITY_OUTPUT)
        .build()
    )


def model_path_urn() -> CapUrn:
    """Build URN for model-path capability"""
    return (
        CapUrnBuilder()
        .tag("op", "model-path")
        .in_spec(MEDIA_MODEL_SPEC)
        .out_spec(MEDIA_PATH_OUTPUT)
        .build()
    )


# -----------------------------------------------------------------------------
# DOCUMENT PROCESSING URN BUILDERS
# -----------------------------------------------------------------------------


def render_page_image_urn(input_media: str) -> str:
    """Build URN for render-page-image capability.

    input_media is the media URN for the input type (e.g., MEDIA_PDF).
    """
    return (
        CapUrnBuilder()
        .tag("op", "render_page_image")
        .in_spec(input_media)
        .out_spec(MEDIA_PNG)
        .build()
        .to_string()
    )


def disbind_urn(input_media: str = MEDIA_IDENTITY) -> CapUrn:
    """Build URN for disbind capability.

    input_media is the media URN for the input type (e.g., MEDIA_PDF, MEDIA_TXT).
    """
    return (
        CapUrnBuilder()
        .tag("op", "disbind")
        .in_spec(input_media)
        .out_spec(MEDIA_TEXTABLE_PAGE)
        .build()
    )


# -----------------------------------------------------------------------------
# FORMAT CONVERSION URN BUILDERS
# -----------------------------------------------------------------------------


def format_conversion_urn(in_media: str, out_media: str) -> str:
    """Build URN for a format conversion capability."""
    return (
        CapUrnBuilder()
        .tag("op", "convert_format")
        .in_spec(in_media)
        .out_spec(out_media)
        .build()
        .to_string()
    )


@dataclass
class FormatConversionPath:
    """A format conversion path with authoritative title and description."""
    in_media: str
    out_media: str
    title: str
    description: str


def all_format_conversion_paths() -> List[FormatConversionPath]:
    """All valid format conversion paths between JSON, YAML, CSV, and textable lists."""
    return [
        # JSON <-> YAML value
        FormatConversionPath(MEDIA_JSON_VALUE, MEDIA_YAML_VALUE,
            "Convert JSON Value to YAML", "Convert a JSON scalar value to YAML format"),
        FormatConversionPath(MEDIA_YAML_VALUE, MEDIA_JSON_VALUE,
            "Convert YAML Value to JSON", "Convert a YAML scalar value to JSON format"),
        # JSON <-> YAML record
        FormatConversionPath(MEDIA_JSON_RECORD, MEDIA_YAML_RECORD,
            "Convert JSON Object to YAML Mapping", "Convert a JSON object to a YAML mapping"),
        FormatConversionPath(MEDIA_YAML_RECORD, MEDIA_JSON_RECORD,
            "Convert YAML Mapping to JSON Object", "Convert a YAML mapping to a JSON object"),
        # JSON <-> YAML list
        FormatConversionPath(MEDIA_JSON_LIST, MEDIA_YAML_LIST,
            "Convert JSON Array to YAML Sequence", "Convert a JSON array to a YAML sequence"),
        FormatConversionPath(MEDIA_YAML_LIST, MEDIA_JSON_LIST,
            "Convert YAML Sequence to JSON Array", "Convert a YAML sequence to a JSON array"),
        # JSON <-> YAML list of records
        FormatConversionPath(MEDIA_JSON_LIST_RECORD, MEDIA_YAML_LIST_RECORD,
            "Convert JSON Array of Objects to YAML List of Mappings",
            "Convert a JSON array of objects to a YAML list of mappings"),
        FormatConversionPath(MEDIA_YAML_LIST_RECORD, MEDIA_JSON_LIST_RECORD,
            "Convert YAML List of Mappings to JSON Array of Objects",
            "Convert a YAML list of mappings to a JSON array of objects"),
        # JSON list of records <-> CSV
        FormatConversionPath(MEDIA_JSON_LIST_RECORD, MEDIA_CSV,
            "Convert JSON Array of Objects to CSV", "Convert a JSON array of objects to CSV format"),
        FormatConversionPath(MEDIA_CSV, MEDIA_JSON_LIST_RECORD,
            "Convert CSV to JSON Array of Objects", "Convert CSV data to a JSON array of objects"),
        # YAML list of records <-> CSV
        FormatConversionPath(MEDIA_YAML_LIST_RECORD, MEDIA_CSV,
            "Convert YAML List of Mappings to CSV", "Convert a YAML list of mappings to CSV format"),
        FormatConversionPath(MEDIA_CSV, MEDIA_YAML_LIST_RECORD,
            "Convert CSV to YAML List of Mappings", "Convert CSV data to a YAML list of mappings"),
        # Textable list <-> JSON list
        FormatConversionPath(MEDIA_TEXTABLE_LIST, MEDIA_JSON_LIST,
            "Convert Text List to JSON Array", "Convert a list of textable values to a JSON array"),
        FormatConversionPath(MEDIA_JSON_LIST, MEDIA_TEXTABLE_LIST,
            "Convert JSON Array to Text List", "Convert a JSON array to a list of textable values"),
        # Textable list <-> YAML list
        FormatConversionPath(MEDIA_TEXTABLE_LIST, MEDIA_YAML_LIST,
            "Convert Text List to YAML Sequence", "Convert a list of textable values to a YAML sequence"),
        FormatConversionPath(MEDIA_YAML_LIST, MEDIA_TEXTABLE_LIST,
            "Convert YAML Sequence to Text List", "Convert a YAML sequence to a list of textable values"),
        # Textable list <-> CSV
        FormatConversionPath(MEDIA_TEXTABLE_LIST, MEDIA_CSV,
            "Convert Text List to CSV", "Convert a list of textable values to CSV format"),
        FormatConversionPath(MEDIA_CSV, MEDIA_TEXTABLE_LIST,
            "Convert CSV to Text List", "Convert CSV data to a list of textable values"),
    ]


# -----------------------------------------------------------------------------
# TEXT PROCESSING URN BUILDERS
# -----------------------------------------------------------------------------


def structured_query_urn(lang_code: str) -> CapUrn:
    """Build URN for structured-query capability"""
    return (
        CapUrnBuilder()
        .tag("op", "query_structured")
        .tag("language", lang_code)
        .tag("constrained", "*")
        .in_spec(MEDIA_JSON_SCHEMA)
        .out_spec(MEDIA_JSON)
        .build()
    )


def make_decision_urn(lang_code: str) -> CapUrn:
    """Build URN for make-decision capability"""
    return (
        CapUrnBuilder()
        .tag("op", "make_decision")
        .tag("language", lang_code)
        .tag("constrained", "*")
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_DECISION)
        .build()
    )


def make_multiple_decisions_urn(lang_code: str) -> CapUrn:
    """Build URN for make-multiple-decisions capability"""
    return (
        CapUrnBuilder()
        .tag("op", "make_multiple_decisions")
        .tag("language", lang_code)
        .tag("constrained", "*")
        .in_spec(MEDIA_STRING)
        .out_spec(MEDIA_DECISION)
        .build()
    )


# =============================================================================
# REGISTRY LOOKUP FUNCTIONS
# =============================================================================

# -----------------------------------------------------------------------------
# FORMAT CONVERSION CAPABILITIES
# -----------------------------------------------------------------------------


async def format_conversion_cap(registry, in_media: str, out_media: str) -> Cap:
    """Get a single format conversion cap from the registry.

    Args:
        registry: CapRegistry instance
        in_media: Input media URN
        out_media: Output media URN

    Returns:
        The Cap for this format conversion

    Raises:
        RegistryError: If the cap is not found
    """
    urn = format_conversion_urn(in_media, out_media)
    return await registry.get_cap(urn)


async def all_format_conversion_caps(registry) -> List[Tuple[str, str, Cap]]:
    """Get all format conversion caps from the registry.

    Returns a list of (in_media, out_media, Cap) tuples.
    Fails if any conversion cap is missing from the registry.

    Args:
        registry: CapRegistry instance

    Returns:
        List of (in_media, out_media, Cap) tuples

    Raises:
        RegistryError: If any conversion cap is missing
    """
    caps = []
    for path in all_format_conversion_paths():
        cap = await format_conversion_cap(registry, path.in_media, path.out_media)
        caps.append((path.in_media, path.out_media, cap))
    return caps
