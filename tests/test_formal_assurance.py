"""TEST12597: every function of the proved model this mirror calls carries a proved claim.

The model's package carries what is proved of each function it exports (its assurance document,
generated from ../formal): each one decides, equals or keeps what its claim says, and none rests
on an assumption about the host — the model needs none.
"""

from capdag import _formal


# TEST12597: every function of the proved model this mirror calls carries a proved claim
def test_12597_every_model_function_carries_a_proved_claim():
    a = _formal.ASSURANCE
    assert a.facilities == () and a.assumptions == (), "the model assumes nothing of the host"
    assert a.exports
    for e in a.exports:
        assert e.claims, f"{e.name} carries no claim"
        assert e.assumptions == (), f"{e.name} rests on {e.assumptions}"
        for name in e.claims:
            claim = a.claim(name)
            assert claim.status == "proved", name
            assert e.name in claim.subjects, f"{name} is about {e.name}"
    dispatch = a.claim("CapDAG.Exec.dispatch_decides")
    assert (dispatch.relation, dispatch.specifications) == ("lungo.decides", ("CapDAG.serves",))
