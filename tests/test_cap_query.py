"""Questions about caps: a side left unknown, and the tags a cap has."""

from capdag import CapQuery, CapUrn, MatchGrade, MediaUrn
from tagged_urn import ConstraintAbsent, ConstraintPresent


def _pages() -> CapUrn:
    return CapUrn.from_string('cap:disbind;in="media:document;ext=pdf";out="media:enc=utf8;ext=txt;page;plain-text"')


def _to_jpeg() -> CapUrn:
    return CapUrn.from_string(
        'cap:convert-image;in="media:ext=png;image";out="media:ext=jpeg;image"'
    )


def _some_image() -> CapUrn:
    return CapUrn.from_string('cap:render;in="media:document;ext=pdf";out="media:ext;image"')


def _bare_image() -> CapUrn:
    return CapUrn.from_string('cap:render;in="media:document;ext=pdf";out="media:image"')


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
    # An image file of some type is not a jpeg, and not excluded: possible,
    # never routed on.
    assert wants_jpeg.grade(_some_image()) is MatchGrade.POSSIBLE
    assert not wants_jpeg.admits(_some_image()) and wants_jpeg.may_admit(_some_image())
    assert wants_jpeg.grade(_pages()) is MatchGrade.NONE
    # A declared output says what the cap gives: one giving media:image gives
    # an image with no file type, never a jpeg.
    assert wants_jpeg.grade(_bare_image()) is MatchGrade.NONE

    # Asked for any image, a jpeg is guaranteed to be one, not exactly it.
    wants_image = CapQuery.producing(MediaUrn.from_string("media:image"))
    assert wants_image.grade(_to_jpeg()) is MatchGrade.GUARANTEED
    assert wants_image.grade(_some_image()) is MatchGrade.GUARANTEED
    assert wants_image.grade(_bare_image()) is MatchGrade.EXACT
    wants_image_file = CapQuery.producing(MediaUrn.from_string("media:ext;image"))
    assert wants_image_file.grade(_some_image()) is MatchGrade.EXACT
    # A cap that gives what it is sent, asked for an image whatever it takes,
    # gives whatever it takes — not only images.
    assert not wants_image.admits(_passes_through())
    wants_pdf = CapQuery.producing(MediaUrn.from_string("media:document;ext=pdf"))
    assert not wants_pdf.admits(_passes_through())
    assert wants_pdf.grade(_passes_through()) is MatchGrade.POSSIBLE

    # What can a pdf become? Whatever takes a pdf — or takes anything.
    has_pdf = CapQuery.consuming(MediaUrn.from_string("media:document;ext=pdf"))
    assert has_pdf.admits(_pages()) and has_pdf.admits(_some_image())
    assert has_pdf.admits(_passes_through()), "it takes anything, a pdf included"
    assert not has_pdf.admits(_to_jpeg()), "a png converter does not take a pdf"
    assert has_pdf.grade(_to_jpeg()) is MatchGrade.NONE

    # Both sides stated is the typed call.
    pdf_to_image = CapQuery.between(
        MediaUrn.from_string("media:document;ext=pdf"), MediaUrn.from_string("media:image")
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

    converters = CapQuery.producing(any_image, {"convert-image": ConstraintPresent()})
    assert converters.admits(_to_jpeg())
    assert not converters.admits(_some_image()), "it renders; it is not tagged convert-image"

    not_converters = CapQuery.producing(any_image, {"convert-image": ConstraintAbsent()})
    assert not_converters.admits(_some_image()), "it does not have the tag"
    assert not not_converters.admits(_to_jpeg()), "it has it"
    assert not_converters.grade(_to_jpeg()) is MatchGrade.NONE

    # The same holds of a call: `!x` is served by a cap silent on x.
    call = CapUrn.from_string('cap:!convert-image;in="media:ext=png;image";out="media:ext;image"')
    renders_png = CapUrn.from_string('cap:render;in="media:ext=png;image";out="media:ext;image"')
    assert renders_png.is_dispatchable(call)
    assert not _to_jpeg().is_dispatchable(call), "it takes a png and gives an image file, and is tagged convert-image"
    assert CapQuery.from_call(call).grade(renders_png) is MatchGrade.EXACT
