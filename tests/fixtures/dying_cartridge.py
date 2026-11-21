"""A cartridge that dies part way through a frame.

It answers the host's handshake, identity check and policy, then takes one
request, says on stderr that it is dying, writes a length prefix that promises
more than follows it, and dies the way ``CAPDAG_TEST_DIE_HOW`` says:
``exit:<code>`` exits with that code, ``abort`` aborts the process. Its
manifest is ``CAPDAG_TEST_DIE_MANIFEST``.
"""

import os
import sys

from capdag.bifaci.frame import Frame, FrameType, compute_checksum
from capdag.bifaci.io import FrameReader, FrameWriter, handshake_accept


def main() -> None:
    how = os.environ["CAPDAG_TEST_DIE_HOW"]
    manifest = os.environ["CAPDAG_TEST_DIE_MANIFEST"].encode("utf-8")
    stdout = sys.stdout.buffer
    reader = FrameReader(sys.stdin.buffer)
    writer = FrameWriter(stdout)

    limits = handshake_accept(reader, writer, manifest, {})
    reader.set_limits(limits)
    writer.set_limits(limits)

    # The host's identity check: echo the payload back.
    identity = reader.read()
    assert identity is not None and identity.frame_type == FrameType.REQ, identity
    body = [reader.read() for _ in range(4)]
    assert [f.frame_type for f in body] == [
        FrameType.STREAM_START, FrameType.CHUNK, FrameType.STREAM_END, FrameType.END,
    ], body
    payload = body[1].payload
    writer.write(Frame.stream_start(identity.id, "identity-verify", "media:"))
    writer.write(Frame.chunk(identity.id, "identity-verify", 0, payload, 0, compute_checksum(payload)))
    writer.write(Frame.stream_end(identity.id, "identity-verify", 1))
    writer.write(Frame.end(identity.id, None))

    policy = reader.read()
    assert policy is not None and policy.frame_type == FrameType.POLICY, policy

    request = reader.read()
    assert request is not None and request.frame_type == FrameType.REQ, request

    sys.stderr.write(f"dying cartridge is dying: {how}\n")
    sys.stderr.flush()
    stdout.write((64).to_bytes(4, "big") + b"part")
    stdout.flush()
    if how == "abort":
        os.abort()
    code = how.removeprefix("exit:")
    os._exit(int(code))


main()
