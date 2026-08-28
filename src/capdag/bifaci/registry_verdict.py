"""What a consumer concluded about a cartridge registry, as a closed
vocabulary shared by every implementation. Mirrors Rust
``bifaci/registry_verdict.rs``.

A REGISTRY IS NOT A CARTRIDGE. A registry verdict is one fact per registry
URL, shared by every cartridge that claims provenance from it; a cartridge
attachment error is one fact per cartridge. Squeezing the first through the
second is how a signature that failed verification came to be reported as a
network outage, with "check your connection" as the remedy.

The vocabulary separates the two things a consumer can conclude:

* **It could not get an answer** — ``OFFLINE``, ``UNREACHABLE``,
  ``HTTP_ERROR``, ``MALFORMED``. We do not know what the registry says.
  Retrying, or changing a setting, may change the answer.
* **It got an answer and refused it** — ``UNSIGNED``, ``UNTRUSTED``,
  ``UNVERIFIABLE``. We know what the registry says and we will not act on it.
  Retrying changes nothing.

Those two groups have opposite remedies, which is the whole reason the
distinction exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

#: Format discriminator for release-key certificates. Mirrors Rust
#: ``RELEASE_KEY_CERT_FORMAT``.
#:
#: THE WIRE FORMAT IS NOT A PRODUCT NAME. Every verifier — this library, a
#: client's in-process verifier, the publisher — must compare against THIS
#: constant. A client holding its own copy can be renamed away from the
#: protocol by a search-and-replace, verify nothing, and report the registry as
#: unreachable; that is exactly what happened, and it is why these live here.
RELEASE_KEY_CERT_FORMAT = "machinefabric-release-key-cert/1"

#: Format discriminator for manifest signature envelopes. Mirrors Rust
#: ``MANIFEST_SIG_FORMAT``.
MANIFEST_SIG_FORMAT = "machinefabric-manifest-sig/1"


class RegistryVerdictState(str, Enum):
    """What a consumer concluded about a registry. The value is the
    snake_case wire form."""

    #: Fetched, chain-verified and parsed. The only state in which a
    #: cartridge from this registry may attach.
    VERIFIED = "verified"
    #: No verdict yet — the first check has not run. NOT a failure: a
    #: consumer that renders this as an error tells every operator their
    #: registry is broken for the first seconds of every launch.
    PENDING = "pending"
    #: The consumer's own network policy forbade the request. The remedy is a
    #: setting, not the network, which is why this is not UNREACHABLE.
    OFFLINE = "offline"
    #: DNS, refused, timeout, TLS. The only state for which "check your
    #: connection" is sound advice.
    UNREACHABLE = "unreachable"
    #: The registry answered with an HTTP error; the status travels with the
    #: verdict, because 404 and 5xx are different situations.
    HTTP_ERROR = "http_error"
    #: The registry answered with a body this build cannot read as a manifest.
    MALFORMED = "malformed"
    #: No signature sidecar where one is required. An unsigned registry is
    #: refused rather than trusted.
    UNSIGNED = "unsigned"
    #: The chain was evaluated and REJECTED. The registry's problem.
    UNTRUSTED = "untrusted"
    #: The chain could NOT be evaluated — a format this build does not
    #: implement. Our problem, remedied by updating the client, never by
    #: distrusting the registry and never by checking the network.
    UNVERIFIABLE = "unverifiable"
    #: This build bakes no trust anchors, so there is no regime to verify
    #: against and the manifest was accepted without proof. A development
    #: build, and only ever that. It permits attachment — a dev build has to
    #: work — and is a SEPARATE state rather than being reported as VERIFIED,
    #: because "we checked and it passed" and "we did not check" are different
    #: facts, and a consumer that cannot tell them apart will one day ship the
    #: second believing the first.
    UNENFORCED = "unenforced"

    @property
    def permits_attachment(self) -> bool:
        """Whether a cartridge claiming provenance from a registry in this
        state may attach. True for VERIFIED alone: every other state, the
        hopeful ones included, means the claim is unconfirmed."""
        return self in (
            RegistryVerdictState.VERIFIED,
            RegistryVerdictState.UNENFORCED,
        )

    @property
    def is_trust_failure(self) -> bool:
        """Whether this state is a refusal of an answer we DID get, as
        opposed to not having got one. A refusal will not change on retry."""
        return self in (
            RegistryVerdictState.UNSIGNED,
            RegistryVerdictState.UNTRUSTED,
            RegistryVerdictState.UNVERIFIABLE,
        )

    @property
    def is_transient(self) -> bool:
        """Whether an unattended retry could plausibly reach a different
        verdict. A trust failure never can; neither does a policy that
        forbids the request, until the policy changes."""
        return self in (
            RegistryVerdictState.PENDING,
            RegistryVerdictState.UNREACHABLE,
            RegistryVerdictState.HTTP_ERROR,
            RegistryVerdictState.MALFORMED,
        )


class RegistryRemedy(str, Enum):
    """WHAT TO DO ABOUT A REGISTRY IN A GIVEN STATE. Mirrors Rust
    ``RegistryRemedy``.

    The remedy follows from the state and nothing else. It used to be a
    sentence glued onto the failure message at the point the record was built
    — "Check the network connection and try again." — appended whatever the
    cause, so a signature a build could not read sent operators to their
    router. A remedy asserted as fact regardless of what failed is worse than
    none.

    This is the ACTION, not its wording: a CLI prints a line, a desktop client
    offers a control. Both derive them from here.
    """

    #: Nothing to do — the registry verified.
    NONE = "none"
    #: A check is in flight and will answer on its own.
    WAIT = "wait"
    #: The machine cannot reach the registry. Check the connection.
    CHECK_NETWORK = "check_network"
    #: This build was told not to go out. Change the network policy.
    CHANGE_NETWORK_POLICY = "change_network_policy"
    #: The registry answered badly; it is the registry's side to fix.
    RETRY_LATER = "retry_later"
    #: This build cannot read the registry's signature format. The registry is
    #: not at fault and the network is not involved.
    UPDATE_CLIENT = "update_client"
    #: The registry's answer was rejected. Do not proceed.
    DO_NOT_PROCEED = "do_not_proceed"


_REGISTRY_REMEDY_BY_STATE = {
    RegistryVerdictState.VERIFIED: RegistryRemedy.NONE,
    RegistryVerdictState.PENDING: RegistryRemedy.WAIT,
    RegistryVerdictState.OFFLINE: RegistryRemedy.CHANGE_NETWORK_POLICY,
    RegistryVerdictState.UNREACHABLE: RegistryRemedy.CHECK_NETWORK,
    RegistryVerdictState.HTTP_ERROR: RegistryRemedy.RETRY_LATER,
    RegistryVerdictState.MALFORMED: RegistryRemedy.RETRY_LATER,
    RegistryVerdictState.UNSIGNED: RegistryRemedy.DO_NOT_PROCEED,
    RegistryVerdictState.UNTRUSTED: RegistryRemedy.DO_NOT_PROCEED,
    RegistryVerdictState.UNVERIFIABLE: RegistryRemedy.UPDATE_CLIENT,
    RegistryVerdictState.UNENFORCED: RegistryRemedy.NONE,
}


def registry_verdict_remedy(state: RegistryVerdictState) -> RegistryRemedy:
    """The one thing to do about a registry in this state."""
    return _REGISTRY_REMEDY_BY_STATE[RegistryVerdictState(state)]


class ChainFailureReason(str, Enum):
    """Why a signature chain failed, as a closed vocabulary. Mirrors Rust
    ``ChainFailureReason``."""

    MALFORMED_ENVELOPE = "malformed_envelope"
    UNSUPPORTED_ENVELOPE_FORMAT = "unsupported_envelope_format"
    MALFORMED_CERTIFICATE = "malformed_certificate"
    UNSUPPORTED_CERTIFICATE_FORMAT = "unsupported_certificate_format"
    EMPTY_CERTIFICATE_LIST = "empty_certificate_list"
    INSUFFICIENT_ROOT_SIGNATURES = "insufficient_root_signatures"
    EXPIRED_CERTIFICATE = "expired_certificate"
    NOT_YET_VALID_CERTIFICATE = "not_yet_valid_certificate"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    KEY_ID_MISMATCH = "key_id_mismatch"
    NO_AUTHORIZING_CERTIFICATE = "no_authorizing_certificate"
    MANIFEST_SIGNATURE_INVALID = "manifest_signature_invalid"


#: The reasons that mean the chain could not be EVALUATED, as opposed to being
#: evaluated and rejected.
_UNEVALUABLE_CHAIN_FAILURES = frozenset(
    {
        ChainFailureReason.MALFORMED_ENVELOPE,
        ChainFailureReason.UNSUPPORTED_ENVELOPE_FORMAT,
        ChainFailureReason.MALFORMED_CERTIFICATE,
        ChainFailureReason.UNSUPPORTED_CERTIFICATE_FORMAT,
        ChainFailureReason.EMPTY_CERTIFICATE_LIST,
    }
)


def registry_verdict_state_for_chain_failure(
    reason: ChainFailureReason,
) -> RegistryVerdictState:
    """The verdict a chain failure produces.

    COULD THE CHAIN BE EVALUATED AT ALL? A format this build does not
    implement, or bytes it cannot parse, means no judgement was reached
    (UNVERIFIABLE — update the client). Everything else means the chain WAS
    judged and found wanting (UNTRUSTED — do not proceed). Leaving this
    decision to each consumer is how one client reported an unreadable
    signature format as a network outage.
    """
    reason = ChainFailureReason(reason)
    return (
        RegistryVerdictState.UNVERIFIABLE
        if reason in _UNEVALUABLE_CHAIN_FAILURES
        else RegistryVerdictState.UNTRUSTED
    )


class RegistryVerdictError(ValueError):
    """A verdict that does not describe a possible situation."""


@dataclass(frozen=True)
class RegistryVerdict:
    """What a consumer concluded about one registry, and why. Mirrors Rust
    ``RegistryVerdict``.

    Illegal combinations are unrepresentable: the constructors take exactly
    what their state requires, and ``validate`` re-checks every invariant on
    the way in from the wire. A verdict that says ``http_error`` without a
    status, or ``verified`` with a failure detail, is a bug in the producer
    and is refused at the boundary rather than rendered as a contradiction.
    """

    #: The registry this verdict is about — the verbatim URL a cartridge
    #: declares, which is what consumers join on.
    registry_url: str
    state: RegistryVerdictState
    #: One operator-visible line saying what happened. Empty exactly when the
    #: state states no failure (VERIFIED, PENDING).
    detail: str
    #: The HTTP status the registry answered with. Present exactly on
    #: HTTP_ERROR.
    http_status: Optional[int]
    #: Which chain check failed. Present exactly on UNTRUSTED and
    #: UNVERIFIABLE — never on UNSIGNED, where there was no chain.
    chain_failure: Optional[ChainFailureReason]
    #: When this verdict was reached, unix seconds.
    checked_at_unix_seconds: int

    def __post_init__(self) -> None:
        self.validate()

    @staticmethod
    def verified(registry_url: str, checked_at_unix_seconds: int) -> "RegistryVerdict":
        """The registry answered, verified and parsed."""
        return RegistryVerdict(
            registry_url=registry_url,
            state=RegistryVerdictState.VERIFIED,
            detail="",
            http_status=None,
            chain_failure=None,
            checked_at_unix_seconds=checked_at_unix_seconds,
        )

    @staticmethod
    def unenforced(registry_url: str, checked_at_unix_seconds: int) -> "RegistryVerdict":
        """This build bakes no trust anchors: the manifest was accepted without
        proof, and says so rather than claiming it verified."""
        return RegistryVerdict(
            registry_url=registry_url,
            state=RegistryVerdictState.UNENFORCED,
            detail="",
            http_status=None,
            chain_failure=None,
            checked_at_unix_seconds=checked_at_unix_seconds,
        )

    @staticmethod
    def pending(registry_url: str) -> "RegistryVerdict":
        """No verdict yet. Carries no time, because nothing has been checked."""
        return RegistryVerdict(
            registry_url=registry_url,
            state=RegistryVerdictState.PENDING,
            detail="",
            http_status=None,
            chain_failure=None,
            checked_at_unix_seconds=0,
        )

    @staticmethod
    def stated(
        registry_url: str,
        state: RegistryVerdictState,
        detail: str,
        checked_at_unix_seconds: int,
    ) -> "RegistryVerdict":
        """A state that carries only a detail line: OFFLINE, UNREACHABLE,
        MALFORMED, UNSIGNED. The other states have their own constructors
        because they require more, and this refuses them rather than letting a
        caller build a verdict missing what it needs."""
        state = RegistryVerdictState(state)
        if state is RegistryVerdictState.HTTP_ERROR:
            raise RegistryVerdictError(
                "an 'http_error' verdict must carry the status the registry answered with"
            )
        if state in (RegistryVerdictState.UNTRUSTED, RegistryVerdictState.UNVERIFIABLE):
            raise RegistryVerdictError(
                f"a '{state.value}' verdict must carry the chain failure reason that produced it"
            )
        return RegistryVerdict(
            registry_url=registry_url,
            state=state,
            detail=detail,
            http_status=None,
            chain_failure=None,
            checked_at_unix_seconds=checked_at_unix_seconds,
        )

    @staticmethod
    def http_error(
        registry_url: str, status: int, detail: str, checked_at_unix_seconds: int
    ) -> "RegistryVerdict":
        """The registry answered with an HTTP error."""
        return RegistryVerdict(
            registry_url=registry_url,
            state=RegistryVerdictState.HTTP_ERROR,
            detail=detail,
            http_status=status,
            chain_failure=None,
            checked_at_unix_seconds=checked_at_unix_seconds,
        )

    @staticmethod
    def chain_failed(
        registry_url: str,
        reason: ChainFailureReason,
        detail: str,
        checked_at_unix_seconds: int,
    ) -> "RegistryVerdict":
        """A signature chain that failed. The state FOLLOWS from the reason,
        so a caller cannot file an unreadable format as a rejected key or the
        other way round."""
        reason = ChainFailureReason(reason)
        return RegistryVerdict(
            registry_url=registry_url,
            state=registry_verdict_state_for_chain_failure(reason),
            detail=detail,
            http_status=None,
            chain_failure=reason,
            checked_at_unix_seconds=checked_at_unix_seconds,
        )

    def validate(self) -> None:
        """Every invariant this type promises, checked. A verdict that fails
        this has no meaning and must not travel."""
        if not self.registry_url:
            raise RegistryVerdictError(
                "a registry verdict must name the registry it is about"
            )
        state = RegistryVerdictState(self.state)
        states_no_failure = state in (
            RegistryVerdictState.VERIFIED,
            RegistryVerdictState.PENDING,
            RegistryVerdictState.UNENFORCED,
        )
        if states_no_failure and self.detail:
            raise RegistryVerdictError(
                f"a '{state.value}' verdict states no failure, so it carries no detail "
                f"(got {self.detail!r})"
            )
        if not states_no_failure and not self.detail:
            raise RegistryVerdictError(
                f"a '{state.value}' verdict must carry the detail that explains it"
            )
        if state is RegistryVerdictState.HTTP_ERROR:
            if self.http_status is None:
                raise RegistryVerdictError(
                    "an 'http_error' verdict must carry the status the registry answered with"
                )
        elif self.http_status is not None:
            raise RegistryVerdictError(
                f"only an 'http_error' verdict carries an HTTP status "
                f"(got one on '{state.value}')"
            )
        chain_states = state in (
            RegistryVerdictState.UNTRUSTED,
            RegistryVerdictState.UNVERIFIABLE,
        )
        if chain_states:
            if self.chain_failure is None:
                raise RegistryVerdictError(
                    f"a '{state.value}' verdict must carry the chain failure reason "
                    "that produced it"
                )
            if registry_verdict_state_for_chain_failure(self.chain_failure) is not state:
                raise RegistryVerdictError(
                    f"only a trust failure carries a chain failure reason "
                    f"(got one on '{state.value}')"
                )
        elif self.chain_failure is not None:
            raise RegistryVerdictError(
                f"only a trust failure carries a chain failure reason "
                f"(got one on '{state.value}')"
            )

    @property
    def permits_attachment(self) -> bool:
        """Whether a cartridge from this registry may attach."""
        return RegistryVerdictState(self.state).permits_attachment

    def to_json(self) -> dict[str, Any]:
        return {
            "registry_url": self.registry_url,
            "state": RegistryVerdictState(self.state).value,
            "detail": self.detail,
            "http_status": self.http_status,
            "chain_failure": (
                None
                if self.chain_failure is None
                else ChainFailureReason(self.chain_failure).value
            ),
            "checked_at_unix_seconds": self.checked_at_unix_seconds,
        }

    @staticmethod
    def from_json(data: dict[str, Any]) -> "RegistryVerdict":
        """Decode and validate in one step: a contradictory verdict is refused
        ON THE WAY IN, where the producer can still be named, rather than
        surfacing later as an interface that says two things at once."""
        raw_failure = data.get("chain_failure")
        return RegistryVerdict(
            registry_url=data["registry_url"],
            state=RegistryVerdictState(data["state"]),
            detail=data["detail"],
            http_status=data.get("http_status"),
            chain_failure=None if raw_failure is None else ChainFailureReason(raw_failure),
            checked_at_unix_seconds=int(data["checked_at_unix_seconds"]),
        )
