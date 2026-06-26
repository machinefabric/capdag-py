"""Media URN - Data type specification using tagged URN format

Media URNs use the tagged URN format with "media" prefix to describe
data types. They replace the old spec ID system (e.g., `media:string`).

Format: `media:<type>[;subtype=<subtype>][;v=<version>][;profile=<url>][;...]`

Examples:
- `media:string`
- `media:object`
- `media:application;subtype=json;profile="https://example.com/schema"`
- `media:image;subtype=png`

Media URNs are just tagged URNs with the "media" prefix. Comparison and
matching use standard tagged URN semantics.
"""

from typing import List, Optional
from tagged_urn import TaggedUrn, TaggedUrnBuilder, TaggedUrnError


# =============================================================================
# STANDARD MEDIA URN CONSTANTS
# =============================================================================

# Primitive types - URNs must match base.toml definitions
# Media URN for void (no input/output) - no coercion tags
MEDIA_VOID = "media:void"
# Media URN for string type — bare UTF-8 text (enc=utf-8), scalar by default (no list marker)
MEDIA_STRING = "media:enc=utf-8"
# Media URN for integer type — numeric (math ops valid), scalar by default
MEDIA_INTEGER = "media:integer;numeric"
# Media URN for number type — numeric, scalar by default
MEDIA_NUMBER = "media:numeric"
# Media URN for boolean type - uses "bool" not "boolean" per base.toml
MEDIA_BOOLEAN = "media:bool;enc=utf-8"
# Media URN for a generic record/object type — internal key-value structure, no content-format claim
MEDIA_OBJECT = "media:record"
# Media URN for the top type — the most general media type (no constraints)
MEDIA_IDENTITY = "media:"

# List types - URNs must match base.toml definitions
# Media URN for untyped list - ordered sequence of opaque byte sequences
MEDIA_LIST = "media:list"
# Media URN for string list type — ordered sequence of bare UTF-8 text values
MEDIA_STRING_LIST = "media:enc=utf-8;list"
# Media URN for integer list type — numeric with list marker
MEDIA_INTEGER_LIST = "media:integer;list;numeric"
# Media URN for number list type - one number per line
MEDIA_NUMBER_LIST = "media:list;numeric"
# Media URN for boolean list type - one boolean per line
MEDIA_BOOLEAN_LIST = "media:bool;enc=utf-8;list"
# Media URN for object list type - list marker, record (each item has structure)
MEDIA_OBJECT_LIST = "media:list;record"

# Semantic media types for specialized content
# Media URN for PNG image data
MEDIA_PNG = "media:ext=png;image"
# Media URN for JPEG image data
MEDIA_JPEG = "media:ext=jpeg;image"
# Media URN for GIF image data
MEDIA_GIF = "media:ext=gif;image"
# Media URN for BMP image data
MEDIA_BMP = "media:ext=bmp;image"
# Media URN for TIFF image data
MEDIA_TIFF = "media:ext=tiff;image"
# Media URN for WebP image data
MEDIA_WEBP = "media:ext=webp;image"
# Media URN for audio data (wav, mp3, flac, etc.)
MEDIA_AUDIO = "media:audio;ext=wav"
# Media URN for WAV audio data
MEDIA_WAV = "media:audio;ext=wav"
# Media URN for MP3 audio data
MEDIA_MP3 = "media:audio;ext=mp3"
# Media URN for FLAC audio data
MEDIA_FLAC = "media:audio;ext=flac"
# Media URN for OGG audio data
MEDIA_OGG = "media:audio;ext=ogg"
# Media URN for AAC audio data
MEDIA_AAC = "media:audio;ext=aac"
# Media URN for M4A audio data
MEDIA_M4A = "media:audio;ext=m4a"
# Media URN for AIFF audio data
MEDIA_AIFF = "media:audio;ext=aiff"
# Media URN for Opus audio data
MEDIA_OPUS = "media:audio;ext=opus"
# Media URN for video data (mp4, webm, mov, etc.)
MEDIA_VIDEO = "media:video"
# Media URN for MP4 video data
MEDIA_MP4 = "media:ext=mp4;video"
# Media URN for MOV video data
MEDIA_MOV = "media:ext=mov;video"
# Media URN for WebM video data
MEDIA_WEBM = "media:ext=webm;video"
# Media URN for MKV video data
MEDIA_MKV = "media:ext=mkv;video"

