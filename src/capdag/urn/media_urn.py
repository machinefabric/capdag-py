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
# Media URN for string type - textable (can become text), scalar by default (no list marker)
MEDIA_STRING = "media:textable"
# Media URN for integer type - textable, numeric (math ops valid), scalar by default
MEDIA_INTEGER = "media:integer;textable;numeric"
# Media URN for number type - textable, numeric, scalar by default (no primary type prefix)
MEDIA_NUMBER = "media:textable;numeric"
# Media URN for boolean type - uses "bool" not "boolean" per base.toml
MEDIA_BOOLEAN = "media:bool;textable"
# Media URN for JSON object type - record (key-value structure), textable (via JSON.stringify)
MEDIA_OBJECT = "media:record"
# Media URN for binary data (wildcard - matches everything)
MEDIA_IDENTITY = "media:"

# List types - URNs must match base.toml definitions
# Media URN for untyped list - ordered sequence of opaque byte sequences
MEDIA_LIST = "media:list"
# Media URN for textable list - ordered sequence of textable values
MEDIA_TEXTABLE_LIST = "media:list;textable"
# Media URN for string list type - list marker, textable (no primary type prefix)
MEDIA_STRING_LIST = "media:list;textable"
# Media URN for integer list type - list marker, integer, numeric, textable (per base.toml:46)
MEDIA_INTEGER_LIST = "media:integer;list;textable;numeric"
# Media URN for number list type - list marker, numeric, textable (no primary type prefix)
MEDIA_NUMBER_LIST = "media:list;numeric;textable"
# Media URN for boolean list type - list marker, bool, textable (uses "bool" not "boolean" per base.toml)
MEDIA_BOOLEAN_LIST = "media:bool;list;textable"
# Media URN for object list type - list marker, record (each item has structure)
MEDIA_OBJECT_LIST = "media:list;record"

# Semantic media types for specialized content
# Media URN for PNG image data
MEDIA_PNG = "media:image;png"
# Media URN for JPEG image data
MEDIA_JPEG = "media:jpeg;image"
# Media URN for GIF image data
MEDIA_GIF = "media:gif;image"
# Media URN for BMP image data
MEDIA_BMP = "media:bmp;image"
# Media URN for TIFF image data
MEDIA_TIFF = "media:tiff;image"
# Media URN for WebP image data
MEDIA_WEBP = "media:webp;image"
# Media URN for audio data (wav, mp3, flac, etc.)
MEDIA_AUDIO = "media:wav;audio"
# Media URN for WAV audio data
MEDIA_WAV = "media:wav;audio"
# Media URN for MP3 audio data
MEDIA_MP3 = "media:mp3;audio"
# Media URN for FLAC audio data
MEDIA_FLAC = "media:flac;audio"
# Media URN for OGG audio data
MEDIA_OGG = "media:ogg;audio"
# Media URN for AAC audio data
MEDIA_AAC = "media:aac;audio"
# Media URN for M4A audio data
MEDIA_M4A = "media:m4a;audio"
# Media URN for AIFF audio data
MEDIA_AIFF = "media:aiff;audio"
# Media URN for Opus audio data
MEDIA_OPUS = "media:opus;audio"
# Media URN for video data (mp4, webm, mov, etc.)
MEDIA_VIDEO = "media:video"
# Media URN for MP4 video data
MEDIA_MP4 = "media:mp4;video"
# Media URN for MOV video data
MEDIA_MOV = "media:mov;video"
# Media URN for WebM video data
MEDIA_WEBM = "media:webm;video"
# Media URN for MKV video data
MEDIA_MKV = "media:mkv;video"

# Semantic AI input types - distinguished by their purpose/context
# Media URN for audio input containing speech for transcription (Whisper)
MEDIA_AUDIO_SPEECH = "media:audio;wav;speech"

# Document types (PRIMARY naming - type IS the format)
# Media URN for PDF documents
MEDIA_PDF = "media:pdf"
# Media URN for EPUB documents
MEDIA_EPUB = "media:epub"

# Text format types (PRIMARY naming - type IS the format)
# Media URN for Markdown text
MEDIA_MD = "media:md;textable"
# Media URN for plain text
MEDIA_TXT = "media:txt;textable"
# Media URN for reStructuredText
MEDIA_RST = "media:rst;textable"
# Media URN for log files
MEDIA_LOG = "media:log;textable"
# Media URN for HTML documents
MEDIA_HTML = "media:html;textable"
# Media URN for XML documents
MEDIA_XML = "media:xml;textable"
# Media URN for JSON data
MEDIA_JSON = "media:json;record;textable"
# Media URN for JSON with schema constraint (input for structured queries) - matches CATALOG
MEDIA_JSON_SCHEMA = "media:json;json-schema;record;textable"
# Media URN for YAML data
MEDIA_YAML = "media:record;textable;yaml"

