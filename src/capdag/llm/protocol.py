"""LLM protocol types.

Canonical Python types matching the capdag media-def schemas for LLM
operations. The Rust ``capdag-cartridge-sdk`` is the reference; these types
carry the same field names, the same defaults and the same wire form, because
the wire form is the contract — a cartridge written in Python answers the same
cap as one written in Rust, and the engine cannot tell them apart.

Media defs:

- ``media:fmt=json;llm-generation-request;record``
- ``media:fmt=ndjson;llm-text-stream``
- ``media:fmt=json;llm-vocab-response;record``
- ``media:fmt=json;llm-model-info;record``

Caps:

- ``cap:op=llm_inference`` — text generation
- ``cap:op=llm_inference_constrained`` — constrained generation with LLGuidance
- ``cap:op=llm_vocab`` — vocabulary extraction
- ``cap:op=llm_model_info`` — model info query

# Absent fields are absent, not null

Every optional field serializes only when it is set, exactly as the reference's
``skip_serializing_if`` does. A ``"temperature": null`` on the wire is not the
same document as one with no temperature at all: the receiving side reads the
first as "the caller chose null" and the second as "the caller chose nothing",
and only the second falls through to the model's own default.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = [
    "REQUEST_TYPE_GENERATE",
    "REQUEST_TYPE_GET_VOCAB",
    "REQUEST_TYPE_GET_INFO",
    "REQUEST_TYPES",
    "LlmGenerationRequest",
    "ConstraintSpec",
    "ToolDefinition",
    "LlmStreamMessage",
    "LlmVocabResponse",
    "LlmModelInfo",
    "FINISH_REASON_STOP",
    "FINISH_REASON_LENGTH",
    "FINISH_REASON_INTERRUPTED",
    "FINISH_REASON_CONSTRAINT_SATISFIED",
    "MEDIA_LLM_GENERATION_REQUEST",
    "MEDIA_LLM_TEXT_STREAM",
    "MEDIA_LLM_VOCAB_RESPONSE",
    "MEDIA_LLM_MODEL_INFO_RESPONSE",
    "CAP_LLM_INFERENCE_GGUF",
    "CAP_LLM_INFERENCE_MLX",
    "CAP_LLM_INFERENCE_CANDLE",
    "CAP_LLM_INFERENCE_CONSTRAINED",
    "CAP_LLM_VOCAB",
    "CAP_LLM_MODEL_INFO",
    "CAP_GENERATE_EMBEDDINGS",
    "CAP_EMBEDDINGS_DIMENSIONS",
    "CAP_DESCRIBE_IMAGE",
    "BACKEND_GGUF",
    "BACKEND_MLX",
    "BACKEND_CANDLE",
    "backend_for_model_spec",
]


# =============================================================================
# Request type (optional discriminator)
# =============================================================================

#: Type of LLM request — used when a single command handles several operations.
#: Prefer a different cap per operation where that is possible.
REQUEST_TYPE_GENERATE = "generate"
REQUEST_TYPE_GET_VOCAB = "get_vocab"
REQUEST_TYPE_GET_INFO = "get_info"

REQUEST_TYPES = (
    REQUEST_TYPE_GENERATE,
    REQUEST_TYPE_GET_VOCAB,
    REQUEST_TYPE_GET_INFO,
)


def _present(mapping: dict[str, Any]) -> dict[str, Any]:
    """Drop the keys whose value is unset.

    The one place the "absent, not null" rule is applied, so no type has to
    remember it.
    """
    return {key: value for key, value in mapping.items() if value is not None}


def _dumps(record: Any) -> str:
    """Serialize the way every other mirror does: compact, no spaces.

    An NDJSON stream is read a line at a time by four implementations, and one
    of them writing `{"type": "token"}` where the others write
    `{"type":"token"}` is a difference that shows up in byte-equal comparisons
    (lineage's reuse check is one) long before anybody looks at the JSON.
    """
    return json.dumps(record, separators=(",", ":"))


# =============================================================================
# media:fmt=json;llm-generation-request;record
# =============================================================================


@dataclass
class LlmGenerationRequest:
    """LLM generation request — the input to every LLM cap.

    Matches ``media:fmt=json;llm-generation-request;record``.
    """

    prompt: str
    model_spec: str
    request_type: Optional[str] = None
    system_prompt: Optional[str] = None
    request_id: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_k: Optional[int] = None
    top_p: Optional[float] = None
    min_p: Optional[float] = None
    seed: Optional[int] = None
    grammar: Optional[str] = None
    json_schema: Optional[Any] = None
    constraint: Optional["ConstraintSpec"] = None
    chat_template: Optional[str] = None
    stop_sequences: Optional[list[str]] = None
    max_context_length: Optional[int] = None
    batch_size: Optional[int] = None
    rope_freq_base: Optional[float] = None
    rope_freq_scale: Optional[float] = None
    repeat_penalty: Optional[float] = None
    #: HuggingFace bearer token, forwarded to modelcartridge for the download
    #: this request triggers. Required for a gated repository — without it the
    #: download fails hard with an authentication error rather than silently
    #: producing nothing.
    hf_token: Optional[str] = None

    @classmethod
    def with_defaults(cls, prompt: str, model_spec: str) -> "LlmGenerationRequest":
        """A request carrying the system's sampling defaults.

        The numbers are the reference's, value for value. They are stated here
        rather than left to the model because a request that omits them is a
        request whose output depends on which backend answered it.
        """
        return cls(
            prompt=prompt,
            model_spec=model_spec,
            request_type=REQUEST_TYPE_GENERATE,
            max_tokens=512,
            temperature=0.7,
            top_k=40,
            top_p=0.9,
            min_p=0.05,
            seed=42,
            # 0 = auto-size the context to prompt + max_tokens, capped at the
            # model's trained context.
            max_context_length=0,
            batch_size=2048,
            rope_freq_base=10000.0,
            rope_freq_scale=1.0,
            repeat_penalty=1.1,
        )

    @property
    def effective_request_type(self) -> str:
        """The request type, defaulting to generation when unset."""
        return self.request_type or REQUEST_TYPE_GENERATE

    def to_dict(self) -> dict[str, Any]:
        return _present(
            {
                "prompt": self.prompt,
                "model_spec": self.model_spec,
                "request_type": self.request_type,
                "system_prompt": self.system_prompt,
                "request_id": self.request_id,
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "top_k": self.top_k,
                "top_p": self.top_p,
                "min_p": self.min_p,
                "seed": self.seed,
                "grammar": self.grammar,
                "json_schema": self.json_schema,
                "constraint": self.constraint.to_dict() if self.constraint else None,
                "chat_template": self.chat_template,
                "stop_sequences": self.stop_sequences,
                "max_context_length": self.max_context_length,
                "batch_size": self.batch_size,
                "rope_freq_base": self.rope_freq_base,
                "rope_freq_scale": self.rope_freq_scale,
                "repeat_penalty": self.repeat_penalty,
                "hf_token": self.hf_token,
            }
        )

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "LlmGenerationRequest":
        constraint = record.get("constraint")
        return cls(
            prompt=record["prompt"],
            model_spec=record["model_spec"],
            request_type=record.get("request_type"),
            system_prompt=record.get("system_prompt"),
            request_id=record.get("request_id"),
            max_tokens=record.get("max_tokens"),
            temperature=record.get("temperature"),
            top_k=record.get("top_k"),
            top_p=record.get("top_p"),
            min_p=record.get("min_p"),
            seed=record.get("seed"),
            grammar=record.get("grammar"),
            json_schema=record.get("json_schema"),
            constraint=ConstraintSpec.from_dict(constraint) if constraint else None,
            chat_template=record.get("chat_template"),
            stop_sequences=record.get("stop_sequences"),
            max_context_length=record.get("max_context_length"),
            batch_size=record.get("batch_size"),
            rope_freq_base=record.get("rope_freq_base"),
            rope_freq_scale=record.get("rope_freq_scale"),
            repeat_penalty=record.get("repeat_penalty"),
            hf_token=record.get("hf_token"),
        )

    def to_json(self) -> str:
        return _dumps(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "LlmGenerationRequest":
        return cls.from_dict(json.loads(text))


@dataclass
class ToolDefinition:
    """A tool a constrained generation may call."""

    name: str
    description: str
    #: JSON Schema for the tool's parameters.
    parameters: Any

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ToolDefinition":
        return cls(
            name=record["name"],
            description=record["description"],
            parameters=record["parameters"],
        )


@dataclass
class ConstraintSpec:
    """A constraint on generation, tagged by ``type`` on the wire.

    One class rather than four, with the payload held per kind: the wire form
    is an internally-tagged union, and Python's own way of spelling that — a
    class hierarchy — would put the tag in two places (the class and the
    ``type`` field) with nothing keeping them in step.
    """

    #: ``json_schema`` | ``regex`` | ``grammar`` | ``tool_call``
    type: str
    schema: Optional[Any] = None
    pattern: Optional[str] = None
    grammar: Optional[str] = None
    tools: Optional[list[ToolDefinition]] = None
    description: Optional[str] = None

    @classmethod
    def json_schema(cls, schema: Any, description: Optional[str] = None) -> "ConstraintSpec":
        return cls(type="json_schema", schema=schema, description=description)

    @classmethod
    def regex(cls, pattern: str, description: Optional[str] = None) -> "ConstraintSpec":
        return cls(type="regex", pattern=pattern, description=description)

    @classmethod
    def grammar_spec(cls, grammar: str, description: Optional[str] = None) -> "ConstraintSpec":
        return cls(type="grammar", grammar=grammar, description=description)

    @classmethod
    def tool_call(
        cls, tools: list[ToolDefinition], description: Optional[str] = None
    ) -> "ConstraintSpec":
        return cls(type="tool_call", tools=tools, description=description)

    def to_dict(self) -> dict[str, Any]:
        if self.type == "json_schema":
            body: dict[str, Any] = {"schema": self.schema}
        elif self.type == "regex":
            body = {"pattern": self.pattern}
        elif self.type == "grammar":
            body = {"grammar": self.grammar}
        elif self.type == "tool_call":
            body = {"tools": [tool.to_dict() for tool in self.tools or []]}
        else:
            raise ValueError(
                f"unknown constraint type {self.type!r} "
                "(expected one of: json_schema, regex, grammar, tool_call)"
            )
        return _present({"type": self.type, **body, "description": self.description})

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "ConstraintSpec":
        kind = record.get("type")
        if kind == "json_schema":
            return cls.json_schema(record["schema"], record.get("description"))
        if kind == "regex":
            return cls.regex(record["pattern"], record.get("description"))
        if kind == "grammar":
            return cls.grammar_spec(record["grammar"], record.get("description"))
        if kind == "tool_call":
            tools = [ToolDefinition.from_dict(tool) for tool in record.get("tools", [])]
            return cls.tool_call(tools, record.get("description"))
        raise ValueError(
            f"unknown constraint type {kind!r} "
            "(expected one of: json_schema, regex, grammar, tool_call)"
        )


# =============================================================================
# media:fmt=ndjson;llm-text-stream
# =============================================================================


@dataclass
class LlmStreamMessage:
    """One NDJSON line of ``media:fmt=ndjson;llm-text-stream``.

    Tagged by ``type``; every variant here is mandated by the media def.
    """

    #: ``token`` | ``status`` | ``complete`` | ``tool_request`` | ``error``
    type: str
    fields: dict[str, Any] = field(default_factory=dict)

    # --- constructors, one per variant -------------------------------------

    @classmethod
    def token(cls, text: str) -> "LlmStreamMessage":
        return cls(type="token", fields={"text": text})

    @classmethod
    def status(
        cls,
        operation: str,
        details: Optional[str] = None,
        progress: Optional[float] = None,
    ) -> "LlmStreamMessage":
        return cls(
            type="status",
            fields=_present(
                {"operation": operation, "details": details, "progress": progress}
            ),
        )

    @classmethod
    def complete(
        cls,
        generated_text: str,
        tokens_generated: int,
        prompt_tokens: int,
        finish_reason: str,
        generation_time_ms: int,
    ) -> "LlmStreamMessage":
        return cls(
            type="complete",
            fields={
                "generated_text": generated_text,
                "tokens_generated": tokens_generated,
                "prompt_tokens": prompt_tokens,
                "finish_reason": finish_reason,
                "generation_time_ms": generation_time_ms,
            },
        )

    @classmethod
    def tool_request(
        cls, partial_text: str, tool_name: str, tool_args: Any
    ) -> "LlmStreamMessage":
        return cls(
            type="tool_request",
            fields={
                "partial_text": partial_text,
                "tool_name": tool_name,
                "tool_args": tool_args,
            },
        )

    @classmethod
    def error(cls, code: str, message: str) -> "LlmStreamMessage":
        return cls(type="error", fields={"code": code, "message": message})

    # --- accessors ---------------------------------------------------------

    def __getitem__(self, key: str) -> Any:
        return self.fields[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.fields.get(key, default)

    # --- wire form ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, **self.fields}

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "LlmStreamMessage":
        body = dict(record)
        kind = body.pop("type", None)
        if not isinstance(kind, str):
            raise ValueError("a stream message must carry a string `type` field")
        return cls(type=kind, fields=body)

    def to_line(self) -> str:
        """One NDJSON line, with no trailing newline."""
        return _dumps(self.to_dict())

    @classmethod
    def from_line(cls, line: str) -> "LlmStreamMessage":
        return cls.from_dict(json.loads(line))


#: Common finish reasons.
FINISH_REASON_STOP = "stop"
FINISH_REASON_LENGTH = "length"
FINISH_REASON_INTERRUPTED = "interrupted"
FINISH_REASON_CONSTRAINT_SATISFIED = "constraint_satisfied"


# =============================================================================
# media:fmt=json;llm-vocab-response;record
# =============================================================================


@dataclass
class LlmVocabResponse:
    """Matches ``media:fmt=json;llm-vocab-response;record``."""

    vocab: list[str]
    vocab_size: Optional[int] = None

    @classmethod
    def of(cls, vocab: list[str]) -> "LlmVocabResponse":
        """A response whose size is its vocabulary's length, always stated."""
        return cls(vocab=list(vocab), vocab_size=len(vocab))

    def to_dict(self) -> dict[str, Any]:
        return _present({"vocab": self.vocab, "vocab_size": self.vocab_size})

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "LlmVocabResponse":
        return cls(vocab=record["vocab"], vocab_size=record.get("vocab_size"))

    def to_json(self) -> str:
        return _dumps(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "LlmVocabResponse":
        return cls.from_dict(json.loads(text))


# =============================================================================
# media:fmt=json;llm-model-info;record
# =============================================================================


@dataclass
class LlmModelInfo:
    """Matches ``media:fmt=json;llm-model-info;record``."""

    model_spec: str
    vocab_size: int
    context_length: Optional[int] = None
    embedding_dim: Optional[int] = None
    file_size_bytes: Optional[int] = None
    head_count: Optional[int] = None
    layer_count: Optional[int] = None
    supports_chat: Optional[bool] = None
    supports_tools: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        return _present(
            {
                "model_spec": self.model_spec,
                "vocab_size": self.vocab_size,
                "context_length": self.context_length,
                "embedding_dim": self.embedding_dim,
                "file_size_bytes": self.file_size_bytes,
                "head_count": self.head_count,
                "layer_count": self.layer_count,
                "supports_chat": self.supports_chat,
                "supports_tools": self.supports_tools,
            }
        )

    @classmethod
    def from_dict(cls, record: dict[str, Any]) -> "LlmModelInfo":
        return cls(
            model_spec=record["model_spec"],
            vocab_size=record["vocab_size"],
            context_length=record.get("context_length"),
            embedding_dim=record.get("embedding_dim"),
            file_size_bytes=record.get("file_size_bytes"),
            head_count=record.get("head_count"),
            layer_count=record.get("layer_count"),
            supports_chat=record.get("supports_chat"),
            supports_tools=record.get("supports_tools"),
        )

    def to_json(self) -> str:
        return _dumps(self.to_dict())

    @classmethod
    def from_json(cls, text: str) -> "LlmModelInfo":
        return cls.from_dict(json.loads(text))


# =============================================================================
# Media URNs — canonical definitions (single source of truth)
# =============================================================================

MEDIA_LLM_GENERATION_REQUEST = "media:fmt=json;llm-generation-request;record"
MEDIA_LLM_TEXT_STREAM = "media:fmt=ndjson;llm-text-stream"
MEDIA_LLM_VOCAB_RESPONSE = "media:fmt=json;llm-vocab-response;record"
MEDIA_LLM_MODEL_INFO_RESPONSE = "media:fmt=json;llm-model-info;record"


# =============================================================================
# Cap URNs — canonical definitions
# =============================================================================

CAP_LLM_INFERENCE_GGUF = (
    'cap:gguf;in="media:fmt=json;llm-generation-request;record";llm;ml-model;'
    'llm-inference;out="media:fmt=ndjson;llm-text-stream"'
)
CAP_LLM_INFERENCE_MLX = (
    'cap:in="media:fmt=json;llm-generation-request;record";llm;ml-model;mlx;'
    'llm-inference;out="media:fmt=ndjson;llm-text-stream"'
)
CAP_LLM_INFERENCE_CANDLE = (
    'cap:candle;in="media:fmt=json;llm-generation-request;record";llm;ml-model;'
    'llm-inference;out="media:fmt=ndjson;llm-text-stream"'
)
CAP_LLM_INFERENCE_CONSTRAINED = (
    'cap:constrained;gguf;in="media:fmt=json;llm-generation-request;record";llm;'
    'ml-model;llm-inference-constrained;out="media:fmt=ndjson;llm-text-stream"'
)
CAP_LLM_VOCAB = (
    'cap:llm-vocab;llm;ml-model;gguf;'
    'in="media:fmt=json;llm-generation-request;record";'
    'out="media:fmt=json;llm-vocab-response;record"'
)
CAP_LLM_MODEL_INFO = (
    'cap:llm-model-info;llm;ml-model;gguf;'
    'in="media:fmt=json;llm-generation-request;record";'
    'out="media:fmt=json;llm-model-info;record"'
)
CAP_GENERATE_EMBEDDINGS = (
    'cap:generate-embeddings;ml-model;gguf;in="media:enc=utf-8";'
    'out="media:embedding-vector;enc=utf-8;record"'
)
CAP_EMBEDDINGS_DIMENSIONS = (
    'cap:gguf;in="media:embeddings;enc=utf-8;gguf;model-spec;'
    'tokenizer-embedded-gguf";ml-model;embeddings-dimensions;'
    'out="media:integer;model-dim;numeric"'
)
CAP_DESCRIBE_IMAGE = (
    'cap:gguf;in="media:ext=png;image";ml-model;describe-image;'
    'out="media:enc=utf-8;ext=txt;image-description;plain-text";vision'
)


# =============================================================================
# Model spec → backend classification
# =============================================================================

BACKEND_GGUF = "gguf"
BACKEND_MLX = "mlx"
BACKEND_CANDLE = "candle"


def backend_for_model_spec(model_spec: str) -> str:
    """Classify a model spec into the inference backend that answers it.

    MLX repositories (``mlx-community/*`` or a ``;mlx`` tag) route to MLX;
    anything carrying a GGUF indicator routes to GGUF; everything else
    (safetensors) routes to Candle. One source of truth for spec → backend,
    used both to populate a model's backend and to pick the cap URN a dispatch
    goes to.
    """
    lower = model_spec.lower()
    if "mlx-community" in lower or ";mlx" in lower:
        return BACKEND_MLX
    if ".gguf" in lower or "gguf" in lower:
        return BACKEND_GGUF
    return BACKEND_CANDLE
