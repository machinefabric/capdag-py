"""What the host allows the cartridges it serves to do (12.2 §Policy).

The engine holds the live policy and gives it to the RelaySwitch; a POLICY
frame carries it through every relay to each host, which keeps the latest and
sends it to each of its cartridges after the handshake and on every change. A
cartridge runtime keeps the latest in a `LivePolicy`, and a handler reads it
through `NetworkAccess` (`cartridge_runtime`) before each call it makes to the
network — never a copy taken when the request was dispatched, so a change to
``offline`` stops a running download or stream at its next call.
(matches Rust bifaci::policy)
"""

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

# The wire key a Policy frame's meta names the network policy by.
POLICY_META_NETWORK = "network"

# The code a call the policy does not allow fails with.
NETWORK_POLICY_CODE = "NETWORK_POLICY"

# The code of a call refused because no policy has been given at all — a
# defect, not the operator's decision.
NETWORK_POLICY_UNSET_CODE = "NETWORK_POLICY_UNSET"


class NetworkPolicy(Enum):
    """How far a cartridge may reach on the network."""

    OFFLINE = "offline"  # nothing beyond this machine
    NO_TELEMETRY = "no_telemetry"  # outside services and ours, never analytics
    FULL = "full"  # the same, and analytics

    def as_str(self) -> str:
        return self.value

    @classmethod
    def from_wire(cls, word: str) -> Optional["NetworkPolicy"]:
        """The policy a wire word names; None for any other word. A word
        nobody defined is never read as one of these."""
        for policy in cls:
            if policy.value == word:
                return policy
        return None

    def allows(self, reach: "Reach") -> bool:
        """Whether this policy lets a call of this reach be made."""
        if self is NetworkPolicy.OFFLINE:
            return False
        if self is NetworkPolicy.NO_TELEMETRY:
            return reach is not Reach.TELEMETRY
        return True


class Reach(Enum):
    """What a call to the network reaches, which is what the policy decides on."""

    THIRD_PARTY = "an outside service"
    OUR_SERVICES = "MachineFabric's services"
    TELEMETRY = "analytics"

    def describe(self) -> str:
        return self.value


@dataclass(frozen=True)
class HostPolicy:
    """Everything a Policy frame says."""

    network: NetworkPolicy


class LivePolicy:
    """The latest policy a runtime was given, shared with every handler it
    runs. Empty until the first Policy frame arrives."""

    def __init__(self, policy: Optional[HostPolicy] = None):
        self._lock = threading.Lock()
        self._policy = policy

    def set(self, policy: HostPolicy) -> None:
        """Replace the policy; every reader sees it at its next read."""
        with self._lock:
            self._policy = policy

    def current(self) -> Optional[HostPolicy]:
        """The policy in force, None before the first one was given."""
        with self._lock:
            return self._policy