# Semantic AI input types - distinguished by their purpose/context
# Media URN for audio input containing speech for transcription (Whisper)
MEDIA_AUDIO_SPEECH = "media:audio;ext=wav;speech"

# Document types (PRIMARY naming - type IS the format)
# Media URN for PDF documents
MEDIA_PDF = "media:ext=pdf"
# Media URN for EPUB documents
MEDIA_EPUB = "media:ext=epub"

# Text format types (PRIMARY naming - type IS the format)
# Media URN for Markdown text
MEDIA_MD = "media:enc=utf-8;ext=md"
# Media URN for plain text
MEDIA_TXT = "media:enc=utf-8;ext=txt"
# Media URN for reStructuredText
MEDIA_RST = "media:enc=utf-8;ext=rst"
# Media URN for log files
MEDIA_LOG = "media:enc=utf-8;ext=log"
# Media URN for HTML documents
MEDIA_HTML = "media:enc=utf-8;ext=html"
# Media URN for XML documents
MEDIA_XML = "media:enc=utf-8;ext=xml"
# Media URN for JSON data - has record marker (structured key-value)
MEDIA_JSON = "media:fmt=json;record"
# Media URN for JSON with schema constraint (input for structured queries)
MEDIA_JSON_SCHEMA = "media:fmt=json;json-schema;record"
# Media URN for YAML data - has record marker (structured key-value)
MEDIA_YAML = "media:fmt=yaml;record"

# Format-specific variants for JSON, YAML, CSV
MEDIA_JSON_VALUE = "media:fmt=json"
MEDIA_JSON_RECORD = "media:fmt=json;record"
MEDIA_JSON_LIST = "media:fmt=json;list"
MEDIA_JSON_LIST_RECORD = "media:fmt=json;list;record"
MEDIA_YAML_VALUE = "media:fmt=yaml"
MEDIA_YAML_RECORD = "media:fmt=yaml;record"
MEDIA_YAML_LIST = "media:fmt=yaml;list"
MEDIA_YAML_LIST_RECORD = "media:fmt=yaml;list;record"
MEDIA_CSV = "media:fmt=csv;list;record"
MEDIA_CSV_LIST = "media:fmt=csv;list;record"

# File path type — for arguments that represent filesystem paths.
# There is a single media URN; cardinality (single file vs many) lives on
# `is_sequence`, not on URN tags.
MEDIA_FILE_PATH = "media:enc=utf-8;file-path"

# Media URN for extracted page text
MEDIA_TEXTABLE_PAGE = "media:enc=utf-8;ext=txt;page;plain-text"

# Semantic text input types - distinguished by their purpose/context
# Media URN for model spec (provider:model format, HuggingFace name, etc.)
# Generic, backend-agnostic — used by modelcartridge for download/status/path operations.
MEDIA_MODEL_SPEC = "media:enc=utf-8;model-spec"

# Backend + use-case specific model-spec variants.
# Each inference cap declares the variant matching its backend and purpose,
# so slot values can target a specific cartridge+task without ambiguity.

# GGUF backend
# GGUF vision model spec (e.g. moondream2)
MEDIA_MODEL_SPEC_GGUF_VISION = "media:enc=utf-8;gguf;model-spec;tokenizer-embedded-gguf;vision"
# GGUF LLM model spec (e.g. Mistral-7B)
MEDIA_MODEL_SPEC_GGUF_LLM = "media:enc=utf-8;gguf;llm;model-spec;tokenizer-embedded-gguf"
# GGUF embeddings model spec (e.g. nomic-embed)
MEDIA_MODEL_SPEC_GGUF_EMBEDDINGS = "media:embeddings;enc=utf-8;gguf;model-spec;tokenizer-embedded-gguf"

