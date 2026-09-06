"""The LLM wire types, held to the reference's numbers.

Each number here tests what the same number tests in the Rust reference
(``src/llm.rs``). A mirror that agrees on the field names but not on the
serialized SHAPE is a mirror that produces documents the engine rejects, so
every assertion is made against the wire form rather than against the object.
"""

import json

from capdag.llm.protocol import (
    BACKEND_CANDLE,
    BACKEND_GGUF,
    BACKEND_MLX,
    FINISH_REASON_STOP,
    ConstraintSpec,
    LlmGenerationRequest,
    LlmModelInfo,
    LlmStreamMessage,
    LlmVocabResponse,
    REQUEST_TYPE_GENERATE,
    ToolDefinition,
    backend_for_model_spec,
)


def test_0001_generation_request_round_trip():
    """TEST0001: a generation request round-trips to equivalent content."""
    request = LlmGenerationRequest.with_defaults("Hello", "model/test")
    parsed = LlmGenerationRequest.from_json(request.to_json())

    assert parsed.prompt == "Hello"
    assert parsed.model_spec == "model/test"
    assert parsed.max_tokens == 512
    assert parsed.effective_request_type == REQUEST_TYPE_GENERATE


def test_0002_stream_message_token_round_trip():
    """TEST0002: a token message round-trips to itself, byte for byte."""
    line = LlmStreamMessage.token("Hello").to_line()
    # The exact bytes the reference emits: compact, in field order.
    assert line == '{"type":"token","text":"Hello"}'

    parsed = LlmStreamMessage.from_line(line)
    assert parsed.type == "token"
    assert parsed["text"] == "Hello"


def test_0003_stream_message_complete_round_trip():
    """TEST0003: Stream message complete round trip."""
    message = LlmStreamMessage.complete("Generated text", 10, 5, FINISH_REASON_STOP, 100)
    parsed = LlmStreamMessage.from_line(message.to_line())

    assert parsed.type == "complete"
    assert parsed["tokens_generated"] == 10
    assert parsed["finish_reason"] == "stop"


def test_0004_stream_message_error_round_trip():
    """TEST0004: Stream message error round trip."""
    message = LlmStreamMessage.error("MODEL_NOT_FOUND", "Model not available")
    parsed = LlmStreamMessage.from_line(message.to_line())

    assert parsed.type == "error"
    assert parsed["code"] == "MODEL_NOT_FOUND"
    assert parsed["message"] == "Model not available"


def test_0005_vocab_response_round_trip():
    """TEST0005: Vocab response round trip."""
    parsed = LlmVocabResponse.from_json(LlmVocabResponse.of(["a", "b", "c"]).to_json())

    assert len(parsed.vocab) == 3
    assert parsed.vocab_size == 3


def test_0006_model_info_round_trip():
    """TEST0006: Model info round trip."""
    info = LlmModelInfo(model_spec="test-model", vocab_size=32000, context_length=4096)
    parsed = LlmModelInfo.from_json(info.to_json())

    assert parsed.model_spec == "test-model"
    assert parsed.vocab_size == 32000
    assert parsed.context_length == 4096
    # The fields nobody set are ABSENT from the document, not null: a null
    # reads as a choice the caller made, and no other mirror emits one.
    assert "embedding_dim" not in json.loads(info.to_json())


def test_0007_constraint_spec_tags():
    """TEST0007: Constraint spec tags."""
    schema = ConstraintSpec.json_schema({"type": "object"})
    assert schema.to_dict()["type"] == "json_schema"

    regex = ConstraintSpec.regex(r"\d+")
    assert regex.to_dict()["type"] == "regex"
    assert regex.to_dict()["pattern"] == r"\d+"

    tools = ConstraintSpec.tool_call(
        [ToolDefinition(name="lookup", description="look it up", parameters={})]
    )
    assert tools.to_dict()["type"] == "tool_call"
    assert tools.to_dict()["tools"][0]["name"] == "lookup"

    # And a constraint survives the round trip through a request, which is the
    # only path it actually travels.
    request = LlmGenerationRequest.with_defaults("Hi", "model/test")
    request.constraint = schema
    parsed = LlmGenerationRequest.from_json(request.to_json())
    assert parsed.constraint is not None
    assert parsed.constraint.type == "json_schema"
    assert parsed.constraint.schema == {"type": "object"}


def test_0008_backend_for_model_spec_gguf():
    """TEST0008: Backend for model spec gguf."""
    assert backend_for_model_spec("hf:bartowski/Llama-3.2-3B-Instruct-GGUF") == BACKEND_GGUF
    assert (
        backend_for_model_spec("hf:TheBloke/Mistral-7B-v0.1-GGUF?include=*Q4_K_M*.gguf")
        == BACKEND_GGUF
    )
    assert backend_for_model_spec("local:/path/to/model.gguf") == BACKEND_GGUF


def test_0009_backend_for_model_spec_mlx():
    """TEST0009: Backend for model spec mlx."""
    assert (
        backend_for_model_spec("hf:mlx-community/Mistral-7B-Instruct-v0.3-4bit")
        == BACKEND_MLX
    )
    assert (
        backend_for_model_spec("hf:mlx-community/Meta-Llama-3.1-8B-Instruct-4bit")
        == BACKEND_MLX
    )
    assert backend_for_model_spec("hf:some-model;mlx") == BACKEND_MLX


def test_0010_backend_for_model_spec_candle():
    """TEST0010: Backend for model spec candle."""
    assert backend_for_model_spec("hf:meta-llama/Llama-3.1-8B-Instruct") == BACKEND_CANDLE
    assert backend_for_model_spec("hf:microsoft/phi-2") == BACKEND_CANDLE
    assert backend_for_model_spec("hf:google/gemma-2b") == BACKEND_CANDLE
