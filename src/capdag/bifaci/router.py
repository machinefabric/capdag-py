"""Cap Router - Pluggable routing for peer invoke requests

When a plugin sends a peer invoke REQ (calling another cap), the host needs to route
that request to an appropriate handler. This module provides a protocol-based abstraction
for different routing strategies.
"""

from abc import ABC, abstractmethod
from typing import Any

from capdag.bifaci.host_runtime import AsyncHostError, PeerInvokeNotSupported


class PeerRequestHandle(ABC):
    """Handle for an active peer invoke request.

    The PluginHostRuntime creates this by calling router.begin_request(), then forwards
    incoming frames (STREAM_START, CHUNK, STREAM_END, END) to the handle.
    """

    @abstractmethod
    def forward_frame(self, frame: Any) -> None:
        """Forward an incoming frame to the target plugin."""
        ...

    @abstractmethod
    def response_receiver(self) -> Any:
        """Get a receiver/iterator for response chunks from the target plugin."""
        ...


class CapRouter(ABC):
    """Trait for routing cap invocation requests to appropriate handlers.

    When a plugin issues a peer invoke, the host receives a REQ frame and calls
    begin_request(). The router returns a handle that the host uses to forward
    incoming argument streams and receive responses.
    """

    @abstractmethod
    def begin_request(
        self, cap_urn: str, req_id: bytes
    ) -> PeerRequestHandle:
        """Begin routing a peer invoke request.

        Args:
            cap_urn: The cap URN being requested
            req_id: The 16-byte request ID from the REQ frame

        Returns:
            A PeerRequestHandle for forwarding frames and receiving responses.

        Raises:
            AsyncHostError: If routing fails (NoHandler, PeerInvokeNotSupported, etc.)
        """
        ...


class NoPeerRouter(CapRouter):
    """No-op router that rejects all peer invoke requests."""

    def begin_request(
        self, cap_urn: str, req_id: bytes
    ) -> PeerRequestHandle:
        raise PeerInvokeNotSupported(cap_urn)