# MLX backend
# MLX vision model spec (e.g. Qwen3-VL)
MEDIA_MODEL_SPEC_MLX_VISION = "media:enc=utf-8;mlx;model-spec;vision"
# MLX LLM model spec (e.g. Llama-3.2-3B)
MEDIA_MODEL_SPEC_MLX_LLM = "media:enc=utf-8;llm;mlx;model-spec"
# MLX embeddings model spec (e.g. all-MiniLM-L6-v2)
MEDIA_MODEL_SPEC_MLX_EMBEDDINGS = "media:embeddings;enc=utf-8;mlx;model-spec"

# Candle backend
# Candle vision model spec (e.g. BLIP)
MEDIA_MODEL_SPEC_CANDLE_VISION = "media:candle;enc=utf-8;model-spec;repo-safetensors;tokenizer-unified;vision"
# Candle text embeddings model spec (e.g. BERT)
MEDIA_MODEL_SPEC_CANDLE_EMBEDDINGS = "media:candle;embeddings;enc=utf-8;model-spec;repo-safetensors;tokenizer-unified"
# Candle image embeddings model spec (e.g. CLIP)
MEDIA_MODEL_SPEC_CANDLE_IMAGE_EMBEDDINGS = "media:candle;enc=utf-8;image-embeddings;model-spec"
# Candle transcription model spec (e.g. Whisper)
MEDIA_MODEL_SPEC_CANDLE_TRANSCRIPTION = "media:candle;enc=utf-8;model-spec;repo-safetensors;tokenizer-unified;transcription"
# Media URN for MLX model path
MEDIA_MLX_MODEL_PATH = "media:enc=utf-8;mlx-model-path"
# Media URN for model repository (input for list-models) - matches CATALOG
MEDIA_MODEL_REPO = "media:enc=utf-8;model-repo;record"
# Media URN for HuggingFace token (secret)
MEDIA_HF_TOKEN = "media:enc=utf-8;hf-token;secret"
# Media URN for model architecture list - JSON record
MEDIA_MODEL_ARCH_LIST = "media:fmt=json;model-arch-list;record"
# Media URN for model search request - JSON record
MEDIA_MODEL_SEARCH_REQUEST = "media:fmt=json;model-search-request;record"
# Media URN for model search response - JSON record
MEDIA_MODEL_SEARCH_RESPONSE = "media:fmt=json;model-search-response;record"
# Media URN for model filter resolution - JSON record
MEDIA_MODEL_FILTER_RESOLUTION = "media:fmt=json;model-filter-resolution;record"

# CAPDAG output types - all record structures (JSON objects)
# Media URN for model dimension output - matches CATALOG
MEDIA_MODEL_DIM = "media:integer;model-dim;numeric"
# Media URN for model download output - record structure
MEDIA_DOWNLOAD_OUTPUT = "media:download-result;enc=utf-8;record"
# Media URN for model list output - record structure
MEDIA_LIST_OUTPUT = "media:enc=utf-8;model-list;record"
# Media URN for model status output - record structure
MEDIA_STATUS_OUTPUT = "media:enc=utf-8;model-status;record"
# Media URN for model contents output - record structure
MEDIA_CONTENTS_OUTPUT = "media:enc=utf-8;model-contents;record"
# Media URN for model availability output - record structure
MEDIA_AVAILABILITY_OUTPUT = "media:enc=utf-8;model-availability;record"
# Media URN for model path output - record structure
MEDIA_PATH_OUTPUT = "media:enc=utf-8;model-path;record"
# Media URN for embedding vector output - record structure
MEDIA_EMBEDDING_VECTOR = "media:embedding-vector;enc=utf-8;record"
# Media URN for vision inference output — a concrete textable terminal.
# Carries `image-description` (the vision-specific marker), `plain-text`
# (the finalised-text marker that opts into cap:save-as-txt's persistence
# path), and `ext=txt` (binds the URN to the `.txt` extension).
MEDIA_IMAGE_DESCRIPTION = "media:enc=utf-8;ext=txt;image-description;plain-text"
# Media URN for finalised plain text — the canonical input/output of cap:save-as-txt.
# Producers of user-facing prose (LLM text-generation, OCR's extracted text,
# summarisation) declare this URN as their `out` so the planner restricts the .txt
# persistence path to those caps. See fabric/media/plain-text.toml.
MEDIA_PLAIN_TEXT = "media:enc=utf-8;ext=txt;plain-text"
# Media URN for transcription output - record structure
MEDIA_TRANSCRIPTION_OUTPUT = "media:enc=utf-8;record;transcription"
# Media URN for decision output (Make Decision) - matches CATALOG
MEDIA_DECISION = "media:decision;fmt=json;record"
# Media URN for adapter selection output - JSON record
MEDIA_ADAPTER_SELECTION = "media:adapter-selection;fmt=json;record"