# Format-specific variants for JSON, YAML, CSV
MEDIA_JSON_VALUE = "media:json;textable"
MEDIA_JSON_RECORD = "media:json;record;textable"
MEDIA_JSON_LIST = "media:json;list;textable"
MEDIA_JSON_LIST_RECORD = "media:json;list;record;textable"
MEDIA_YAML_VALUE = "media:textable;yaml"
MEDIA_YAML_RECORD = "media:record;textable;yaml"
MEDIA_YAML_LIST = "media:list;textable;yaml"
MEDIA_YAML_LIST_RECORD = "media:list;record;textable;yaml"
MEDIA_CSV = "media:csv;list;record;textable"
MEDIA_CSV_LIST = "media:csv;list;record;textable"

# File path type — for arguments that represent filesystem paths.
# There is a single media URN; cardinality (single file vs many) lives on
# `is_sequence`, not on URN tags.
MEDIA_FILE_PATH = "media:file-path;textable"

# Media URN for extracted page text
MEDIA_TEXTABLE_PAGE = "media:page;plain-text;textable;txt"

# Semantic text input types - distinguished by their purpose/context
# Media URN for model spec (provider:model format, HuggingFace name, etc.)
# Generic, backend-agnostic — used by modelcartridge for download/status/path operations.
MEDIA_MODEL_SPEC = "media:model-spec;textable"

# Backend + use-case specific model-spec variants.
# Each inference cap declares the variant matching its backend and purpose,
# so slot values can target a specific cartridge+task without ambiguity.

# GGUF backend
# GGUF vision model spec (e.g. moondream2)
MEDIA_MODEL_SPEC_GGUF_VISION = "media:model-spec;gguf;textable;vision"
# GGUF LLM model spec (e.g. Mistral-7B)
MEDIA_MODEL_SPEC_GGUF_LLM = "media:model-spec;gguf;textable;llm"
# GGUF embeddings model spec (e.g. nomic-embed)
MEDIA_MODEL_SPEC_GGUF_EMBEDDINGS = "media:model-spec;gguf;textable;embeddings"

# MLX backend
# MLX vision model spec (e.g. Qwen3-VL)
MEDIA_MODEL_SPEC_MLX_VISION = "media:model-spec;mlx;textable;vision"
# MLX LLM model spec (e.g. Llama-3.2-3B)
MEDIA_MODEL_SPEC_MLX_LLM = "media:model-spec;mlx;textable;llm"
# MLX embeddings model spec (e.g. all-MiniLM-L6-v2)
MEDIA_MODEL_SPEC_MLX_EMBEDDINGS = "media:model-spec;mlx;textable;embeddings"

# Candle backend
# Candle vision model spec (e.g. BLIP)
MEDIA_MODEL_SPEC_CANDLE_VISION = "media:model-spec;candle;textable;vision"
# Candle text embeddings model spec (e.g. BERT)
MEDIA_MODEL_SPEC_CANDLE_EMBEDDINGS = "media:model-spec;candle;textable;embeddings"
# Candle image embeddings model spec (e.g. CLIP)
MEDIA_MODEL_SPEC_CANDLE_IMAGE_EMBEDDINGS = "media:model-spec;candle;image-embeddings;textable"
# Candle transcription model spec (e.g. Whisper)
MEDIA_MODEL_SPEC_CANDLE_TRANSCRIPTION = "media:model-spec;candle;textable;transcription"
# Media URN for MLX model path
MEDIA_MLX_MODEL_PATH = "media:mlx-model-path;textable"
# Media URN for model repository (input for list-models) - matches CATALOG
MEDIA_MODEL_REPO = "media:model-repo;record;textable"
# Media URN for HuggingFace token (secret, textable)
MEDIA_HF_TOKEN = "media:hf-token;secret;textable"
# Media URN for model architecture list - JSON record, textable
MEDIA_MODEL_ARCH_LIST = "media:model-arch-list;json;record;textable"
# Media URN for model search request - JSON record, textable
MEDIA_MODEL_SEARCH_REQUEST = "media:model-search-request;json;record;textable"
# Media URN for model search response - JSON record, textable
MEDIA_MODEL_SEARCH_RESPONSE = "media:model-search-response;json;record;textable"
# Media URN for model filter resolution - JSON record, textable
MEDIA_MODEL_FILTER_RESOLUTION = "media:model-filter-resolution;json;record;textable"

