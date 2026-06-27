"""Tests for cartridge_runtime module"""

import pytest
import json
import cbor2
import sys
import queue
import io
from capdag.bifaci.cartridge_runtime import (
    CartridgeRuntime,
    NoPeerInvoker,
    CliStreamEmitter,
    PeerRequestError,
    DeserializeError,
    CapUrnError,
    extract_effective_payload,
    collect_args_by_media_urn,
    collect_peer_response,
    collect_streams,
    find_stream,
    require_stream,
    demux_peer_response,
    PeerResponseItem,
    PeerResponse,
    ProgressSender,
    ThreadSafeEmitter,
    SyncFrameWriter,
    InputStream,
    InputPackage,
    OutputStream,
    PeerCall,
    RuntimeError as CartridgeRuntimeError,
    NoHandlerError,
    MissingArgumentError,
    UnknownSubcommandError,
    ManifestError,
    PeerResponseError,
    PendingStream,
    Request,
    WET_KEY_REQUEST,
    dispatch_op,
    OpFactory,
)
from ops import Op, OpMetadata, DryContext, WetContext, ExecutionFailedError
from capdag.cap.caller import CapArgumentValue
from capdag.bifaci.manifest import CapManifest
from capdag.urn.media_urn import MediaUrn
from capdag.bifaci.frame import DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, Frame, FrameType, MessageId
from capdag.standard.caps import CAP_IDENTITY, CAP_DISCARD, CAP_ADAPTER_SELECTION

# Test manifest JSON with a single cap for basic tests.
# Note: cap URN uses "cap:test" which lacks in/out tags, so CapManifest deserialization
# may fail because Cap requires in/out specs. For tests that only need raw manifest bytes
# (CBOR mode handshake), this is fine. For tests that need parsed CapManifest, use
# VALID_MANIFEST instead.
TEST_MANIFEST = '{"name":"TestCartridge","version":"1.0.0","channel":"release","registry_url":null,"description":"Test cartridge","cap_groups":[{"name":"default","caps":[{"urn":"cap:test","title":"Test","command":"test"}]}]}'

# Valid manifest with explicit identity and one additional cap for tests that need parsed CapManifest
VALID_MANIFEST = '{"name":"TestCartridge","version":"1.0.0","channel":"release","registry_url":null,"description":"Test cartridge","cap_groups":[{"name":"default","caps":[{"urn":"cap:effect=none","title":"Identity","command":"identity"},{"urn":"cap:in=\\"media:void\\";test;out=\\"media:void\\"","title":"Test","command":"test"}]}]}'


# =============================================================================
# Test helpers
# =============================================================================

def make_test_frames(media_urn: str, data: bytes) -> queue.Queue:
    """Create a queue.Queue of frames for testing a single-stream input."""
    from capdag.bifaci.frame import compute_checksum
    request_id = MessageId(0)
    frames = queue.Queue()
    frames.put(Frame.stream_start(request_id, "arg-0", media_urn))
    encoded = cbor2.dumps(data)
    frames.put(Frame.chunk(request_id, "arg-0", 0, encoded, 0, compute_checksum(encoded)))
    frames.put(Frame.stream_end(request_id, "arg-0", 1))
    frames.put(Frame.end(request_id, None))
    frames.put(None)
    return frames


def invoke_op(factory: OpFactory, frames: queue.Queue, emitter) -> None:
    """Helper: invoke a factory-produced Op with test input/output."""
    op = factory()
    peer = NoPeerInvoker()
    dispatch_op(op, frames, emitter, peer)


def create_test_cap(urn_str: str, title: str, command: str, args: list):
    """Helper function to create a Cap for tests"""
    from capdag.urn.cap_urn import CapUrn
    from capdag.cap.definition import Cap
    urn = CapUrn.from_string(urn_str)
    cap = Cap(urn, title, command)
    cap.args = args
    return cap


def cli_extract_value(runtime, cap, cli_args, stdin_data=None):
    """Drive the full CLI flow (build_payload_from_cli → extract_effective_payload)
    and return the first argument's `value` field. Returns the raw value (bytes
    for scalar, list for sequence) so tests can assert on file contents directly.
    """
    from capdag.bifaci.cartridge_runtime import (
        build_cli_foreach_iterations,
        extract_effective_payload,
    )
    # Manually mirror build_payload_from_cli when stdin_data provided so tests
    # don't rely on the runtime's non-blocking stdin probe.
    if stdin_data is not None:
        from capdag.cap.caller import CapArgumentValue
        from capdag.cap.definition import StdinSource as _StdinSource
        arguments = []
        for arg_def in cap.get_args():
            value, came_from_stdin = runtime._extract_arg_value(arg_def, cli_args, stdin_data)
            if value is not None:
                media_urn = arg_def.media_urn
                if came_from_stdin:
                    for s in arg_def.sources:
                        if isinstance(s, _StdinSource):
                            media_urn = s.stdin
                            break
                arguments.append(CapArgumentValue(media_urn=media_urn, value=value))
        cbor_args = [{"media_urn": a.media_urn, "value": a.value} for a in arguments]
        raw_payload = cbor2.dumps(cbor_args)
    else:
        raw_payload = runtime.build_payload_from_cli(cap, cli_args)
    iterations = build_cli_foreach_iterations(raw_payload, cap)
    # For non-foreach (single iteration) tests, return the first arg's value.
    payload = extract_effective_payload(iterations[0], "application/cbor", cap, True)
    arr = cbor2.loads(payload)
    return arr[0]["value"]


def cli_extract_all_iterations(runtime, cap, cli_args):
    """Drive build_payload_from_cli + build_cli_foreach_iterations and return
    a list of effective payloads (one per CLI foreach iteration)."""
    from capdag.bifaci.cartridge_runtime import (
        build_cli_foreach_iterations,
        extract_effective_payload,
    )
    raw_payload = runtime.build_payload_from_cli(cap, cli_args)
    iterations = build_cli_foreach_iterations(raw_payload, cap)
    return [extract_effective_payload(it, "application/cbor", cap, True) for it in iterations]


# TEST248: Test register_op and find_handler by exact cap URN
def test_248_register_and_find_handler():
    class EmitBytesOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"result")
        def metadata(self): return OpMetadata.builder("EmitBytesOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:in=media:;test;out=media:", EmitBytesOp)
    assert runtime.find_handler("cap:in=media:;test;out=media:") is not None


