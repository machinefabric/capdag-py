"""TEST12166: every answer about media and caps is the proved model's.

The rules are proved in capdag/formal (Lean); this is what ties them to this
mirror: every row of ../formal/conformance.json (written by the model,
`lake exe conformance`) is parsed by the media and cap URN parsers here and
must get the model's verdict: between media, the guarantee, the possibility and
the complete reading; between caps, serving, could-serve and the grade of a
request, fitting a pattern, being the same cap, and flowing into one another;
which caps cannot be declared (TEST7123); and what a file is (TEST7124).
The same table runs in every mirror.
"""

import json
import pathlib

from capdag.input_resolver.detection import (
    AdapterVerdict,
    FileMediaCandidate,
    primary_media,
    settle,
    surviving_candidates,
)
from capdag.input_resolver.value_adapter_registry import ValueAdapterRegistry
from capdag.media.spec import MediaValidation
from capdag.urn.cap_query import CapQuery
from capdag.urn.cap_urn import CapUrn, CapUrnError, IllegalDeclarationError
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
        request = CapQuery.from_call(q)
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


def _model_table():
    table_path = pathlib.Path(__file__).resolve().parents[2] / "formal" / "conformance.json"
    return json.loads(table_path.read_text())


# TEST7123: the cap URN parser refuses a cap exactly when the model says it
# cannot be declared, and for the reason the model gives: the bare top form, or
# an effect=none cap whose input is not inside its output. Every other cap over
# every effect, patch included, parses.
def test_7123_admissibility_is_the_models():
    rows = _model_table()["admissible"]
    assert len(rows) == 500, "every cap over the directions, cap-tags and effects"
    wrong = []
    for r in rows:
        try:
            CapUrn.from_string(r["cap"])
            got = None
        except IllegalDeclarationError as e:
            message = str(e)
            if message.startswith("illegal bare top cap"):
                got = "bare_top"
            elif message.startswith("effect=none requires declared input"):
                got = "none_not_inside"
            else:
                got = f"refused: {message}"
        except CapUrnError as e:
            got = f"refused, not as illegal: {e}"
        if got != r["illegal"]:
            wrong.append(f"{r['cap']}: model {r['illegal']}, got {got}")
    assert not wrong, f"{len(wrong)} of {len(rows)} row(s) differ from the model, e.g.\n  " + "\n  ".join(wrong[:8])


# TEST7124: what a file is, decided through the detection module as a host runs
# it: which candidates stand, given what their rules say of the content, the
# consulted adapters and what their cartridges claimed; which of those each line
# of refinement keeps; and which of the kept a host that cannot ask takes. The
# content is one byte, so a rule of at least one byte is met and a rule of at
# least two is not.
def test_7124_detection_is_the_models():
    rows = _model_table()["detect"]
    assert len(rows) == (9 + 81) * 2 * 4, "every rule, owner and claim set over both lists"
    content = b"x"
    rules = {
        "unruled": None,
        "met": MediaValidation(min_length=1),
        "unmet": MediaValidation(min_length=2),
    }
    wrong = []
    for r in rows:
        candidates = [
            FileMediaCandidate(MediaUrn.from_string(c["urn"]), rules[c["rules"]]) for c in r["candidates"]
        ]
        verdict = AdapterVerdict(
            owners=[MediaUrn.from_string(u) for u in r["owners"]],
            claimed=[MediaUrn.from_string(u) for u in r["claims"]],
        )
        survivors = surviving_candidates(content, candidates, verdict)
        stands = [any(s is c.urn for s in survivors) for c in candidates]
        if stands != r["stands"]:
            wrong.append(f"{r}: stands {stands}")
            continue
        kept = settle(survivors, ValueAdapterRegistry(), content)
        most_specific = [s.to_string() in kept for s in survivors]
        if most_specific != r["most_specific"] or len(kept) != sum(r["most_specific"]):
            wrong.append(f"{r}: kept {kept}")
            continue
        primary = primary_media(kept)
        expected = None if r["primary"] is None else kept[r["primary"]]
        if primary != expected:
            wrong.append(f"{r}: primary {primary}")
    assert not wrong, f"{len(wrong)} of {len(rows)} row(s) differ from the model, e.g.\n  " + "\n  ".join(wrong[:8])
