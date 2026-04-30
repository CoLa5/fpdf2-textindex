from collections.abc import Iterator
import itertools

import fpdf
import pytest

from fpdf2_textindex.md_emphasis import MDEmphasis


@pytest.mark.parametrize("mde", list(MDEmphasis))
def test_properties(mde: MDEmphasis) -> None:
    assert isinstance(mde.font_style, str)
    if mde.value != 0:
        assert mde.font_style in {"B", "I", "U", "S"}
    assert isinstance(mde.marker, str)
    if mde.value != 0:
        assert len(mde.marker) == 2
    assert isinstance(mde.text_emphasis, fpdf.enums.TextEmphasis)


@pytest.mark.parametrize(
    "mde",
    [
        MDEmphasis(sum(c, start=MDEmphasis.NONE))
        for i in range(1, len(MDEmphasis) + 1)
        for c in itertools.combinations(MDEmphasis, i)
    ],
)
def test_combo_properties(mde: MDEmphasis) -> None:
    assert isinstance(mde.font_style, str)
    assert all((c in {"B", "I", "U", "S"}) for c in mde.font_style), (
        mde.font_style
    )
    assert isinstance(mde.marker, str), mde.marker
    assert len(mde.marker) % 2 == 0, mde.marker
    assert len(mde.marker) // 2 > 0, mde.marker
    assert isinstance(mde.text_emphasis, fpdf.enums.TextEmphasis)


def create_examples() -> Iterator[tuple[MDEmphasis, str]]:
    yield (MDEmphasis.BOLD, "**text**")
    yield (MDEmphasis.ITALICS, "__text__")
    yield (MDEmphasis.STRIKETHROUGH, "~~text~~")
    yield (MDEmphasis.UNDERLINE, "--text--")
    yield (MDEmphasis.BOLD | MDEmphasis.ITALICS, "**__text__**")
    yield (MDEmphasis.BOLD | MDEmphasis.STRIKETHROUGH, "**~~text~~**")
    yield (MDEmphasis.BOLD | MDEmphasis.UNDERLINE, "**--text--**")
    yield (
        MDEmphasis.BOLD | MDEmphasis.ITALICS | MDEmphasis.STRIKETHROUGH,
        "**__~~text~~__**",
    )


@pytest.mark.parametrize(
    ("mde", "formatted_text"),
    list(create_examples()),
)
def test_format(mde: MDEmphasis, formatted_text: str) -> None:
    assert mde.format("text") == formatted_text


@pytest.mark.parametrize(
    ("mde", "formatted_text"),
    list(create_examples()),
)
def test_parse(mde: MDEmphasis, formatted_text: str) -> None:
    t, m = MDEmphasis.parse(formatted_text)
    assert t == "text"
    assert m == mde


@pytest.mark.parametrize(
    "formatted_text", list(t for _, t in create_examples())
)
def test_remove(formatted_text: str) -> None:
    assert MDEmphasis.remove(formatted_text) == "text"