# TEST249: Test register_op handler echoes bytes directly
def test_249_raw_handler():
    received = []

    class EchoOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames = req.take_frames()
            chunks = []
            for frame in iter(frames.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload:
                    chunks.append(cbor2.loads(frame.payload))
                elif frame.frame_type == FrameType.END:
                    break
            data = b''.join(chunks)
            received.append(data)
            req.emitter().emit_cbor(data)
        def metadata(self): return OpMetadata.builder("EchoOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:raw", EchoOp)

    factory = runtime.find_handler("cap:raw")
    assert factory is not None

    frames = make_test_frames("media:", b"echo this")
    emitter = CliStreamEmitter()
    invoke_op(factory, frames, emitter)
    assert received[0] == b"echo this", "Op handler must echo payload"


# TEST250: Test Op handler collects input and processes it
def test_250_typed_handler_deserialization():
    received = []

    class JsonKeyOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames = req.take_frames()
            chunks = []
            for frame in iter(frames.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload:
                    chunks.append(cbor2.loads(frame.payload))
                elif frame.frame_type == FrameType.END:
                    break
            all_bytes = b''.join(chunks)
            data = json.loads(all_bytes)
            value = data.get("key", "missing").encode('utf-8')
            received.append(value)
            req.emitter().emit_cbor(value)
        def metadata(self): return OpMetadata.builder("JsonKeyOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:test", JsonKeyOp)

    factory = runtime.find_handler("cap:test")
    assert factory is not None

    frames = make_test_frames("media:", b'{"key":"hello"}')
    emitter = CliStreamEmitter()
    invoke_op(factory, frames, emitter)
    assert received[0] == b"hello"


# TEST251: Test Op handler propagates errors through RuntimeError::Handler
def test_251_typed_handler_rejects_invalid_json():
    class JsonParseOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames = req.take_frames()
            chunks = []
            for frame in iter(frames.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload:
                    chunks.append(cbor2.loads(frame.payload))
                elif frame.frame_type == FrameType.END:
                    break
            all_bytes = b''.join(chunks)
            data = json.loads(all_bytes)  # raises on bad JSON
            _ = data
        def metadata(self): return OpMetadata.builder("JsonParseOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:test", JsonParseOp)

    factory = runtime.find_handler("cap:test")
    frames = make_test_frames("media:", b"not json {{{{")
    emitter = CliStreamEmitter()

    with pytest.raises(Exception) as exc_info:
        invoke_op(factory, frames, emitter)

    assert exc_info.value is not None, "Invalid input must produce an error"


# TEST252: Test find_handler returns None for unregistered cap URNs
def test_252_find_handler_unknown_cap():
    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    assert runtime.find_handler("cap:nonexistent") is None


# TEST293: Test CartridgeRuntime Op registration and lookup by exact and non-existent cap URN
def test_293_cartridge_runtime_handler_registration():
    class JsonEchoOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"echo")
        def metadata(self): return OpMetadata.builder("JsonEchoOp").build()

    class TransformOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"transformed")
        def metadata(self): return OpMetadata.builder("TransformOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode("utf-8"))
    runtime.register_op("cap:json-echo", JsonEchoOp)
    runtime.register_op("cap:transform", TransformOp)

    assert runtime.find_handler("cap:json-echo") is JsonEchoOp
    assert runtime.find_handler("cap:transform") is TransformOp
    assert runtime.find_handler("cap:nonexistent") is None


# TEST253: Test OpFactory can be cloned via Arc and sent across tasks (Send + Sync)
def test_253_handler_is_send_sync():
    import threading

    received = []

    class EmitAndRecordOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"done")
            received.append(b"done")
        def metadata(self): return OpMetadata.builder("EmitAndRecordOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:threaded", EmitAndRecordOp)

    factory = runtime.find_handler("cap:threaded")
    assert factory is not None

    def thread_func():
        frames = make_test_frames("media:", b"{}")
        emitter = CliStreamEmitter()
        invoke_op(factory, frames, emitter)

    thread = threading.Thread(target=thread_func)
    thread.start()
    thread.join()
    assert received == [b"done"]


# TEST254: Test NoPeerInvoker always returns PeerRequest error
def test_254_no_peer_invoker():
    no_peer = NoPeerInvoker()

    with pytest.raises(PeerRequestError) as exc_info:
        no_peer.invoke("cap:test", [])

    assert "not supported" in str(exc_info.value).lower()


# TEST255: Test NoPeerInvoker call_with_bytes also returns error
def test_255_no_peer_invoker_with_arguments():
    no_peer = NoPeerInvoker()
    args = [CapArgumentValue.from_str("media:test", "value")]

    with pytest.raises(PeerRequestError):
        no_peer.invoke("cap:test", args)


# TEST256: Test CartridgeRuntime::with_manifest_json stores manifest data and parses when valid
def test_256_with_manifest_json():
    runtime_basic = CartridgeRuntime.with_manifest_json(TEST_MANIFEST)
    assert len(runtime_basic.manifest_data) > 0

    # VALID_MANIFEST has proper in/out specs
    runtime_valid = CartridgeRuntime.with_manifest_json(VALID_MANIFEST)
    assert len(runtime_valid.manifest_data) > 0
    assert runtime_valid.manifest is not None, "VALID_MANIFEST must parse into CapManifest"


# TEST257: Test CartridgeRuntime::new with invalid JSON still creates runtime (manifest is None)
def test_257_new_with_invalid_json():
    runtime = CartridgeRuntime(b"not json")
    assert len(runtime.manifest_data) > 0
    assert runtime.manifest is None, "invalid JSON should leave manifest as None"


# TEST258: Test CartridgeRuntime::with_manifest creates runtime with valid manifest data
def test_258_with_manifest_struct():
    manifest_dict = json.loads(VALID_MANIFEST)
    manifest = CapManifest.from_dict(manifest_dict)
    runtime = CartridgeRuntime.with_manifest(manifest)
    assert len(runtime.manifest_data) > 0
    assert runtime.manifest is not None


# TEST259: Test extract_effective_payload with non-CBOR content_type returns raw payload unchanged
def test_259_extract_effective_payload_non_cbor():
    cap = create_test_cap('cap:in=media:void;test;out=media:void', "Test", "test", [])
    payload = b"raw data"
    result = extract_effective_payload(payload, "application/json", cap, True)
    assert result == payload


# TEST260: Test extract_effective_payload with None content_type returns raw payload unchanged
def test_260_extract_effective_payload_no_content_type():
    cap = create_test_cap('cap:in=media:void;test;out=media:void', "Test", "test", [])
    payload = b"raw data"
    result = extract_effective_payload(payload, "", cap, True)
    assert result == payload


# TEST261: Test extract_effective_payload with CBOR content extracts matching argument value
def test_261_extract_effective_payload_cbor_match():
    args = [{"media_urn": "media:enc=utf-8;string", "value": b"hello"}]
    payload = cbor2.dumps(args)
    cap = create_test_cap('cap:in="media:enc=utf-8;string";test;out="media:void"', "Test", "test", [])
    result = extract_effective_payload(payload, "application/cbor", cap, False)
    # NEW REGIME: result is full CBOR array; extract value from matching arg
    result_arr = cbor2.loads(result)
    assert isinstance(result_arr, list) and len(result_arr) == 1
    assert result_arr[0]["value"] == b"hello"


# TEST262: Test extract_effective_payload with CBOR content fails when no argument matches expected input
def test_262_extract_effective_payload_cbor_no_match():
    args = [{"media_urn": "media:other-type", "value": b"data"}]
    payload = cbor2.dumps(args)
    cap = create_test_cap('cap:in="media:enc=utf-8;string";test;out="media:void"', "Test", "test", [])
    with pytest.raises(DeserializeError) as exc_info:
        extract_effective_payload(payload, "application/cbor", cap, False)
    assert "No argument found matching" in str(exc_info.value)


# TEST263: Test extract_effective_payload with invalid CBOR bytes returns deserialization error
def test_263_extract_effective_payload_invalid_cbor():
    cap = create_test_cap('cap:in=media:void;test;out=media:void', "Test", "test", [])
    with pytest.raises(DeserializeError):
        extract_effective_payload(b"not cbor", "application/cbor", cap, False)


# TEST264: Test extract_effective_payload with CBOR non-array (e.g. map) returns error
def test_264_extract_effective_payload_cbor_not_array():
    payload = cbor2.dumps({})  # CBOR map, not array
    cap = create_test_cap('cap:in=media:void;test;out=media:void', "Test", "test", [])
    with pytest.raises(DeserializeError):
        extract_effective_payload(payload, "application/cbor", cap, False)


# TEST266: Test CliFrameSender wraps CliStreamEmitter correctly (basic construction)
def test_266_cli_stream_emitter_construction():
    emitter = CliStreamEmitter()
    assert emitter.ndjson, "default CLI emitter must use NDJSON"

    emitter2 = CliStreamEmitter.without_ndjson()
    assert not emitter2.ndjson


# TEST268: Test RuntimeError variants display correct messages
def test_268_runtime_error_display():
    err = NoHandlerError("cap:missing")
    assert "cap:missing" in str(err)

    err2 = MissingArgumentError("model")
    assert "model" in str(err2)

    err3 = UnknownSubcommandError("badcmd")
    assert "badcmd" in str(err3)

    err4 = ManifestError("parse failed")
    assert "parse failed" in str(err4)

    err5 = PeerRequestError("denied")
    assert "denied" in str(err5)

    err6 = PeerResponseError("timeout")
    assert "timeout" in str(err6)


# TEST270: Test registering multiple Op handlers for different caps and finding each independently
def test_270_multiple_handlers():
    class EchoTagOp(Op):
        def __init__(self, tag: bytes):
            self.tag = tag
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(self.tag)
        def metadata(self): return OpMetadata.builder("EchoTagOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op("cap:alpha", lambda: EchoTagOp(b"a"))
    runtime.register_op("cap:beta", lambda: EchoTagOp(b"b"))
    runtime.register_op("cap:gamma", lambda: EchoTagOp(b"g"))

    emitter = CliStreamEmitter()
    f_alpha = runtime.find_handler("cap:alpha")
    invoke_op(f_alpha, make_test_frames("media:", b""), emitter)

    f_beta = runtime.find_handler("cap:beta")
    invoke_op(f_beta, make_test_frames("media:", b""), emitter)

    f_gamma = runtime.find_handler("cap:gamma")
    invoke_op(f_gamma, make_test_frames("media:", b""), emitter)


# TEST271: Test Op handler replacing an existing registration for the same cap URN
def test_271_handler_replacement():
    result2 = []

    class FirstOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"first")
        def metadata(self): return OpMetadata.builder("FirstOp").build()

    class SecondOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            _ = req.take_frames()
            req.emitter().emit_cbor(b"second")
            result2.append(b"second")
        def metadata(self): return OpMetadata.builder("SecondOp").build()

    runtime = CartridgeRuntime(TEST_MANIFEST.encode('utf-8'))
    runtime.register_op_type("cap:test", FirstOp)
    runtime.register_op_type("cap:test", SecondOp)

    factory = runtime.find_handler("cap:test")
    assert factory is not None

    emitter = CliStreamEmitter()
    invoke_op(factory, make_test_frames("media:", b""), emitter)
    assert result2 == [b"second"], "later registration must replace earlier"


# TEST272: Test extract_effective_payload CBOR with multiple arguments selects the correct one
def test_272_extract_effective_payload_multiple_args():
    args = [
        {"media_urn": "media:enc=utf-8;other-type", "value": b"wrong"},
        {"media_urn": "media:enc=utf-8;model-spec", "value": b"correct"},
    ]
    payload = cbor2.dumps(args)
    cap = create_test_cap('cap:in="media:enc=utf-8;model-spec";infer;out="media:void"', "Test", "infer", [])
    result = extract_effective_payload(payload, "application/cbor", cap, False)
    # NEW REGIME: handler receives full CBOR array; matches against in_spec.
    result_arr = cbor2.loads(result)
    assert len(result_arr) == 2
    in_spec = MediaUrn.from_string("media:enc=utf-8;model-spec")
    found = None
    for arg in result_arr:
        arg_urn = MediaUrn.from_string(arg["media_urn"])
        if in_spec.is_comparable(arg_urn):
            found = arg["value"]
            break
    assert found == b"correct"


# TEST273: Test extract_effective_payload with binary data in CBOR value (not just text)
def test_273_extract_effective_payload_binary_value():
    binary_data = bytes(range(256))
    args = [{"media_urn": "media:ext=pdf", "value": binary_data}]
    payload = cbor2.dumps(args)
    cap = create_test_cap('cap:in="media:ext=pdf";process;out=media:void', "Test", "process", [])
    result = extract_effective_payload(payload, "application/cbor", cap, False)
    result_arr = cbor2.loads(result)
    assert result_arr[0]["value"] == binary_data


# =============================================================================
# File-path to bytes conversion tests (TEST336-TEST360)
# =============================================================================

def create_test_manifest(name: str, version: str, description: str, caps: list) -> CapManifest:
    """Helper function to create a CapManifest for tests"""
    from capdag.bifaci.manifest import default_group
    from capdag.cap.definition import Cap
    from capdag.urn.cap_urn import CapUrn

    all_caps = list(caps)
    if not any(cap.urn_string() == CAP_IDENTITY for cap in all_caps):
        all_caps.insert(0, Cap(CapUrn.from_string(CAP_IDENTITY), "Identity", "identity"))
    return CapManifest(
        name=name,
        version=version, channel="release",
            registry_url=None,
            description=description,
        cap_groups=[default_group(all_caps)],
    )


# TEST336: Single file-path arg with stdin source reads file and passes bytes to handler
def test_336_file_path_reads_file_passes_bytes(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource
    from capdag.bifaci.frame import compute_checksum

    test_file = tmp_path / "test336_input.pdf"
    test_file.write_bytes(b"PDF binary content 336")

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process PDF",
        "process",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    received_payload = []

    class CollectBytesOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames_q = req.take_frames()
            chunks = []
            for frame in iter(frames_q.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload:
                    chunks.append(cbor2.loads(frame.payload))
                elif frame.frame_type == FrameType.END:
                    break
            received_payload.append(b''.join(chunks))
        def metadata(self): return OpMetadata.builder("CollectBytesOp").build()

    runtime.register_op('cap:in="media:ext=pdf";process;out=media:void', CollectBytesOp)

    # Simulate CLI invocation through the full runtime CLI flow.
    cli_args = [str(test_file)]
    cap = runtime.find_cap_by_command(runtime.manifest, 'process')
    assert cap is not None, "Process cap not found in manifest"
    payloads = cli_extract_all_iterations(runtime, cap, cli_args)
    assert len(payloads) == 1, "scalar file-path must produce a single iteration"

    # Build frame queue like dispatch_cli_payload does.
    request_id = MessageId(0)
    frames = queue.Queue()
    arr = cbor2.loads(payloads[0])
    for i, arg in enumerate(arr):
        stream_id = f"arg-{i}"
        frames.put(Frame.stream_start(request_id, stream_id, arg["media_urn"]))
        encoded = cbor2.dumps(arg["value"])
        frames.put(Frame.chunk(request_id, stream_id, 0, encoded, 0, compute_checksum(encoded)))
        frames.put(Frame.stream_end(request_id, stream_id, 1))
    frames.put(Frame.end(request_id, None))
    frames.put(None)

    factory = runtime.find_handler(cap.urn_string())
    emitter = CliStreamEmitter()
    invoke_op(factory, frames, emitter)

    # Verify handler received file bytes, not file path
    assert received_payload[0] == b"PDF binary content 336", "Handler should receive file bytes"


# TEST337: file-path arg without stdin source passes path as string (no conversion)
def test_337_file_path_without_stdin_passes_string(tmp_path):
    from capdag.cap.definition import CapArg, PositionSource

    test_file = tmp_path / "test337_input.txt"
    test_file.write_bytes(b"content")

    cap = create_test_cap(
        'cap:in=media:void;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[PositionSource(0)]  # NO stdin source!
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    # No stdin source → no file-path conversion → arg value stays as raw path bytes.
    result, _ = runtime._extract_arg_value(cap.args[0], cli_args, None)
    value_str = result.decode('utf-8')
    assert "test337_input.txt" in value_str, "Should receive file path string when no stdin source"


# TEST338: file-path arg reads file via --file CLI flag
def test_338_file_path_via_cli_flag(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, CliFlagSource

    test_file = tmp_path / "test338.pdf"
    test_file.write_bytes(b"PDF via flag 338")

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process",
        "process",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                CliFlagSource("--file"),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = ["--file", str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == b"PDF via flag 338", "Should read file from --file flag"


# TEST339: file-path-array reads multiple files with glob pattern
def test_339_file_path_array_glob_expansion(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_dir = tmp_path / "test339"
    test_dir.mkdir()

    file1 = test_dir / "doc1.txt"
    file2 = test_dir / "doc2.txt"
    file1.write_bytes(b"content1")
    file2.write_bytes(b"content2")

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Batch",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            is_sequence=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # CLI: bare glob pattern for sequence-declared file-path arg.
    pattern = f"{test_dir}/*.txt"
    cli_args = [pattern]
    result = cli_extract_value(runtime, cap, cli_args)
    # Sequence args produce a list of file bytes.
    assert isinstance(result, list)
    assert len(result) == 2
    assert sorted(result) == [b"content1", b"content2"]


# TEST340: File not found error provides clear message
def test_340_file_not_found_clear_error():
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    cap = create_test_cap(
        'cap:in="media:ext=pdf";test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = ["/nonexistent/file.pdf"]
    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    with pytest.raises(_Rt) as exc_info:
        cli_extract_value(runtime, cap, cli_args)
    err_msg = str(exc_info.value)
    assert "/nonexistent/file.pdf" in err_msg, "Error should mention file path"
    assert "File not found" in err_msg, f"Error should be clear; got: {err_msg}"


# TEST341: stdin takes precedence over file-path in source order
def test_341_stdin_precedence_over_file_path(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test341_input.txt"
    test_file.write_bytes(b"file content")

    # Stdin source comes BEFORE position source
    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),  # First
                PositionSource(0),            # Second
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    stdin_data = b"stdin content 341"
    # Stdin source comes first → its data is selected (no file conversion needed).
    result, came_from_stdin = runtime._extract_arg_value(cap.args[0], cli_args, stdin_data)
    assert came_from_stdin is True
    assert result == b"stdin content 341", "stdin source should take precedence"


# TEST342: file-path with position 0 reads first positional arg as file
def test_342_file_path_position_zero_reads_first_arg(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test342.dat"
    test_file.write_bytes(b"binary data 342")

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == b"binary data 342", "Should read file at position 0"


# TEST343: Non-file-path args are not affected by file reading
def test_343_non_file_path_args_unaffected():
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    # Arg with different media type should NOT trigger file reading
    cap = create_test_cap(
        'cap:in=media:void;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;model-spec",  # NOT file-path
            required=True,
            sources=[
                StdinSource("media:enc=utf-8;model-spec"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = ["mlx-community/Llama-3.2-3B-Instruct-4bit"]
    # Non-file-path arg → no conversion; raw cli string returned as bytes.
    result, _ = runtime._extract_arg_value(cap.args[0], cli_args, None)
    assert result.decode('utf-8') == "mlx-community/Llama-3.2-3B-Instruct-4bit"


# TEST6586: A scalar file-path arg receiving a nonexistent path fails hard
# with a clear error that names the path. The runtime refuses to silently
# swallow user mistakes like typos or wrong directories.
def test_6586_file_path_array_invalid_json_fails():
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = ["/nonexistent/path/to/nothing"]
    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    with pytest.raises(_Rt) as exc_info:
        cli_extract_value(runtime, cap, cli_args)
    err = str(exc_info.value)
    assert "/nonexistent/path/to/nothing" in err, f"Error should mention the path; got: {err}"
    assert "File not found" in err, f"Error should be clear; got: {err}"


# TEST6587: file-path-array with literal nonexistent path fails hard
def test_6587_file_path_array_one_file_missing_fails_hard(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    missing_path = tmp_path / "test345_missing.txt"

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(missing_path)]
    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    with pytest.raises(_Rt) as exc_info:
        cli_extract_value(runtime, cap, cli_args)
    err = str(exc_info.value)
    assert "test345_missing.txt" in err, "Error should mention the missing file"
    assert "File not found" in err, f"Error should be clear; got: {err}"


# TEST346: Large file (1MB) reads successfully
def test_346_large_file_reads_successfully(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test346_large.bin"

    # Create 1MB file
    large_data = bytes([42] * 1_000_000)
    test_file.write_bytes(large_data)

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert len(result) == 1_000_000, "Should read entire 1MB file"
    assert result == large_data, "Content should match exactly"


# TEST347: Empty file reads as empty bytes
def test_347_empty_file_reads_as_empty_bytes(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test347_empty.txt"
    test_file.write_bytes(b"")

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == b"", "Empty file should produce empty bytes"


# TEST348: file-path conversion respects source order
def test_348_file_path_conversion_respects_source_order(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test348.txt"
    test_file.write_bytes(b"file content 348")

    # Position source BEFORE stdin source
    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                PositionSource(0),            # First
                StdinSource("media:"),  # Second
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    stdin_data = b"stdin content 348"
    # Position source comes first → path is selected and the file is read.
    result = cli_extract_value(runtime, cap, cli_args, stdin_data=stdin_data)
    assert result == b"file content 348", "Position source tried first, file read"


# TEST349: file-path arg with multiple sources tries all in order
def test_349_file_path_multiple_sources_fallback(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource, CliFlagSource

    test_file = tmp_path / "test349.txt"
    test_file.write_bytes(b"content 349")

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                CliFlagSource("--file"),     # First (not provided)
                PositionSource(0),            # Second (provided)
                StdinSource("media:"),  # Third (not used)
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # Only provide position arg, no --file flag → falls back to position.
    cli_args = [str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == b"content 349", "Should fall back to position source and read file"


# TEST350: Integration test - full CLI mode invocation with file-path
def test_350_full_cli_mode_with_file_path_integration(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource
    from capdag.bifaci.frame import compute_checksum

    test_file = tmp_path / "test350_input.pdf"
    test_content = b"PDF file content for integration test"
    test_file.write_bytes(test_content)

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out="media:enc=utf-8;result"',
        "Process PDF",
        "process",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    received_payload = []

    class CollectBytesOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames_q = req.take_frames()
            chunks = []
            for frame in iter(frames_q.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload:
                    chunks.append(cbor2.loads(frame.payload))
                elif frame.frame_type == FrameType.END:
                    break
            received_payload.append(b''.join(chunks))
        def metadata(self): return OpMetadata.builder("CollectBytesOp").build()

    runtime.register_op(
        'cap:in="media:ext=pdf";process;out="media:enc=utf-8;result"',
        CollectBytesOp,
    )

    # Simulate full CLI invocation through the new flow.
    cli_args = [str(test_file)]
    cap = runtime.find_cap_by_command(runtime.manifest, 'process')
    assert cap is not None, "Process cap not found in manifest"
    payloads = cli_extract_all_iterations(runtime, cap, cli_args)
    assert len(payloads) == 1

    request_id = MessageId(0)
    frames = queue.Queue()
    arr = cbor2.loads(payloads[0])
    for i, arg in enumerate(arr):
        stream_id = f"arg-{i}"
        frames.put(Frame.stream_start(request_id, stream_id, arg["media_urn"]))
        encoded = cbor2.dumps(arg["value"])
        frames.put(Frame.chunk(request_id, stream_id, 0, encoded, 0, compute_checksum(encoded)))
        frames.put(Frame.stream_end(request_id, stream_id, 1))
    frames.put(Frame.end(request_id, None))
    frames.put(None)

    factory = runtime.find_handler(cap.urn_string())
    emitter = CliStreamEmitter()
    invoke_op(factory, frames, emitter)

    assert received_payload[0] == test_content, "Handler should receive file bytes, not path"


# TEST6588: file-path arg in CBOR mode with empty Array returns empty.
# CBOR Array (not JSON-encoded) is the multi-input wire form for sequence
# args. Mirrors Rust test351_file_path_array_empty_array.
def test_6588_file_path_array_empty_array():
    from capdag.cap.definition import CapArg, StdinSource

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=False,
            is_sequence=True,
            sources=[StdinSource("media:")]
        )]
    )

    # CBOR-mode payload: value is an empty Array.
    args = [{"media_urn": "media:enc=utf-8;file-path", "value": []}]
    payload = cbor2.dumps(args)
    result = extract_effective_payload(payload, "application/cbor", cap, False)

    result_arr = cbor2.loads(result)
    assert len(result_arr) == 1
    val = result_arr[0]["value"]
    assert isinstance(val, list)
    assert len(val) == 0


# TEST352: file permission denied error is clear (Unix-specific)
@pytest.mark.skipif(sys.platform == "win32", reason="Unix permissions only")
def test_352_file_permission_denied_clear_error(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource
    import os

    test_file = tmp_path / "test352_noperm.txt"
    test_file.write_bytes(b"content")

    # Remove read permissions
    os.chmod(test_file, 0o000)

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    try:
        with pytest.raises(_Rt) as exc_info:
            cli_extract_value(runtime, cap, cli_args)
        err = str(exc_info.value)
        assert "test352_noperm.txt" in err, "Error should mention the file"
    finally:
        os.chmod(test_file, 0o644)


# TEST353: CBOR payload format matches between CLI and CBOR mode
def test_353_cbor_payload_format_consistency():
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    cap = create_test_cap(
        'cap:in="media:enc=utf-8;text";test;out="media:void"',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;text",
            required=True,
            sources=[
                StdinSource("media:enc=utf-8;text"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = ["test value"]
    payload = runtime.build_payload_from_cli(cap, cli_args)
    arr = cbor2.loads(payload)
    assert len(arr) == 1
    assert arr[0]["media_urn"] == "media:enc=utf-8;text"
    assert arr[0]["value"] == b"test value"


# TEST6589: A glob pattern with no matches fails hard. Silent empty results
# mask real user mistakes (typo'd path, wrong directory), so the runtime
# surfaces them rather than returning an empty array.
def test_6589_glob_pattern_no_matches_fails_hard(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            is_sequence=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    pattern = f"{tmp_path}/nonexistent_*.xyz"
    cli_args = [pattern]
    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    with pytest.raises(_Rt) as exc_info:
        cli_extract_value(runtime, cap, cli_args)
    err = str(exc_info.value)
    assert "No files matched" in err, f"Error should say no files matched; got: {err}"


# TEST355: Glob pattern skips directories
def test_355_glob_pattern_skips_directories(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_dir = tmp_path / "test355"
    test_dir.mkdir()

    subdir = test_dir / "subdir"
    subdir.mkdir()

    file1 = test_dir / "file1.txt"
    file1.write_bytes(b"content1")

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            is_sequence=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    pattern = f"{test_dir}/*"
    cli_args = [pattern]
    result = cli_extract_value(runtime, cap, cli_args)
    assert isinstance(result, list)
    assert len(result) == 1, "Should only include files, not directories"
    assert result[0] == b"content1"


# TEST356: Multiple glob patterns combined
def test_356_multiple_glob_patterns_combined(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_dir = tmp_path / "test356"
    test_dir.mkdir()

    file1 = test_dir / "doc.txt"
    file2 = test_dir / "data.json"
    file1.write_bytes(b"text")
    file2.write_bytes(b"json")

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            is_sequence=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # CBOR mode allows arrays of patterns. Mirrors Rust test356.
    pattern1 = f"{test_dir}/*.txt"
    pattern2 = f"{test_dir}/*.json"
    args = [{"media_urn": "media:enc=utf-8;file-path", "value": [pattern1, pattern2]}]
    payload = cbor2.dumps(args)
    result = extract_effective_payload(payload, "application/cbor", cap, False)
    result_arr = cbor2.loads(result)
    val = result_arr[0]["value"]
    assert isinstance(val, list)
    assert len(val) == 2
    assert sorted(val) == [b"json", b"text"]


# TEST357: Symlinks are followed when reading files
@pytest.mark.skipif(sys.platform == "win32", reason="Unix symlinks only")
def test_357_symlinks_followed(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource
    import os

    test_dir = tmp_path / "test357"
    test_dir.mkdir()

    real_file = test_dir / "real.txt"
    link_file = test_dir / "link.txt"
    real_file.write_bytes(b"real content")
    os.symlink(real_file, link_file)

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(link_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == b"real content", "Should follow symlink and read real file"


# TEST358: Binary file with non-UTF8 data reads correctly
def test_358_binary_file_non_utf8(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test358.bin"

    # Binary data that's not valid UTF-8
    binary_data = bytes([0xFF, 0xFE, 0x00, 0x01, 0x80, 0x7F, 0xAB, 0xCD])
    test_file.write_bytes(binary_data)

    cap = create_test_cap(
        'cap:in=media:;test;out=media:void',
        "Test",
        "test",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    result = cli_extract_value(runtime, cap, cli_args)
    assert result == binary_data, "Binary data should read correctly"


# TEST359: Invalid glob pattern fails with clear error
def test_359_invalid_glob_pattern_fails():
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    cap = create_test_cap(
        'cap:in=media:;batch;out=media:void',
        "Test",
        "batch",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            is_sequence=True,
            sources=[
                StdinSource("media:"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # Invalid glob pattern (unclosed bracket) sent in CBOR mode.
    args = [{"media_urn": "media:enc=utf-8;file-path", "value": "[invalid"}]
    payload = cbor2.dumps(args)

    from capdag.bifaci.cartridge_runtime import RuntimeError as _Rt
    with pytest.raises(_Rt) as exc_info:
        extract_effective_payload(payload, "application/cbor", cap, False)
    err = str(exc_info.value)
    assert "Invalid glob pattern" in err, "Error should mention invalid glob"


# TEST360: Extract effective payload handles file-path data correctly
def test_360_extract_effective_payload_with_file_data(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test360.pdf"
    pdf_content = b"PDF content for extraction test"
    test_file.write_bytes(pdf_content)

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process",
        "process",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    cli_args = [str(test_file)]
    # The full CLI flow (build_payload_from_cli + extract_effective_payload)
    # delivers a CBOR args array with the file bytes inlined into the matching
    # arg's value.
    payload = runtime.build_payload_from_cli(cap, cli_args)
    effective = extract_effective_payload(payload, "application/cbor", cap, True)
    arr = cbor2.loads(effective)
    assert len(arr) == 1
    assert arr[0]["value"] == pdf_content


# TEST361: CLI mode with file path - pass file path as command-line argument
def test_361_cli_mode_file_path(tmp_path):
    from capdag.cap.definition import CapArg, StdinSource, PositionSource

    test_file = tmp_path / "test361.pdf"
    pdf_content = b"PDF content for CLI file path test"
    test_file.write_bytes(pdf_content)

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process",
        "process",
        [CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
                PositionSource(0),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # CLI mode: pass file path as positional argument; runtime reads the file
    # in extract_effective_payload and relabels media_urn to the stdin source.
    cli_args = [str(test_file)]
    cap = runtime.find_cap_by_command(runtime.manifest, cap.command)
    payload = runtime.build_payload_from_cli(cap, cli_args)
    effective = extract_effective_payload(payload, "application/cbor", cap, True)
    arr = cbor2.loads(effective)
    assert len(arr) == 1
    assert arr[0]["media_urn"] == "media:ext=pdf"
    assert arr[0]["value"] == pdf_content


# TEST362: CLI mode with binary piped in - pipe binary data via stdin This test simulates real-world conditions: - Pure binary data piped to stdin (NOT CBOR) - CLI mode detected (command arg present) - Cap accepts stdin source - Binary is chunked on-the-fly and accumulated - Handler receives complete CBOR payload
def test_362_cli_mode_piped_binary():
    from capdag.cap.definition import CapArg, StdinSource
    import io

    # Simulate large binary being piped (1MB PDF)
    pdf_content = bytes([0xAB] * 1_000_000)

    # Create cap that accepts stdin
    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process",
        "process",
        [CapArg(
            media_urn="media:ext=pdf",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # Mock stdin with BytesIO (simulates piped binary)
    mock_stdin = io.BytesIO(pdf_content)

    # Build payload from streaming reader (what CLI piped mode does)
    from capdag.bifaci.frame import DEFAULT_MAX_CHUNK
    payload = runtime._build_payload_from_streaming_reader(cap, mock_stdin, DEFAULT_MAX_CHUNK)

    # Verify payload is CBOR array with correct structure
    cbor_val = cbor2.loads(payload)
    assert isinstance(cbor_val, list), "Expected CBOR array"
    assert len(cbor_val) == 1, "CBOR array should have one argument"

    arg_map = cbor_val[0]
    assert isinstance(arg_map, dict), "Expected Map in CBOR array"

    media_urn = arg_map.get("media_urn")
    value = arg_map.get("value")

    assert media_urn == "media:ext=pdf", "Media URN should match cap in_spec"
    assert value == pdf_content, "Binary content should be preserved exactly"


# TEST363: CBOR mode with chunked content - send file content streaming as chunks
def test_363_cbor_mode_chunked_content():
    from capdag.cap.definition import CapArg, StdinSource

    pdf_content = bytes([0xAA] * 10000)  # 10KB of data
    received_data = []

    class StreamingOp(Op):
        async def perform(self, dry, wet):
            req = wet.get_required(WET_KEY_REQUEST)
            frames_q = req.take_frames()
            total = bytearray()
            for frame in iter(frames_q.get, None):
                if frame.frame_type == FrameType.CHUNK and frame.payload is not None:
                    total.extend(frame.payload)
                elif frame.frame_type == FrameType.END:
                    break
            cbor_val = cbor2.loads(bytes(total))
            if isinstance(cbor_val, list) and len(cbor_val) > 0:
                arg_map = cbor_val[0]
                if isinstance(arg_map, dict) and "value" in arg_map:
                    received_data.append(arg_map["value"])
        def metadata(self): return OpMetadata.builder("StreamingOp").build()

    cap = create_test_cap(
        'cap:in="media:ext=pdf";process;out=media:void',
        "Process",
        "process",
        [CapArg(
            media_urn="media:ext=pdf",
            required=True,
            sources=[
                StdinSource("media:ext=pdf"),
            ]
        )]
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)
    runtime.register_op(cap.urn_string(), StreamingOp)

    # Build CBOR payload
    from capdag.cap.caller import CapArgumentValue
    args = [CapArgumentValue(media_urn="media:ext=pdf", value=pdf_content)]
    payload_bytes = cbor2.dumps([
        {
            "media_urn": arg.media_urn,
            "value": arg.value,
        }
        for arg in args
    ])

    from capdag.bifaci.frame import compute_checksum
    factory = runtime.find_handler(cap.urn_string())
    assert factory is not None, "Handler not found"

    emitter = CliStreamEmitter()
    frames = queue.Queue()
    max_chunk = 262144
    request_id = MessageId(0)
    stream_id = "test-stream"

    # Send STREAM_START
    frames.put(Frame.stream_start(request_id, stream_id, "media:"))

    # Send CHUNK frames (raw payload bytes, not CBOR-re-encoded)
    offset = 0
    seq = 0
    while offset < len(payload_bytes):
        chunk_size = min(len(payload_bytes) - offset, max_chunk)
        chunk = payload_bytes[offset:offset + chunk_size]
        frames.put(Frame.chunk(request_id, stream_id, seq, chunk, seq, compute_checksum(chunk)))
        offset += chunk_size
        seq += 1

    # Send STREAM_END and END
    frames.put(Frame.stream_end(request_id, stream_id, seq))
    frames.put(Frame.end(request_id, None))
    frames.put(None)

    invoke_op(factory, frames, emitter)

    assert len(received_data) == 1, "Should receive data"
    assert received_data[0] == pdf_content, "Handler should receive chunked content"


# TEST364: CBOR mode with file path - send file path in CBOR arguments (auto-conversion)
def test_364_cbor_mode_file_path(tmp_path):
    test_file = tmp_path / "test364.pdf"
    pdf_content = b"PDF content for CBOR file path test"
    test_file.write_bytes(pdf_content)

    # Build CBOR arguments with file-path URN
    from capdag.cap.caller import CapArgumentValue
    args = [CapArgumentValue(
        media_urn="media:enc=utf-8;file-path",
        value=str(test_file).encode('utf-8'),
    )]
    payload = cbor2.dumps([
        {
            "media_urn": arg.media_urn,
            "value": arg.value,
        }
        for arg in args
    ])

    # Verify the CBOR structure is correct
    decoded = cbor2.loads(payload)
    assert isinstance(decoded, list), "Expected CBOR array"
    assert len(decoded) == 1, "Expected 1 argument"

    arg_map = decoded[0]
    assert isinstance(arg_map, dict), "Expected map"

    media_urn = arg_map.get("media_urn")
    value = arg_map.get("value")

    assert media_urn == "media:enc=utf-8;file-path", "Expected media:file-path URN"
    assert value == str(test_file).encode('utf-8'), "Expected file path as value"


# TEST395: Small payload (< max_chunk) produces correct CBOR arguments
def test_395_build_payload_small():
    cap = create_test_cap(
        'cap:in=media:;process;out=media:void',
        "Process",
        "process",
        [],
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    data = b"small payload"
    reader = io.BytesIO(data)

    from capdag.bifaci.frame import DEFAULT_MAX_CHUNK
    payload = runtime._build_payload_from_streaming_reader(cap, reader, DEFAULT_MAX_CHUNK)

    # Verify CBOR structure
    cbor_val = cbor2.loads(payload)
    assert isinstance(cbor_val, list), f"Expected list, got: {type(cbor_val)}"
    assert len(cbor_val) == 1, f"Should have one argument, got: {len(cbor_val)}"

    arg_map = cbor_val[0]
    assert isinstance(arg_map, dict), f"Expected dict, got: {type(arg_map)}"
    assert "value" in arg_map, "Argument should have 'value' field"

    value_bytes = arg_map["value"]
    assert isinstance(value_bytes, bytes), f"Expected bytes, got: {type(value_bytes)}"
    assert value_bytes == data, f"Payload bytes should match, expected: {data}, got: {value_bytes}"


# TEST396: Large payload (> max_chunk) accumulates across chunks correctly
def test_396_build_payload_large():
    cap = create_test_cap(
        'cap:in=media:;process;out=media:void',
        "Process",
        "process",
        [],
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    # Use small max_chunk to force multi-chunk
    data = bytes(i % 256 for i in range(1000))
    reader = io.BytesIO(data)

    payload = runtime._build_payload_from_streaming_reader(cap, reader, 100)

    cbor_val = cbor2.loads(payload)
    arr = cbor_val
    arg_map = arr[0]
    value_bytes = arg_map["value"]

    assert len(value_bytes) == 1000, f"All bytes should be accumulated, expected: 1000, got: {len(value_bytes)}"
    assert value_bytes == data, "Data should match exactly"


# TEST397: Empty reader produces valid empty CBOR arguments
def test_397_build_payload_empty():
    cap = create_test_cap(
        'cap:in=media:;process;out=media:void',
        "Process",
        "process",
        [],
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    reader = io.BytesIO(b"")

    from capdag.bifaci.frame import DEFAULT_MAX_CHUNK
    payload = runtime._build_payload_from_streaming_reader(cap, reader, DEFAULT_MAX_CHUNK)

    cbor_val = cbor2.loads(payload)
    arr = cbor_val
    arg_map = arr[0]
    value_bytes = arg_map["value"]

    assert len(value_bytes) == 0, f"Empty reader should produce empty bytes, got: {len(value_bytes)} bytes"


# ErrorReader that simulates an IO error
class ErrorReader:
    def read(self, size=-1):
        raise IOError("simulated read error")


# TEST398: IO error from reader propagates as RuntimeError::Io
def test_398_build_payload_io_error():
    cap = create_test_cap(
        'cap:in=media:;process;out=media:void',
        "Process",
        "process",
        [],
    )

    manifest = create_test_manifest("TestCartridge", "1.0.0", "Test", [cap])
    runtime = CartridgeRuntime.with_manifest(manifest)

    reader = ErrorReader()

    from capdag.bifaci.frame import DEFAULT_MAX_CHUNK
    with pytest.raises(IOError) as exc_info:
        runtime._build_payload_from_streaming_reader(cap, reader, DEFAULT_MAX_CHUNK)

    assert "simulated read error" in str(exc_info.value), f"Expected 'simulated read error', got: {exc_info.value}"


# TEST478: CartridgeRuntime auto-registers identity and discard handlers on construction
def test_478_auto_registers_identity_and_discard_handlers():
    runtime = CartridgeRuntime.with_manifest_json(VALID_MANIFEST)

    assert runtime.find_handler(CAP_IDENTITY) is not None
    assert runtime.find_handler(CAP_DISCARD) is not None
    assert runtime.find_handler('cap:in=media:void;nonexistent;out=media:void') is None


# TEST479: Custom identity Op overrides auto-registered default
def test_479_custom_identity_overrides_default():
    class FailOp(Op):
        async def perform(self, dry, wet):
            raise ExecutionFailedError("custom identity")
        def metadata(self): return OpMetadata.builder("FailOp").build()

    runtime = CartridgeRuntime.with_manifest_json(VALID_MANIFEST)

    # Auto-registered identity handler must exist
    assert runtime.find_handler(CAP_IDENTITY) is not None, "Auto-registered identity must exist"

    # Count handlers before override
    handlers_before = len(runtime.handlers)

    # Override identity with a custom Op
    runtime.register_op_type(CAP_IDENTITY, FailOp)

    # Handler count must not change (dict insert replaces, doesn't add)
    assert len(runtime.handlers) == handlers_before, \
        "Replacing identity must not increase handler count"

    # Custom Op must be invoked (not the default)
    factory = runtime.find_handler(CAP_IDENTITY)
    assert factory is not None
    frames = make_test_frames("media:", b"test")
    emitter = CliStreamEmitter()
    with pytest.raises(Exception) as exc_info:
        invoke_op(factory, frames, emitter)
    assert "custom identity" in str(exc_info.value), \
        f"Custom identity Op must be called: {exc_info.value}"


# =============================================================================
# Mock frame writer for OutputStream/emitter tests
# =============================================================================

class MockFrameWriter:
    """Mock FrameWriter that captures frames in a list."""
    def __init__(self):
        self.frames = []
        self.limits = None

    def write(self, frame):
        self.frames.append(frame)

    def set_limits(self, limits):
        self.limits = limits


def make_mock_emitter(media_urn="media:test"):
    """Create a ThreadSafeEmitter backed by a MockFrameWriter for testing."""
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    request_id = MessageId.new_uuid()
    emitter = ThreadSafeEmitter(
        writer=sync_writer,
        request_id=request_id,
        stream_id="s1",
        media_urn=media_urn,
        routing_id=None,
        max_chunk=DEFAULT_MAX_CHUNK,
    )
    return emitter, mock_writer


def make_input_stream(media_urn: str, items):
    q = queue.Queue()
    for item in items:
        q.put(item)
    q.put(None)
    return InputStream(media_urn, q)


def make_input_package(streams):
    q = queue.Queue()
    for stream in streams:
        q.put(stream)
    q.put(None)
    return InputPackage(q)


# TEST529: InputStream recv yields chunks in order
def test_529_input_stream_recv_order():
    stream = make_input_stream("media:test", [b"chunk1", b"chunk2", b"chunk3"])

    collected = []
    while True:
        item = stream.recv_data()
        if item is None:
            break
        collected.append(item)

    assert collected == [b"chunk1", b"chunk2", b"chunk3"]


# TEST530: InputStream::collect_bytes concatenates byte chunks
def test_530_input_stream_collect_bytes():
    stream = make_input_stream("media:", [b"hello", b" ", b"world"])
    assert stream.collect_bytes() == b"hello world"


# TEST531: InputStream::collect_bytes handles text chunks
def test_531_input_stream_collect_bytes_text():
    stream = make_input_stream("media:text", ["hello", " world"])
    assert stream.collect_bytes() == b"hello world"


# TEST532: InputStream empty stream produces empty bytes
def test_532_input_stream_empty():
    stream = make_input_stream("media:void", [])
    assert stream.collect_bytes() == b""


# TEST533: InputStream propagates errors
def test_533_input_stream_error_propagation():
    stream = make_input_stream("media:test", [b"data", CartridgeRuntimeError("test error")])
    with pytest.raises(CartridgeRuntimeError) as exc_info:
        stream.collect_bytes()
    assert str(exc_info.value) == "test error"


# TEST534: InputStream::media_urn returns correct URN
def test_534_input_stream_media_urn():
    stream = make_input_stream("media:image;format=png", [b"data"])
    assert stream.media_urn() == "media:image;format=png"


# TEST535: InputPackage recv yields streams
def test_535_input_package_iteration():
    package = make_input_package(
        [
            make_input_stream("media:stream0", [b"stream0"]),
            make_input_stream("media:stream1", [b"stream1"]),
            make_input_stream("media:stream2", [b"stream2"]),
        ]
    )

    streams = []
    while True:
        item = package.recv()
        if item is None:
            break
        streams.append(item)

    assert len(streams) == 3
    assert [stream.media_urn() for stream in streams] == [
        "media:stream0",
        "media:stream1",
        "media:stream2",
    ]


# TEST536: InputPackage::collect_all_bytes aggregates all streams
def test_536_input_package_collect_all_bytes():
    package = make_input_package(
        [
            make_input_stream("media:s1", [b"hello"]),
            make_input_stream("media:s2", [b" world"]),
        ]
    )
    assert package.collect_all_bytes() == b"hello world"


# TEST537: InputPackage empty package produces empty bytes
def test_537_input_package_empty():
    package = make_input_package([])
    assert package.collect_all_bytes() == b""


# TEST538: InputPackage propagates stream errors
def test_538_input_package_error_propagation():
    package = make_input_package(
        [
            make_input_stream("media:good", [b"data"]),
            make_input_stream("media:bad", [CartridgeRuntimeError("stream error")]),
        ]
    )
    with pytest.raises(CartridgeRuntimeError) as exc_info:
        package.collect_all_bytes()
    assert str(exc_info.value) == "stream error"


# =============================================================================
# PeerCall / PeerResponse Tests
# =============================================================================

# TEST539: OutputStream sends STREAM_START on first write
def test_539_output_stream_sends_stream_start():
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    stream = OutputStream(
        writer=sync_writer,
        request_id=MessageId.new_uuid(),
        stream_id="stream-1",
        media_urn="media:test",
        max_chunk=256_000,
    )

    stream.start(False, None)
    stream.emit_cbor(b"test")

    assert len(mock_writer.frames) >= 2
    assert mock_writer.frames[0].frame_type == FrameType.STREAM_START
    assert mock_writer.frames[0].stream_id == "stream-1"


# TEST540: OutputStream::close sends STREAM_END with correct chunk_count
def test_540_output_stream_close_sends_stream_end():
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    stream = OutputStream(
        writer=sync_writer,
        request_id=MessageId.new_uuid(),
        stream_id="stream-1",
        media_urn="media:test",
        max_chunk=256_000,
    )

    stream.start(False, None)
    stream.emit_cbor(b"chunk1")
    stream.emit_cbor(b"chunk2")
    stream.emit_cbor(b"chunk3")
    stream.close()

    stream_end = next(frame for frame in mock_writer.frames if frame.frame_type == FrameType.STREAM_END)
    assert stream_end.chunk_count == 3


# TEST541: OutputStream chunks large data correctly
def test_541_output_stream_chunks_large_data():
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    stream = OutputStream(
        writer=sync_writer,
        request_id=MessageId.new_uuid(),
        stream_id="stream-1",
        media_urn="media:",
        max_chunk=100,
    )

    stream.start(False, None)
    stream.emit_cbor(bytes([0xAA]) * 250)
    stream.close()

    chunks = [frame for frame in mock_writer.frames if frame.frame_type == FrameType.CHUNK]
    assert len(chunks) >= 3


# TEST542: OutputStream empty stream sends STREAM_START and STREAM_END only
def test_542_output_stream_empty():
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    stream = OutputStream(
        writer=sync_writer,
        request_id=MessageId.new_uuid(),
        stream_id="stream-1",
        media_urn="media:void",
        max_chunk=256_000,
    )

    stream.start(False, None)
    stream.close()

    assert any(frame.frame_type == FrameType.STREAM_START for frame in mock_writer.frames)
    assert any(frame.frame_type == FrameType.STREAM_END for frame in mock_writer.frames)
    assert sum(1 for frame in mock_writer.frames if frame.frame_type == FrameType.CHUNK) == 0


# TEST543: PeerCall::arg creates OutputStream with correct stream_id
def test_543_peer_call_arg_creates_stream():
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    peer = PeerCall(
        writer=sync_writer,
        request_id=MessageId.new_uuid(),
        max_chunk=256_000,
    )

    arg_stream = peer.arg("media:argument")
    assert arg_stream.media_urn == "media:argument"
    assert arg_stream.stream_id != ""


# TEST544: PeerCall::finish sends END frame
def test_544_peer_invoker_sends_end_frame():
    """PeerInvokerImpl sends END frame after all args."""
    from capdag.bifaci.frame import compute_checksum

    # Create a mock writer that captures frames
    mock_writer = MockFrameWriter()
    sync_writer = SyncFrameWriter(mock_writer)
    pending_requests = {}

    from capdag.bifaci.cartridge_runtime import PeerInvokerImpl
    peer = PeerInvokerImpl(
        writer=sync_writer,
        pending_requests=pending_requests,
        max_chunk=DEFAULT_MAX_CHUNK,
    )

    args = [CapArgumentValue.from_str("media:test", "hello")]
    response_queue = peer.invoke('cap:in=media:void;test;out=media:void', args)

    # Check that frames include END
    end_frames = [f for f in mock_writer.frames if f.frame_type == FrameType.END]
    assert len(end_frames) == 1, f"Expected 1 END frame, got {len(end_frames)}"


# TEST545: PeerCall::finish returns PeerResponse with data
def test_545_peer_response_returns_data():
    """demux_peer_response yields data items from peer response frames."""
    from capdag.bifaci.frame import compute_checksum

    req_id = MessageId.new_uuid()
    raw_queue = queue.Queue()

    # STREAM_START
    raw_queue.put(Frame.stream_start(req_id, "s1", "media:binary"))

    # CHUNK with CBOR-encoded bytes
    data = b"response data"
    cbor_payload = cbor2.dumps(data)
    raw_queue.put(Frame.chunk(req_id, "s1", 0, cbor_payload, 0, compute_checksum(cbor_payload)))

    # STREAM_END + sentinel
    raw_queue.put(Frame.stream_end(req_id, "s1", 1))
    raw_queue.put(None)

    response = demux_peer_response(raw_queue)
    result = response.collect_bytes()
    assert result == b"response data"


# TEST839: LOG frames arriving BEFORE StreamStart are delivered immediately This tests the critical fix: during a peer call, the peer (e.g., modelcartridge) sends LOG frames for minutes during model download BEFORE sending any data (StreamStart + Chunk). The handler must receive these LOGs in real-time so it can re-emit progress and keep the engine's activity timer alive. Previously, demux_single_stream blocked on awaiting StreamStart before returning PeerResponse, which meant the handler couldn't call recv() until data arrived — causing 120s activity timeouts during long downloads.
def test_839_peer_response_delivers_logs_before_stream_start():
    from capdag.bifaci.frame import compute_checksum

    req_id = MessageId.new_uuid()
    raw_queue = queue.Queue()

    # Send LOG frames BEFORE any StreamStart — simulates modelcartridge
    # sending download progress before the actual data response
    raw_queue.put(Frame.progress(req_id, 0.1, "downloading file 1/10"))
    raw_queue.put(Frame.progress(req_id, 0.5, "downloading file 5/10"))
    raw_queue.put(Frame.log(req_id, "status", "large file in progress"))

    # Now send the actual data
    raw_queue.put(Frame.stream_start(req_id, "s1", "media:binary"))

    data = b"model output"
    cbor_payload = cbor2.dumps(data)
    raw_queue.put(Frame.chunk(req_id, "s1", 0, cbor_payload, 0, compute_checksum(cbor_payload)))
    raw_queue.put(Frame.stream_end(req_id, "s1", 1))
    raw_queue.put(None)

    response = demux_peer_response(raw_queue)

    # Handler must be able to recv() LOG frames right away
    item1 = response.recv()
    assert item1 is not None
    assert item1.is_log
    assert item1.log.log_progress() == pytest.approx(0.1, abs=0.01)
    assert item1.log.log_message() == "downloading file 1/10"

    item2 = response.recv()
    assert item2 is not None
    assert item2.is_log
    assert item2.log.log_progress() == pytest.approx(0.5, abs=0.01)
    assert item2.log.log_message() == "downloading file 5/10"

    item3 = response.recv()
    assert item3 is not None
    assert item3.is_log
    assert item3.log.log_message() == "large file in progress"

    # Data must arrive after the LOGs
    item4 = response.recv()
    assert item4 is not None
    assert item4.is_data
    assert item4.data_value == b"model output"

    assert response.recv() is None, "stream must end after STREAM_END"


# TEST840: PeerResponse::collect_bytes discards LOG frames
def test_840_peer_response_collect_bytes_discards_logs():
    from capdag.bifaci.frame import compute_checksum

    req_id = MessageId.new_uuid()
    raw_queue = queue.Queue()

    # STREAM_START
    raw_queue.put(Frame.stream_start(req_id, "s1", "media:binary"))

    # LOG frames (should be discarded by collect_bytes)
    raw_queue.put(Frame.progress(req_id, 0.25, "working"))
    raw_queue.put(Frame.progress(req_id, 0.75, "almost"))

    # CHUNK
    cbor_payload = cbor2.dumps(b"hello")
    raw_queue.put(Frame.chunk(req_id, "s1", 0, cbor_payload, 0, compute_checksum(cbor_payload)))

    # Another LOG
    raw_queue.put(Frame.log(req_id, "info", "done"))

    # STREAM_END + sentinel
    raw_queue.put(Frame.stream_end(req_id, "s1", 1))
    raw_queue.put(None)

    response = demux_peer_response(raw_queue)
    result = response.collect_bytes()
    assert result == b"hello", "collect_bytes must return only data, discarding all LOG frames"


# TEST841: PeerResponse::collect_value discards LOG frames
def test_841_peer_response_collect_value_discards_logs():
    from capdag.bifaci.frame import compute_checksum

    req_id = MessageId.new_uuid()
    raw_queue = queue.Queue()

    # STREAM_START
    raw_queue.put(Frame.stream_start(req_id, "s1", "media:binary"))

    # LOG frames before the data value
    raw_queue.put(Frame.progress(req_id, 0.5, "half"))
    raw_queue.put(Frame.log(req_id, "debug", "processing"))

    # Single CHUNK with a CBOR integer
    cbor_payload = cbor2.dumps(42)
    raw_queue.put(Frame.chunk(req_id, "s1", 0, cbor_payload, 0, compute_checksum(cbor_payload)))

    # STREAM_END + sentinel
    raw_queue.put(Frame.stream_end(req_id, "s1", 1))
    raw_queue.put(None)

    response = demux_peer_response(raw_queue)
    value = response.collect_value()
    assert value == 42, "collect_value must skip LOG frames and return first data value"


# =============================================================================
# find_stream / require_stream Tests
# =============================================================================

# TEST678: find_stream with exact equivalent URN (same tags, different order) succeeds
def test_678_find_stream_equivalent_urn():
    streams = [
        ("media:enc=utf-8;ext=txt", b"hello world"),
    ]
    result = find_stream(streams, "media:enc=utf-8;ext=txt")
    assert result == b"hello world"


# TEST679: find_stream with base URN vs full URN fails — is_equivalent is strict This is the root cause of the cartridge_client.rs bug. Sender sent "media:llm-generation-request" but receiver looked for "media:fmt=json;llm-generation-request;record".
def test_679_find_stream_base_vs_full_fails():
    streams = [
        ("media:enc=utf-8;ext=txt", b"hello"),
    ]
    result = find_stream(streams, "media:enc=utf-8")
    assert result is None, "Base URN must not match more specific URN (is_equivalent is strict)"


# TEST680: require_stream with missing URN returns hard StreamError
def test_680_require_stream_missing_fails():
    streams = [
        ("media:enc=utf-8;ext=txt", b"hello"),
    ]
    with pytest.raises(CartridgeRuntimeError) as exc_info:
        require_stream(streams, "media:binary")
    assert "Missing required arg" in str(exc_info.value)


# TEST681: find_stream with multiple streams returns the correct one
def test_681_find_stream_multiple():
    streams = [
        ("media:enc=utf-8;ext=txt", b"text data"),
        ("media:ext=png;image", b"image data"),
        ("media:fmt=json", b"json data"),
    ]
    assert find_stream(streams, "media:ext=png;image") == b"image data"
    assert find_stream(streams, "media:enc=utf-8;ext=txt") == b"text data"
    assert find_stream(streams, "media:fmt=json") == b"json data"


# TEST682: require_stream_str returns UTF-8 string for text data
def test_682_require_stream_returns_data():
    streams = [
        ("media:enc=utf-8;ext=txt", b"hello text"),
    ]
    result = require_stream(streams, "media:enc=utf-8;ext=txt")
    assert result == b"hello text"


# TEST683: find_stream returns None for invalid media URN string (not a parse error — just None)
def test_683_find_stream_invalid_urn_returns_none():
    streams = [
        ("media:enc=utf-8;ext=txt", b"data"),
    ]
    found = find_stream(streams, "")
    assert found is None, "Invalid URN must return None, not panic"


# =============================================================================
# ProgressSender Tests
# =============================================================================

# TEST842: run_with_keepalive returns closure result (fast operation, no keepalive frames)
def test_842_progress_sender_emits_frames():
    emitter, mock_writer = make_mock_emitter()

    ps = emitter.progress_sender()
    ps.progress(0.5, "halfway there")
    ps.log("info", "loading complete")

    # Filter out non-LOG frames (emitter may send STREAM_START etc)
    log_frames = [f for f in mock_writer.frames if f.frame_type == FrameType.LOG]
    assert len(log_frames) == 2, f"ProgressSender should emit 2 LOG frames, got {len(log_frames)}"
    assert log_frames[0].log_progress() == pytest.approx(0.5, abs=0.01)
    assert log_frames[0].log_message() == "halfway there"
    assert log_frames[1].log_level() == "info"
    assert log_frames[1].log_message() == "loading complete"


# TEST843: run_with_keepalive returns Ok/Err from closure
def test_843_progress_sender_from_background_thread():
    import threading

    emitter, mock_writer = make_mock_emitter()
    ps = emitter.progress_sender()

    results = []

    def background_work():
        ps.progress(0.25, "quarter")
        results.append("done")

    thread = threading.Thread(target=background_work)
    thread.start()
    thread.join(timeout=5.0)

    assert results == ["done"]
    log_frames = [f for f in mock_writer.frames if f.frame_type == FrameType.LOG]
    assert len(log_frames) == 1
    assert log_frames[0].log_progress() == pytest.approx(0.25, abs=0.01)


# TEST844: run_with_keepalive propagates errors from closure
def test_844_progress_sender_multiple_threads():
    import threading

    emitter, mock_writer = make_mock_emitter()
    ps = emitter.progress_sender()

    def worker(progress_val, msg):
        ps.progress(progress_val, msg)

    threads = [
        threading.Thread(target=worker, args=(0.25, "t1")),
        threading.Thread(target=worker, args=(0.75, "t2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    log_frames = [f for f in mock_writer.frames if f.frame_type == FrameType.LOG]
    assert len(log_frames) == 2, "Both threads must emit progress"
    messages = sorted([f.log_message() for f in log_frames])
    assert messages == ["t1", "t2"]


# TEST845: ProgressSender emits progress and log frames independently of OutputStream
def test_845_progress_sender_independent_of_emitter():
    emitter, mock_writer = make_mock_emitter()

    ps = emitter.progress_sender()
    ps.progress(0.5, "halfway there")
    ps.log("info", "loading complete")

    log_frames = [f for f in mock_writer.frames if f.frame_type == FrameType.LOG]
    assert len(log_frames) == 2, "ProgressSender should emit 2 frames"
    # Verify progress frame has correct progress value
    assert log_frames[0].log_progress() == pytest.approx(0.5, abs=0.01)
    assert log_frames[0].log_message() == "halfway there"
    # Verify log frame
    assert log_frames[1].log_level() == "info"
    assert log_frames[1].log_message() == "loading complete"


# TEST1282: AdapterSelectionOp is auto-registered by CartridgeRuntime
def test_1282_adapter_selection_auto_registered():
    runtime = CartridgeRuntime(VALID_MANIFEST.encode('utf-8'))
    assert runtime.find_handler(CAP_ADAPTER_SELECTION) is not None, \
        "CartridgeRuntime must auto-register adapter selection handler"


# TEST1283: Custom adapter selection Op overrides the default
def test_1283_adapter_selection_custom_override():
    runtime = CartridgeRuntime(VALID_MANIFEST.encode('utf-8'))

    # Verify default is registered
    assert runtime.find_handler(CAP_ADAPTER_SELECTION) is not None

    # Override with custom handler
    class CustomAdapterOp(Op):
        def perform(self, dry: DryContext, wet: WetContext):
            pass
        def metadata(self):
            return OpMetadata.builder("CustomAdapterOp").build()

    runtime.register_op_type(CAP_ADAPTER_SELECTION, CustomAdapterOp)

    # Must still find a handler (the custom one)
    assert runtime.find_handler(CAP_ADAPTER_SELECTION) is not None, \
        "Custom adapter selection handler must be findable after override"
    assert runtime.find_handler(CAP_ADAPTER_SELECTION) is CustomAdapterOp, \
        "Handler after override must be the custom class"
