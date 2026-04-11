"""Markdown Emphasis."""

from __future__ import annotations

import enum
import re
from typing import Self, TYPE_CHECKING

import fpdf


class MDEmphasis(enum.IntFlag):
    """Markdown Emphasis."""

    if TYPE_CHECKING:
        MARKER_PATTERN: str
        MARKERS: dict[MDEmphasis, str]
        MD_PATTERN: re.Pattern[str]

    NONE = 0
    """No emphasis."""

    BOLD = 1
    """Bold."""

    ITALICS = 2
    """Italics."""

    UNDERLINE = 4
    """Underline."""

    STRIKETHROUGH = 8
    """Strikethrough."""

    @property
    def font_style(self) -> str:
        """The corresponding :py:attr:`fpdf.FPDF.font_style`."""
        return "".join(
            str(mde.name)[0] for mde in type(self) if mde.value & self
        )

    @property
    def marker(self) -> str:
        """The marker."""
        return "".join(
            type(self).MARKERS[mde] for mde in type(self) if mde.value & self
        )

    @property
    def text_emphasis(self) -> fpdf.enums.TextEmphasis:
        """The corresponding :py:class:`fpdf.enums.TextEmphasis`."""
        return fpdf.enums.TextEmphasis.coerce(self.font_style)

    def format(self, text: str) -> str:
        """Formats a text according to this Markdown Emphasis.

        Args:
            text: The text to format.

        Returns:
            The formatted text.
        """
        prefix = "".join(mde.marker for mde in type(self) if mde.value & self)
        suffix = prefix[::-1]
        return f"{prefix:s}{text:s}{suffix:s}"

    @classmethod
    def parse(cls, text: str) -> tuple[str, Self]:
        """Parses a text and returns the "inner", unformatted text and the
        corresponding :py:class:`MDEmphasis`.

        Args:
            text: The text to parse.

        Returns:
            The "inner", unformatted text and the corresponding
            :py:class:`MDEmphasis`.

        Raises:
            ValueError: If the end emphasis does not correspond to the mirrored
                start emphasis.
        """
        label_emphasis = MDEmphasis.NONE
        match = cls.MD_PATTERN.match(text)
        if not match:
            return text, label_emphasis
        start_emph = match.group("md_start")
        end_emph = match.group("md_end")
        if start_emph != end_emph[::-1]:
            msg = f"invalid (not-mirrored) emphasis: {match.group(0)!r:s}"
            raise ValueError(msg)
        for mde in MDEmphasis:
            if mde.marker in start_emph:
                label_emphasis |= mde
        text = match.group("text")
        return text, label_emphasis

    @classmethod
    def remove(cls, text: str) -> str:
        """Removes the markdown emphasis markers from a text.

        Args:
            text: The text to remove the markers from.

        Returns:
            The "inner", unformatted text.
        """
        return cls.parse(text)[0]


# Add markers and patterns for formatting and parsing
MDEmphasis.MARKERS = {MDEmphasis.NONE: ""}
MDEmphasis.MARKERS.update(
    {s: getattr(fpdf.FPDF, f"MARKDOWN_{s.name:s}_MARKER") for s in MDEmphasis}
)
MDEmphasis.MARKER_PATTERN = (
    r"(?<!\\)(?P<{name:s}>"
    rf"(?:{'|'.join(re.escape(mde.marker) for mde in MDEmphasis):s})"
    r"{{0,4}})"
)
MDEmphasis.MD_PATTERN = re.compile(
    rf"{MDEmphasis.MARKER_PATTERN.format(name='md_start'):s}"
    rf"(?!\*|~|_|-)(?P<text>.*)(?<!\*|~|_|-)"
    rf"{MDEmphasis.MARKER_PATTERN.format(name='md_end'):s}"
)