# Fabric registry lookup wire types (consumed/produced by cap:lookup-cap;fabric
# and cap:lookup-media-def;fabric, both implemented by fetchcartridge).
MEDIA_CAP_URN = "media:cap-urn;enc=utf-8"
MEDIA_MEDIA_URN = "media:enc=utf-8;media-urn"
MEDIA_CAP_DEFINITION = "media:cap-definition;fmt=json;record"
MEDIA_MEDIA_DEFINITION = "media:fmt=json;media-definition;record"
MEDIA_FABRIC_DEFVER = "media:defver;enc=utf-8"


# Helper functions to build media URNs. The extension is carried on
# the keyed `ext=<value>` axis so that `MediaUrn.extension()` (which
# looks up the `ext` tag) resolves correctly.
def file_media_urn_for_ext(ext: str) -> str:
    """Helper to build a bare file media URN for a given extension — a file of
    the given type with no content-format or encoding claim (e.g. media:ext=pdf)."""
    return f"media:ext={ext}"


def text_media_urn_for_ext(ext: str) -> str:
    """Helper to build a UTF-8 text file media URN for a given extension
    (e.g. media:enc=utf-8;ext=md)."""
    return f"media:enc=utf-8;ext={ext}"


def image_media_urn_for_ext(ext: str) -> str:
    """Helper to build image media URN with extension"""
    return f"media:ext={ext};image"


def audio_media_urn_for_ext(ext: str) -> str:
    """Helper to build audio media URN with extension"""
    return f"media:audio;ext={ext}"


# =============================================================================
# MEDIA URN TYPE
# =============================================================================

class MediaUrnError(Exception):
    """Base exception for media URN errors"""
    pass


class MediaUrnCoordinateDelta:
    def __init__(self, inner):
        self.inner = inner


