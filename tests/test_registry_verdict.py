"""The registry-trust vocabulary, mirrored from Rust
``bifaci/registry_verdict.rs``.

These tests pin the same facts its Rust, Go, Swift and JavaScript twins do — a
mirror that drifts stops understanding its own producers, which is the failure
this vocabulary exists to make impossible.
"""

import pytest

from capdag.bifaci.registry_verdict import (
    MANIFEST_SIG_FORMAT,
    RELEASE_KEY_CERT_FORMAT,
    ChainFailureReason,
    RegistryVerdict,
    RegistryVerdictError,
    RegistryRemedy,
    RegistryVerdictState,
    registry_verdict_remedy,
    registry_verdict_state_for_chain_failure,
)

URL = "https://cartridges.example/v1/manifest"
NOW = 1_700_000_000


def test_8150_state_wire_names_match_the_mirrors():
    """TEST8150: the wire vocabulary is closed and matches the other mirrors."""
    assert [state.value for state in RegistryVerdictState] == [
        "verified",
        "pending",
        "offline",
        "unreachable",
        "http_error",
        "malformed",
        "unsigned",
        "untrusted",
        "unverifiable",
        "unenforced",
    ]
    assert [reason.value for reason in ChainFailureReason] == [
        "malformed_envelope",
        "unsupported_envelope_format",
        "malformed_certificate",
        "unsupported_certificate_format",
        "empty_certificate_list",
        "insufficient_root_signatures",
        "expired_certificate",
        "not_yet_valid_certificate",
        "environment_mismatch",
        "key_id_mismatch",
        "no_authorizing_certificate",
        "manifest_signature_invalid",
    ]
    with pytest.raises(ValueError):
        RegistryVerdictState("network_error")


def test_8151_unreadable_format_is_unverifiable_and_rejected_key_is_untrusted():
    """TEST8151: a format this build cannot read is OUR limitation — never the
    registry being untrustworthy, and never a network problem."""
    for unevaluable in (
        ChainFailureReason.MALFORMED_ENVELOPE,
        ChainFailureReason.UNSUPPORTED_ENVELOPE_FORMAT,
        ChainFailureReason.MALFORMED_CERTIFICATE,
        ChainFailureReason.UNSUPPORTED_CERTIFICATE_FORMAT,
        ChainFailureReason.EMPTY_CERTIFICATE_LIST,
    ):
        assert (
            registry_verdict_state_for_chain_failure(unevaluable)
            is RegistryVerdictState.UNVERIFIABLE
        ), f"{unevaluable.value} could not be judged at all"
    for judged in (
        ChainFailureReason.INSUFFICIENT_ROOT_SIGNATURES,
        ChainFailureReason.EXPIRED_CERTIFICATE,
        ChainFailureReason.NOT_YET_VALID_CERTIFICATE,
        ChainFailureReason.ENVIRONMENT_MISMATCH,
        ChainFailureReason.KEY_ID_MISMATCH,
        ChainFailureReason.NO_AUTHORIZING_CERTIFICATE,
        ChainFailureReason.MANIFEST_SIGNATURE_INVALID,
    ):
        assert (
            registry_verdict_state_for_chain_failure(judged)
            is RegistryVerdictState.UNTRUSTED
        ), f"{judged.value} is a judgement that WAS reached"
    with pytest.raises(ValueError):
        registry_verdict_state_for_chain_failure("bad_signature")


def test_8152_only_verified_permits_attachment():
    """TEST8152: only a verified registry lets a cartridge attach — PENDING
    included, which must never read as permission."""
    for state in RegistryVerdictState:
        assert state.permits_attachment == (
            state in (RegistryVerdictState.VERIFIED, RegistryVerdictState.UNENFORCED)
        )
    # A DEV BUILD HAS TO WORK, and it says which of the two it is: "we checked
    # and it passed" and "we did not check" are different facts.
    assert RegistryVerdictState.UNENFORCED.permits_attachment
    assert not RegistryVerdictState.UNENFORCED.is_trust_failure
    assert not RegistryVerdictState.UNENFORCED.is_transient


def test_8153_trust_failures_are_never_transient():
    """TEST8153: a refusal never resolves itself, so nothing may present it as
    worth retrying."""
    for state in RegistryVerdictState:
        assert not (
            state.is_trust_failure and state.is_transient
        ), f"'{state.value}' cannot be both a refusal and something a retry could fix"
    assert RegistryVerdictState.UNVERIFIABLE.is_trust_failure
    assert RegistryVerdictState.UNTRUSTED.is_trust_failure
    assert RegistryVerdictState.UNSIGNED.is_trust_failure
    assert RegistryVerdictState.UNREACHABLE.is_transient
    assert RegistryVerdictState.PENDING.is_transient
    # Policy is not transient: it holds until an operator changes it.
    assert not RegistryVerdictState.OFFLINE.is_transient
    assert not RegistryVerdictState.OFFLINE.is_trust_failure


