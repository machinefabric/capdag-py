"""TEST12166: matching, specificity, dispatch and acceptance are the proved model's.

The rules are proved in capdag/formal (Lean); this is what ties them to this
mirror: every row of ../formal/conformance.json (written by the model,
`lake exe conformance`) is parsed by the media and cap URN parsers here and
must get the model's verdict. The same table runs in every mirror.
"""

import json
import pathlib

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


# TEST12166: every row of the proved model's table
def test_12166_the_implementation_is_the_proved_model():
    table_path = pathlib.Path(__file__).resolve().parents[2] / "formal" / "conformance.json"
    table = json.loads(table_path.read_text())
    wrong = []
    for r in table["refines"]:
        a = MediaUrn.from_string(r["instance"])
        b = MediaUrn.from_string(r["pattern"])
        got = a.conforms_to(b)
        if got != r["refines"]:
            wrong.append(f"{a} ⪯ {b}: model {r['refines']}, got {got}")
    for r in table["scores"]:
        u = MediaUrn.from_string(r["urn"])
        got = u.specificity()
        if got != r["score"]:
            wrong.append(f"score {u}: model {r['score']}, got {got}")
    for r in table["dispatch"]:
        c = CapUrn.from_string(r["candidate"])
        q = CapUrn.from_string(r["request"])
        got = c.is_dispatchable(q)
        if got != r["dispatch"]:
            wrong.append(f"{c} serves {q}: model {r['dispatch']}, got {got}")
        got = c.accepts(q)
        if got != r["accepts"]:
            wrong.append(f"{c} accepts {q}: model {r['accepts']}, got {got}")
    assert len(table["refines"]) > 4000 and len(table["dispatch"]) > 20000, "the table is the full one"
    assert not wrong, f"{len(wrong)} row(s) differ from the model, e.g. {wrong[:8]}"