# CAPDAG output types - all record structures (JSON objects)
# Media URN for model dimension output - matches CATALOG
MEDIA_MODEL_DIM = "media:integer;model-dim;numeric;textable"
# Media URN for model download output - record structure
MEDIA_DOWNLOAD_OUTPUT = "media:download-result;record;textable"
# Media URN for model list output - record structure
MEDIA_LIST_OUTPUT = "media:model-list;record;textable"
# Media URN for model status output - record structure
MEDIA_STATUS_OUTPUT = "media:model-status;record;textable"
# Media URN for model contents output - record structure
MEDIA_CONTENTS_OUTPUT = "media:model-contents;record;textable"
# Media URN for model availability output - record structure
MEDIA_AVAILABILITY_OUTPUT = "media:model-availability;record;textable"
# Media URN for model path output - record structure
MEDIA_PATH_OUTPUT = "media:model-path;record;textable"
# Media URN for embedding vector output - record structure
MEDIA_EMBEDDING_VECTOR = "media:embedding-vector;record;textable"
# Media URN for vision inference output — a concrete textable terminal.
# Carries `image-description` (the vision-specific marker), `plain-text`
# (the finalised-text marker that opts into cap:save-as-txt's persistence
# path), and `file-type=txt` (binds the URN to the `.txt` extension).
MEDIA_IMAGE_DESCRIPTION = "media:image-description;plain-text;textable;txt"
# Media URN for finalised plain text — the canonical input/output of cap:save-as-txt.
# Producers of user-facing prose (LLM text-generation, OCR's extracted text,
# summarisation) declare this URN as their `out` so the planner restricts the .txt
# persistence path to those caps. See fabric/media/plain-text.toml.
MEDIA_PLAIN_TEXT = "media:plain-text;textable;txt"
# Media URN for transcription output - record structure
MEDIA_TRANSCRIPTION_OUTPUT = "media:record;textable;transcription"
# Media URN for decision output (Make Decision) - matches CATALOG
MEDIA_DECISION = "media:decision;json;record;textable"
# Media URN for adapter selection output - JSON record
MEDIA_ADAPTER_SELECTION = "media:adapter-selection;json;record"

# Fabric registry lookup wire types (consumed/produced by cap:lookup-cap;fabric
# and cap:lookup-media-spec;fabric, both implemented by fetchcartridge).
MEDIA_CAP_URN = "media:cap-urn;textable"
MEDIA_MEDIA_URN = "media:media-urn;textable"
MEDIA_CAP_DEFINITION = "media:cap-definition;json;record;textable"
MEDIA_MEDIA_SPEC_DEFINITION = "media:media-spec-definition;json;record;textable"


# Helper functions to build media URNs
def binary_media_urn_for_ext(ext: str) -> str:
    """Helper to build binary media URN with extension"""
    return f"media:binary;ext={ext}"


def text_media_urn_for_ext(ext: str) -> str:
    """Helper to build text media URN with extension"""
    return f"media:ext={ext};textable"


def image_media_urn_for_ext(ext: str) -> str:
    """Helper to build image media URN with extension"""
    return f"media:image;ext={ext}"


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
        - [media:pdf, media:pdf] -> media:pdf
        - [media:pdf, media:image;png] -> media: (no common tags)
        - [media:json;textable, media:csv;textable] -> media:textable
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

    def is_binary(self) -> bool:
        """Check if this represents binary (non-text) data.
        Returns True if the "textable" marker tag is NOT present."""
        tag_val = self._urn.get_tag("textable")
        return tag_val is None

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
        """Check if this media URN represents JSON data (json marker tag)"""
        tag_val = self._urn.get_tag("json")
        return tag_val is not None

    def is_yaml(self) -> bool:
        """Check if this media URN represents YAML data (yaml marker tag)"""
        return self.has_marker_tag("yaml")

    def is_csv(self) -> bool:
        """Check if this media URN represents CSV data (csv marker tag)"""
        return self.has_marker_tag("csv")

    def is_text(self) -> bool:
        """Check if this media URN represents textable data (textable marker tag)"""
        tag_val = self._urn.get_tag("textable")
        return tag_val is not None

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
