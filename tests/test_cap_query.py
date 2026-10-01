"""Questions about caps: a side left unknown, and the tags a cap has."""

from capdag import CapQuery, CapUrn, MatchGrade, MediaUrn


def _pages() -> CapUrn:
    return CapUrn.from_string('cap:disbind;in="media:ext=pdf";out="media:enc=utf-8;ext=txt;page"')


def _to_jpeg() -> CapUrn:
    return CapUrn.from_string(
        'cap:convert-image;in="media:ext=png;image";out="media:ext=jpeg;image"'
    )


def _some_image() -> CapUrn:
    return CapUrn.from_string('cap:render;in="media:ext=pdf";out="media:image"')


def _passes_through() -> CapUrn:
    return CapUrn.from_string("cap:decimate-sequence;effect=none")


# TEST12368: "what gives me this, whatever it takes?" and "what can this
# become?" are questions with a side unknown, and each cap answers with a grade.
#
# No cap URN can ask them: `media:` on a side is the type "anything", so a
# request spelled that way asked for a cap that takes everything, and found
# none. The unknown side asks nothing; the stated side is held to.
def test_12368_a_question_may_leave_a_side_unknown():
    wants_jpeg = CapQuery.producing(MediaUrn.from_string("media:ext=jpeg;image"))
    assert wants_jpeg.grade(_to_jpeg()) is MatchGrade.EXACT
    assert wants_jpeg.admits(_to_jpeg()), "whatever it takes: a png here"
    # "Some image" is not a jpeg, and not excluded: possible, never routed on.
    assert wants_jpeg.grade(_some_image()) is MatchGrade.POSSIBLE
    assert not wants_jpeg.admits(_some_image()) and wants_jpeg.may_admit(_some_image())
    assert wants_jpeg.grade(_pages()) is MatchGrade.NONE

    # Asked for any image, a jpeg is guaranteed to be one, not exactly it.
    wants_image = CapQuery.producing(MediaUrn.from_string("media:image"))
    assert wants_image.grade(_to_jpeg()) is MatchGrade.GUARANTEED
    assert wants_image.grade(_some_image()) is MatchGrade.EXACT
    assert not wants_image.admits(_passes_through()), "media: out promises no image"

    # What can a pdf become? Whatever takes a pdf — or takes anything.
    has_pdf = CapQuery.consuming(MediaUrn.from_string("media:ext=pdf"))
    assert has_pdf.admits(_pages()) and has_pdf.admits(_some_image())
    assert has_pdf.admits(_passes_through()), "it takes anything, a pdf included"
    assert not has_pdf.admits(_to_jpeg()), "a png converter does not take a pdf"
    assert has_pdf.grade(_to_jpeg()) is MatchGrade.NONE

    # Both sides stated is the typed call.
    pdf_to_image = CapQuery.between(
        MediaUrn.from_string("media:ext=pdf"), MediaUrn.from_string("media:image")
    )
    assert pdf_to_image.admits(_some_image())
    assert not pdf_to_image.admits(_pages()) and not pdf_to_image.admits(_to_jpeg())


# TEST12369: the cap-tags a query asks for are matched against the tags the
# cap HAS — a cap's own list is complete.
#
# So asking that a tag be absent selects the caps that do not carry it, which
# no cap needs to declare; and a cap may carry tags nobody asked about.
def test_12369_a_querys_tags_are_asked_of_the_tags_a_cap_has():
    any_image = MediaUrn.from_string("media:image")

    converters = CapQuery.producing(any_image, {"convert-image": "*"})
    assert converters.admits(_to_jpeg())
    assert not converters.admits(_some_image()), "it renders; it is not tagged convert-image"

    not_converters = CapQuery.producing(any_image, {"convert-image": "!"})
    assert not_converters.admits(_some_image()), "it does not have the tag"
    assert not not_converters.admits(_to_jpeg()), "it has it"
    assert not_converters.grade(_to_jpeg()) is MatchGrade.NONE

    # The same holds of a request: `!x` is served by a cap silent on x.
    request = CapUrn.from_string('cap:!convert-image;out="media:image"')
    assert _some_image().is_dispatchable(request)
    assert not _to_jpeg().is_dispatchable(request)
    assert CapQuery.from_request(request).grade(_some_image()) is MatchGrade.EXACT
