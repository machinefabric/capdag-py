"""Tests for bifaci router - mirroring capdag Rust tests"""

import pytest
from capdag.bifaci.router import NoPeerRouter
from capdag.bifaci.host_runtime import PeerInvokeNotSupported


# TEST638: NoPeerRouter rejects all requests with PeerInvokeNotSupported
def test_638_no_peer_router_rejects_all():
    router = NoPeerRouter()
    req_id = bytes(16)

    with pytest.raises(PeerInvokeNotSupported) as exc_info:
        router.begin_request(
            'cap:in="media:void";op=test;out="media:void"',
            req_id,
        )

    assert "test" in str(exc_info.value)