def test_8159_the_remedy_follows_from_the_state():
    """TEST8159: the remedy follows from the state, and "check the network" is
    reachable from exactly one state. That sentence used to be appended to
    every held-cartridge message whatever the cause, which is how a signature
    format a build could not read sent operators to their router."""
    network = [
        state
        for state in RegistryVerdictState
        if registry_verdict_remedy(state) is RegistryRemedy.CHECK_NETWORK
    ]
    assert network == [RegistryVerdictState.UNREACHABLE], (
        "only a registry we could not reach is a network problem"
    )
    for state in RegistryVerdictState:
        if not state.is_trust_failure:
            continue
        remedy = registry_verdict_remedy(state)
        assert remedy in (RegistryRemedy.DO_NOT_PROCEED, RegistryRemedy.UPDATE_CLIENT), (
            f"'{state.value}' is a refusal; its remedy must not be a retry"
        )
    # The one that was misclassified: our limitation, so update the client —
    # never distrust the registry, never touch the network.
    assert (
        registry_verdict_remedy(RegistryVerdictState.UNVERIFIABLE)
        is RegistryRemedy.UPDATE_CLIENT
    )
    assert (
        registry_verdict_remedy(RegistryVerdictState.UNTRUSTED)
        is RegistryRemedy.DO_NOT_PROCEED
    )
    assert registry_verdict_remedy(RegistryVerdictState.VERIFIED) is RegistryRemedy.NONE
    assert registry_verdict_remedy(RegistryVerdictState.PENDING) is RegistryRemedy.WAIT
    # Policy is the operator's setting, not their router.
    assert (
        registry_verdict_remedy(RegistryVerdictState.OFFLINE)
        is RegistryRemedy.CHANGE_NETWORK_POLICY
    )
    with pytest.raises(ValueError):
        registry_verdict_remedy("flaky")


def test_8154_contradictory_verdicts_are_refused():
    """TEST8154: illegal states are unrepresentable — every contradiction is
    refused at construction and again at the wire boundary."""
    with pytest.raises(RegistryVerdictError, match="must carry the detail"):
        RegistryVerdict.stated(URL, RegistryVerdictState.UNREACHABLE, "", NOW)
    with pytest.raises(RegistryVerdictError, match="states no failure"):
        RegistryVerdict.stated(URL, RegistryVerdictState.VERIFIED, "all good", NOW)
    with pytest.raises(RegistryVerdictError, match="must carry the status"):
        RegistryVerdict.stated(URL, RegistryVerdictState.HTTP_ERROR, "500", NOW)
    with pytest.raises(RegistryVerdictError, match="chain failure reason"):
        RegistryVerdict.stated(URL, RegistryVerdictState.UNTRUSTED, "nope", NOW)
    with pytest.raises(RegistryVerdictError, match="must name the registry"):
        RegistryVerdict.stated("", RegistryVerdictState.UNREACHABLE, "timeout", NOW)

    # A status on a state that never answered, smuggled in over the wire.
    with pytest.raises(RegistryVerdictError, match="only an 'http_error'"):
        RegistryVerdict.from_json(
            {
                "registry_url": URL,
                "state": "unreachable",
                "detail": "timeout",
                "http_status": 404,
                "chain_failure": None,
                "checked_at_unix_seconds": NOW,
            }
        )
    # A reason that contradicts the state it is filed under.
    with pytest.raises(RegistryVerdictError, match="chain failure reason"):
        RegistryVerdict.from_json(
            {
                "registry_url": URL,
                "state": "untrusted",
                "detail": "x",
                "http_status": None,
                "chain_failure": "unsupported_envelope_format",
                "checked_at_unix_seconds": NOW,
            }
        )


def test_8155_wire_round_trip_and_refusals():
    """TEST8155: the wire form round-trips with its invariants intact."""
    verdict = RegistryVerdict.chain_failed(
        URL,
        ChainFailureReason.UNSUPPORTED_ENVELOPE_FORMAT,
        "envelope format 'other/1' is not implemented by this build",
        NOW,
    )
    assert verdict.state is RegistryVerdictState.UNVERIFIABLE
    decoded = RegistryVerdict.from_json(verdict.to_json())
    assert decoded == verdict
    assert not decoded.permits_attachment
    assert decoded.chain_failure is ChainFailureReason.UNSUPPORTED_ENVELOPE_FORMAT, (
        "the failing check travels with the verdict, not only in prose"
    )

    http = RegistryVerdict.http_error(URL, 404, "registry answered HTTP 404", NOW)
    assert http.http_status == 404
    assert RegistryVerdict.from_json(http.to_json()).http_status == 404

    with pytest.raises(RegistryVerdictError, match="must carry the status"):
        RegistryVerdict.from_json(
            {
                "registry_url": URL,
                "state": "http_error",
                "detail": "answered badly",
                "http_status": None,
                "chain_failure": None,
                "checked_at_unix_seconds": NOW,
            }
        )
    with pytest.raises(ValueError):
        RegistryVerdict.from_json(
            {
                "registry_url": URL,
                "state": "flaky",
                "detail": "hm",
                "http_status": None,
                "chain_failure": None,
                "checked_at_unix_seconds": NOW,
            }
        )


def test_8157_signature_format_discriminators_come_from_the_library():
    """TEST8157: the format discriminators are the library's, so no consumer
    can hold a divergent copy. A product rename that edits a client's private
    constant makes that client verify nothing while every other implementation
    keeps working — which is precisely what happened."""
    assert MANIFEST_SIG_FORMAT == "machinefabric-manifest-sig/1"
    assert RELEASE_KEY_CERT_FORMAT == "machinefabric-release-key-cert/1"