class MediaUrn:
    """A media URN representing a data type specification

    Media URNs are tagged URNs with the "media" prefix. They describe data
    types using tags like `type`, `subtype`, `v` (version), and `profile`.

    This is a newtype wrapper around `TaggedUrn` that enforces the "media"
    prefix and provides convenient accessors for common tags.
    """

    PREFIX = "media"

    def __init__(self, urn: TaggedUrn):
        """Create a new MediaUrn from a TaggedUrn.

        Raises MediaUrnError if:
        - The TaggedUrn doesn't have the "media" prefix.
        - The ``void`` marker tag is combined with any other tag.
          ``media:void`` is the type-theoretic unit ``()`` and admits
          no refinements; reasons or labels belong on cap-tags or
          args, not as media URN tags.
        """
        if urn.get_prefix() != self.PREFIX:
            raise MediaUrnError(
                f"Invalid prefix: expected '{self.PREFIX}', got '{urn.get_prefix()}'"
            )
        if "void" in urn.tags and len(urn.tags) > 1:
            extras = sorted(k for k in urn.tags if k != "void")
            raise MediaUrnError(
                "media:void is atomic and cannot be refined; got extra tag(s): "
                f"{', '.join(extras)}. Move why/how this void is used into "
                "cap-tags or args, not the media URN."
            )
        self._urn = urn

    @classmethod
    def from_string(cls, s: str) -> "MediaUrn":
        """Create a MediaUrn from a string representation

        The string must be a valid tagged URN with the "media" prefix.
        Whitespace and empty input validation is handled by TaggedUrn.from_string.
        """
        urn = TaggedUrn.from_string(s)
        return cls(urn)

    def inner(self) -> TaggedUrn:
        """Get the inner TaggedUrn"""
        return self._urn

    def get_tag(self, key: str) -> Optional[str]:
        """Get any tag value by key"""
        return self._urn.get_tag(key)

    def has_tag(self, key: str, value: str) -> bool:
        """Check if this media URN has a specific tag"""
        return self._urn.has_tag(key, value)

    def with_tag(self, key: str, value: str) -> "MediaUrn":
        """Create a new MediaUrn with an additional or updated tag"""
        new_urn = self._urn.with_tag(key, value)
        return MediaUrn(new_urn)

    def without_tag(self, key: str) -> "MediaUrn":
        """Create a new MediaUrn without a specific tag"""
        new_urn = self._urn.without_tag(key)
        return MediaUrn(new_urn)

    @staticmethod
    def least_upper_bound(urns: "List[MediaUrn]") -> "MediaUrn":
        """Compute the least upper bound (most specific common type) of a set of MediaUrns.

        Returns the MediaUrn whose tag set is the intersection of all input tag sets:
        only tags present in ALL inputs with matching values are kept.

        - Empty input -> media: (universal type)
        - Single input -> returned as-is
        - [media:ext=pdf, media:ext=pdf] -> media:ext=pdf
        - [media:ext=pdf, media:ext=png;image] -> media: (no common tags)
        - [media:fmt=json, media:fmt=csv] -> media:enc=utf-8
        """
        from tagged_urn import TaggedUrn

        if not urns:
            return MediaUrn.from_string("media:")

        if len(urns) == 1:
            return urns[0]

        # Start with the first URN's tags, intersect with each subsequent URN
        common_tags = dict(urns[0]._urn.tags)

        for urn in urns[1:]:
            common_tags = {
                key: value
                for key, value in common_tags.items()
                if urn._urn.tags.get(key) == value
            }

        result_urn = TaggedUrn("media", common_tags)
        return MediaUrn(result_urn)

    def tags_to_string(self) -> str:
        """Serialize just the tags portion (without "media:" prefix)

        Returns tags in canonical form with proper quoting and sorting.
        """
        return self._urn.tags_to_string()

    def to_string(self) -> str:
        """Get the canonical string representation"""
        return self._urn.to_string()

    def conforms_to(self, pattern: "MediaUrn") -> bool:
        """Check if this media URN (instance) satisfies the pattern's constraints.

        An instance conforms to a pattern when the instance has all tags
        required by the pattern. Missing tags in the pattern are wildcards.
        Equivalent to pattern.accepts(self).
        """
        return self._urn.conforms_to(pattern._urn)

    def accepts(self, instance: "MediaUrn") -> bool:
        """Check if this media URN (pattern) accepts the given instance.

        A pattern accepts an instance when the instance has all tags
        required by the pattern. Missing tags in the pattern are wildcards.
        Equivalent to instance.conforms_to(self).
        """
        return self._urn.accepts(instance._urn)

    def is_comparable(self, other: "MediaUrn") -> bool:
        """Check if two media URNs are comparable in the order-theoretic sense.

        Two URNs are comparable if either one accepts (subsumes) the other.
        This is the symmetric closure of the accepts relation.
        Use for discovery/validation: are they on the same specialization chain?
        """
        return self.accepts(other) or other.accepts(self)

    def is_equivalent(self, other: "MediaUrn") -> bool:
        """Check if two media URNs are equivalent in the order-theoretic sense.

        Two URNs are equivalent if each accepts (subsumes) the other.
        This means they have the same tag set (order-independent equality).
        Use for exact stream matching.
        """
        return self.accepts(other) and other.accepts(self)

    def specificity(self) -> int:
        """Get the specificity of this media URN

        Specificity is calculated from tag values (not just count).
        """
        return self._urn.specificity()

    def delta_from(self, base: "MediaUrn") -> MediaUrnCoordinateDelta:
        if base is None:
            raise MediaUrnError("cannot derive delta from null base media URN")
        return MediaUrnCoordinateDelta(self._urn.delta_from(base._urn))

    def apply_delta(self, delta: MediaUrnCoordinateDelta) -> "MediaUrn":
        if delta is None:
            raise MediaUrnError("cannot apply null media delta")
        next_urn = self._urn.apply_delta(delta.inner)
        return MediaUrn(next_urn)

    def has_marker_tag(self, tag_name: str) -> bool:
        """Check if a marker tag is present (has wildcard value).

        Marker tags are tags with wildcard values (*) that indicate
        boolean-like properties of the media type.
        """
        return self._urn.tags.get(tag_name) == "*"

    def is_scalar(self) -> bool:
        """Check if this media URN represents a single value (not a list).
        Returns True if the "list" marker tag is NOT present."""
        return not self.has_marker_tag("list")

    def is_list(self) -> bool:
        """Check if this media URN has list as a semantic data format tag.
        This is a semantic type check about data format, NOT cardinality.
        Returns True if the "list" marker tag is present."""
        return self.has_marker_tag("list")

    def is_record(self) -> bool:
        """Check if this media URN has internal record structure (key-value pairs).
        Returns True if the "record" marker tag is present."""
        return self.has_marker_tag("record")

    def is_opaque(self) -> bool:
        """Check if this media URN has no recognized internal structure.
        Returns True if the "record" marker tag is NOT present."""
        return not self.has_marker_tag("record")

    def is_json(self) -> bool:
        """Check if this value's content format is JSON (fmt=json)."""
        return self._urn.get_tag("fmt") == "json"

    def is_yaml(self) -> bool:
        """Check if this value's content format is YAML (fmt=yaml)."""
        return self._urn.get_tag("fmt") == "yaml"

    def is_csv(self) -> bool:
        """Check if this value's content format is CSV (fmt=csv)."""
        return self._urn.get_tag("fmt") == "csv"

    def is_image(self) -> bool:
        """Check if this represents image data.
        Returns true if the "image" marker tag is present.
        """
        return self._urn.get_tag("image") is not None

    def is_audio(self) -> bool:
        """Check if this represents audio data.
        Returns true if the "audio" marker tag is present.
        """
        return self._urn.get_tag("audio") is not None

    def is_video(self) -> bool:
        """Check if this represents video data.
        Returns true if the "video" marker tag is present.
        """
        return self._urn.get_tag("video") is not None

    def is_numeric(self) -> bool:
        """Check if this represents numeric data.
        Returns true if the "numeric" marker tag is present.
        """
        return self._urn.get_tag("numeric") is not None

    def is_bool(self) -> bool:
        """Check if this represents boolean data.
        Returns true if the "bool" marker tag is present.
        """
        return self._urn.get_tag("bool") is not None

    def is_void(self) -> bool:
        """Check if this represents a void (no data) type — the
        **unit type** in the type-theoretic reading. ``media:void`` is
        the nullary value; a cap with ``media:void`` on a side has no
        meaningful data on that side. NOT "invalid" or "absent".
        """
        # Check for "void" marker tag
        return "void" in self._urn.tags

    def is_top(self) -> bool:
        """True if this is the **top** media URN — the universal
        wildcard ``media:`` with no tags. Order-theoretically, every
        other media URN ``conforms_to`` this one. Distinct from
        ``is_void``: top means "any data type accepted here," void
        means "no data flows here."
        """
        return len(self._urn.tags) == 0

    def is_file_path(self) -> bool:
        """True if this URN specializes `media:file-path`.

        There is a single file-path media URN; cardinality (single file vs
        many files) is carried on the wire via `is_sequence`, not via URN
        tags. Callers deciding scalar-vs-sequence must look at the arg
        definition's `is_sequence` flag instead.
        """
        return self.has_marker_tag("file-path")

    def extension(self) -> Optional[str]:
        """Get the extension tag value if present"""
        return self._urn.get_tag("ext")

    def __str__(self) -> str:
        return self.to_string()

    def __repr__(self) -> str:
        return f"MediaUrn('{self.to_string()}')"

    def _cmp_key(self) -> tuple:
        return (self._urn.prefix, tuple(sorted(self._urn.tags.items())))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MediaUrn):
            return False
        return self._urn == other._urn

    def __hash__(self) -> int:
        return hash(self._urn)
