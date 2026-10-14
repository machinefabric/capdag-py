"""Complete cap definitions for tests that are not about definitions.

A manifest is held to the definition rules wherever it is read, so a test
that routes frames or stages a cartridge has to advertise definitions a real
cartridge could: the main input declared on stdin, the output `out=` states.
"""

import json

from capdag import Cap, CapArg, CapUrn
from capdag.cap.definition import CapOutput, StdinSource
from capdag.standard.caps import identity_cap
from capdag.urn.media_urn import MEDIA_VOID, MediaUrn


def complete_cap(cap_urn: str, title: str = "Test", alias: str = "test") -> Cap:
    """The smallest definition of ``cap_urn`` that passes every rule: its
    input taken on stdin unless it is void, its output declared unless it is
    void."""
    urn = CapUrn.from_string(cap_urn)
    void = MediaUrn.from_string(MEDIA_VOID)
    cap = Cap(urn, title, [alias])
    if not MediaUrn.from_string(urn.in_spec()).is_equivalent(void):
        cap.add_arg(CapArg(urn.in_spec(), "input", True, [StdinSource(urn.in_spec())]))
    if not MediaUrn.from_string(urn.out_spec()).is_equivalent(void):
        cap.add_output(CapOutput(urn.out_spec(), "output", ""))
    return cap


def complete_cap_json(cap_urn: str, title: str = "Test", alias: str = "test") -> str:
    """``complete_cap`` as the JSON a manifest carries."""
    return json.dumps(complete_cap(cap_urn, title, alias).to_dict(), separators=(",", ":"))


#: The identity cap every manifest declares, as the JSON a manifest carries.
IDENTITY_CAP_JSON = json.dumps(identity_cap().to_dict(), separators=(",", ":"))
