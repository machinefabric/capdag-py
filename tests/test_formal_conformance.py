"""TEST12166: every answer about media and caps is the proved model's.

The rules are proved in capdag/formal (Lean); this is what ties them to this
mirror: every row of ../formal/conformance.json (written by the model,
`lake exe conformance`) is parsed by the media and cap URN parsers here and
must get the model's verdict: between media, the guarantee, the possibility and
the complete reading; between caps, serving, could-serve and the grade of a
request, fitting a pattern, being the same cap, and flowing into one another.
The same table runs in every mirror.
"""

import json
import pathlib

from capdag.urn.cap_query import CapQuery
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
        for name, got in (
            ("refines", a.conforms_to(b)),
            ("meets", a.meets(b)),
            ("satisfies", a.satisfies(b)),
            ("may_satisfy", a.may_satisfy(b)),
        ):
            if got != r[name]:
                wrong.append(f"{a} {name} {b}: model {r[name]}, got {got}")
    for r in table["scores"]:
        u = MediaUrn.from_string(r["urn"])
        got = u.specificity()
        if got != r["score"]:
            wrong.append(f"score {u}: model {r['score']}, got {got}")
    for r in table["dispatch"]:
        c = CapUrn.from_string(r["candidate"])
        q = CapUrn.from_string(r["request"])
        request = CapQuery.from_request(q)
        grade = request.grade(c).value
        if grade != r["grade"]:
            wrong.append(f"grade of {c} for {q}: model {r['grade']}, got {grade}")
        for name, got in (
            ("dispatch", c.is_dispatchable(q)),
            ("dispatch", request.admits(c)),
            ("may_dispatch", c.may_dispatch(q)),
            ("may_dispatch", request.may_admit(c)),
            ("accepts", c.accepts(q)),
            ("accepts", CapQuery.from_pattern(c).admits(q)),
            ("accepts", q.conforms_to(c)),
            ("equivalent", c.is_equivalent(q)),
            ("flows", c.flows_into(q)),
        ):
            if got != r[name]:
                wrong.append(f"{name}: {c} / {q}: model {r[name]}, got {got}")
    assert len(table["refines"]) > 4000 and len(table["dispatch"]) > 30000, "the table is the full one"
    assert not wrong, f"{len(wrong)} row(s) differ from the model, e.g. {wrong[:8]}"
