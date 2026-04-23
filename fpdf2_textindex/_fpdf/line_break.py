"""Line Break."""

# ruff: noqa: E501, UP045

from typing import Optional

from fpdf.enums import Align
from fpdf.enums import WrapMode
from fpdf.errors import FPDFException
import fpdf.line_break
from fpdf.line_break import BREAKING_SPACE_SYMBOLS_STR
from fpdf.line_break import FORM_FEED
from fpdf.line_break import Fragment
from fpdf.line_break import HYPHEN
from fpdf.line_break import HyphenHint
from fpdf.line_break import NBSP
from fpdf.line_break import NEWLINE
from fpdf.line_break import SOFT_HYPHEN
from fpdf.line_break import SPACE
from fpdf.line_break import SpaceHint
from fpdf.line_break import TextLine
from fpdf.util import FloatTolerance


class CurrentLine(fpdf.line_break.CurrentLine):
    def add_character(
        self,
        character: str,
        character_width: float,
        original_fragment: Fragment | HyphenHint,
        original_fragment_index: int,
        original_character_index: int,
        height: float,
        url: Optional[str | int] = None,
    ) -> None:
        assert character != NEWLINE
        self.height = height
        if not self.fragments:
            assert isinstance(original_fragment, Fragment)
            self.fragments.append(
                original_fragment.__class__(
                    characters="",
                    graphics_state=original_fragment.graphics_state,
                    k=original_fragment.k,
                    link=url,
                )
            )

        # characters are expected to be grouped into fragments by font and
        # character attributes. If the last existing fragment doesn't match
        # the properties of the pending character -> add a new fragment.
        elif isinstance(original_fragment, Fragment):
            # BUGFIX: https://github.com/py-pdf/fpdf2/issues/1814
            if isinstance(self.fragments[-1], Fragment) and not (
                original_fragment.has_same_style(self.fragments[-1])
                and url == self.fragments[-1].link
            ):
                self.fragments.append(
                    original_fragment.__class__(
                        characters="",
                        graphics_state=original_fragment.graphics_state,
                        k=original_fragment.k,
                        link=url,
                    )
                )
        active_fragment = self.fragments[-1]

        if character in BREAKING_SPACE_SYMBOLS_STR:
            self.space_break_hint = SpaceHint(
                original_fragment_index,
                original_character_index,
                len(self.fragments),
                len(active_fragment.characters),
                self.width,
                self.number_of_spaces,
            )
            self.number_of_spaces += 1
        elif character == NBSP:
            # PDF viewers ignore NBSP for word spacing with "Tw".
            character = SPACE
            self.number_of_spaces += 1
        elif character == SOFT_HYPHEN and not self.print_sh:
            self.hyphen_break_hint = HyphenHint(
                original_fragment_index,
                original_character_index,
                len(self.fragments),
                len(active_fragment.characters),
                self.width,
                self.number_of_spaces,
                HYPHEN,
                character_width,
                original_fragment.graphics_state,
                original_fragment.k,
            )

        if character != SOFT_HYPHEN or self.print_sh:
            active_fragment.characters.append(character)


class MultiLineBreak(fpdf.line_break.MultiLineBreak):
    __PATCHED__: bool = True

    # pylint: disable=too-many-return-statements
    def get_line(self) -> Optional[TextLine]:
        first_char = True  # "Tw" ignores the first character in a text object.
        idx_last_forced_break = self.idx_last_forced_break
        self.idx_last_forced_break = None

        if self.fragment_index == len(self.fragments):
            return None

        current_font_height: float = 0

        max_width = self.get_width(current_font_height)
        # The full max width will be passed on via TextLine to FPDF._render_styled_text_line().
        current_line = CurrentLine(
            max_width=max_width,
            print_sh=self.print_sh,
            indent=self.first_line_indent if self._is_first_line else 0,
        )
        # For line wrapping we need to use the reduced width.
        for margin in self.margins:
            max_width -= float(margin)
        if self._is_first_line:
            max_width -= self.first_line_indent

        if self.skip_leading_spaces:
            # write_html() with TextColumns uses this, since it can't know in
            # advance where the lines will be broken.
            while self.fragment_index < len(self.fragments):
                if self.character_index >= len(
                    self.fragments[self.fragment_index].characters
                ):
                    self.character_index = 0
                    self.fragment_index += 1
                    continue
                character = self.fragments[self.fragment_index].characters[
                    self.character_index
                ]
                if character == SPACE:
                    self.character_index += 1
                else:
                    break

        while self.fragment_index < len(self.fragments):
            current_fragment = self.fragments[self.fragment_index]

            if FloatTolerance.greater_than(
                current_fragment.font_size, current_font_height
            ):
                current_font_height = (
                    current_fragment.font_size
                )  # document units
                max_width = self.get_width(current_font_height)
                current_line.max_width = max_width
                for margin in self.margins:
                    max_width -= float(margin)
                if self._is_first_line:
                    max_width -= self.first_line_indent

            if self.character_index >= len(current_fragment.characters):
                # BUGFIX: Support of empty md links
                # Catch empty fragments with link
                if (
                    len(current_fragment.characters) == 0
                    and current_fragment.link is not None
                ):
                    current_line.add_character(
                        "",
                        0.0,
                        current_fragment,
                        self.fragment_index,
                        self.character_index,
                        current_font_height * self.line_height,
                        current_fragment.link,
                    )
                self.character_index = 0
                self.fragment_index += 1
                continue

            character = current_fragment.characters[self.character_index]
            character_width = current_fragment.get_character_width(
                character, self.print_sh, initial_cs=not first_char
            )
            first_char = False

            if character in (NEWLINE, FORM_FEED):
                self.character_index += 1
                if not current_line.fragments:
                    current_line.height = current_font_height * self.line_height
                self._is_first_line = False
                return current_line.manual_break(
                    Align.L if self.align == Align.J else self.align,
                    trailing_nl=character == NEWLINE,
                    trailing_form_feed=character == FORM_FEED,
                )
            if FloatTolerance.greater_than(
                current_line.width + character_width, max_width
            ):
                self._is_first_line = False
                if (
                    character in BREAKING_SPACE_SYMBOLS_STR
                ):  # must come first, always drop a current space.
                    self.character_index += 1
                    return current_line.manual_break(self.align)
                if self.wrapmode == WrapMode.CHAR:
                    # If the line ends with one or more spaces, then we want to get
                    # rid of them so it can be justified correctly.
                    current_line.trim_trailing_spaces()
                    return current_line.manual_break(self.align)
                if current_line.automatic_break_possible():
                    (
                        self.fragment_index,
                        self.character_index,
                        line,
                    ) = current_line.automatic_break(self.align)
                    self.character_index += 1
                    return line
                if idx_last_forced_break == self.character_index:
                    raise FPDFException(
                        "Not enough horizontal space to render a single character"
                    )
                self.idx_last_forced_break = self.character_index
                return current_line.manual_break(
                    Align.L if self.align == Align.J else self.align,
                )

            current_line.add_character(
                character,
                character_width,
                current_fragment,
                self.fragment_index,
                self.character_index,
                current_font_height * self.line_height,
                current_fragment.link,
            )

            self.character_index += 1

        if current_line.width:
            self._is_first_line = False
            return current_line.manual_break(
                Align.L if self.align == Align.J else self.align,
            )
        return None


# Monkey-patch
fpdf.fpdf.MultiLineBreak = MultiLineBreak  # type: ignore[attr-defined]
fpdf.line_break.CurrentLine = CurrentLine  # type: ignore[misc]
fpdf.line_break.MultiLineBreak = MultiLineBreak  # type: ignore[misc]
