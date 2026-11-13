"""A fabric registry on a local socket, for tests: it answers each request by
its path with a status, a body, or nothing at all, and counts what it was
asked. A real server, so the whole fetch path — connect, send, read — is
exercised as it is against the published fabric.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass(frozen=True)
class Answer:
    """What the stub answers one request with: ``status`` with a short body,
    200 with ``body``, or — ``silence`` — nothing, so the client's timeout
    decides."""

    status: int = 200
    body: Optional[bytes] = None
    silence: bool = False


class StubRegistry:
    def __init__(self, answer: Callable[[str], Answer]):
        self._answer = answer
        self._server: Optional[asyncio.base_events.Server] = None
        self.requests: Counter = Counter()
        self.anchor = ""

    async def __aenter__(self) -> "StubRegistry":
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        host, port = self._server.sockets[0].getsockname()[:2]
        self.anchor = f"http://{host}:{port}"
        return self

    async def __aexit__(self, *exc) -> None:
        self._server.close()

    def requests_for(self, url: str) -> int:
        """How many requests were made for ``url``, a URL on this stub."""
        assert url.startswith(self.anchor), f"{url} is not on the stub at {self.anchor}"
        return self.requests[url[len(self.anchor):]]

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
        except (asyncio.IncompleteReadError, ConnectionError):
            writer.close()
            return
        path = head.split(b"\r\n", 1)[0].split(b" ")[1].decode()
        self.requests[path] += 1
        answer = self._answer(path)
        if answer.silence:
            # Hold the connection open, answering nothing, until the client
            # gives up and closes it.
            await reader.read()
            writer.close()
            return
        body = answer.body if answer.body is not None else f"status {answer.status}".encode()
        writer.write(
            f"HTTP/1.1 {answer.status} STUB\r\nContent-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n".encode()
            + body
        )
        await writer.drain()
        writer.close()
