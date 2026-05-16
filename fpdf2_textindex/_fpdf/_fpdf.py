"""Fixes bugs in :py:class:`fpdf.FPDF`."""

# ruff: noqa: E501, E713, RUF069, SIM102, SIM108, UP007, UP045

from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
import re
import types
from typing import Literal, Optional, Union
import warnings

from fpdf.deprecation import get_stack_level
from fpdf.deprecation import support_deprecated_txt_arg
from fpdf.drawing_primitives import DeviceCMYK
from fpdf.drawing_primitives import DeviceGray
from fpdf.drawing_primitives import DeviceRGB
from fpdf.drawing_primitives import convert_to_device_color
from fpdf.enums import Align
from fpdf.enums import CharVPos
from fpdf.enums import DocumentCompliance
from fpdf.enums import MethodReturnValue
from fpdf.enums import PDFResourceType
from fpdf.enums import PageOrientation
from fpdf.enums import TextEmphasis
from fpdf.enums import TextMode
from fpdf.enums import WrapMode
from fpdf.enums import XPos
from fpdf.enums import YPos
from fpdf.errors import FPDFException
from fpdf.fonts import CoreFont
from fpdf.fonts import TTFFont
import fpdf.fpdf
from fpdf.fpdf import ToCPlaceholder
from fpdf.fpdf import check_page
from fpdf.graphics_state import StateStackType
from fpdf.line_break import Fragment
from fpdf.line_break import MultiLineBreak
from fpdf.line_break import TextLine
from fpdf.line_break import TotalPagesSubstitutionFragment
from fpdf.outline import OutlineSection
from fpdf.output import ResourceTypes
from fpdf.syntax import PDFArray
from fpdf.table import draw_box_borders
from fpdf.unicode_script import UnicodeScript
from fpdf.unicode_script import get_unicode_script
from fpdf.util import FloatTolerance
from fpdf.util import Padding


class FPDF(fpdf.fpdf.FPDF):
    __PATCHED__: bool = True
    # BUGFIX: Support of empty md links and escaped square brackets in link
    MARKDOWN_ESCAPE_CHARACTER = "\\"
    MARKDOWN_LINK_REGEX = re.compile(
        rf"^(?<!{MARKDOWN_ESCAPE_CHARACTER * 2:s})"
        rf"\[((?:{MARKDOWN_ESCAPE_CHARACTER * 2:s}[\[\]]|[^\[\]])*)\]"
        r"\(([^()]+)\)(.*)$",
        re.DOTALL,
    )
    _MARKDOWN_LINK_TEXT_UNESCAPE = re.compile(r"\\([\[\]])")

    # BUGFIX: https://github.com/py-pdf/fpdf2/issues/1807, dry-run-in-toc
    @contextmanager
    def _disable_writing(self) -> Iterator[None]:
        if not isinstance(self._out, types.MethodType):
            # This mean that self._out has already been redefined.
            # This is the case of a nested call to this method: we do nothing
            yield
            return
        self._out = lambda *args, **kwargs: None  # type: ignore[method-assign]
        prev_page, prev_pages_count, prev_x, prev_y, prev_toc_inserted_pages = (
            self.page,
            self.pages_count,
            self.x,
            self.y,
            self._toc_inserted_pages,
        )
        annots = PDFArray(self.pages[self.page].annots or [])
        self._push_local_stack()
        try:
            yield
        finally:
            self._pop_local_stack()
            # restore location:
            for p in range(prev_pages_count + 1, self.pages_count + 1):
                del self.pages[p]
            self.page = prev_page
            self.pages[self.page].annots = annots
            self.set_xy(prev_x, prev_y)
            # restore inserted pages in toc
            self._toc_inserted_pages = prev_toc_inserted_pages
            # restore writing function:
            del self._out

    # Bugfix: https://github.com/py-pdf/fpdf2/issues/1840, multi-cell-md-result
    def _join_text_lines(
        self,
        text_lines: list[TextLine],
        markdown: bool = False,
    ) -> list[str]:
        output_lines: list[str] = []
        if not markdown:
            for text_line in text_lines:
                characters: list[str] = []
                for frag in text_line.fragments:
                    characters.extend(frag.characters)
                output_lines.append("".join(characters))
        else:
            emphasis_markers: dict[TextEmphasis, str] = {
                TextEmphasis.NONE: "",
                TextEmphasis.B: self.MARKDOWN_BOLD_MARKER,
                TextEmphasis.I: self.MARKDOWN_ITALICS_MARKER,
                TextEmphasis.U: self.MARKDOWN_UNDERLINE_MARKER,
                TextEmphasis.S: self.MARKDOWN_STRIKETHROUGH_MARKER,
            }
            marker_pattern: str = "|".join(
                re.escape(m)
                for te, m in emphasis_markers.items()
                if te != TextEmphasis.NONE
            )
            escape_pattern: re.Pattern[str] = re.compile(
                rf"({marker_pattern:s})"
            )

            def escape(text: str) -> str:
                return escape_pattern.sub(
                    rf"{self.MARKDOWN_ESCAPE_CHARACTER:s}\\1", text
                )

            for text_line in text_lines:
                text_parts: list[str] = []
                last_emphasis: TextEmphasis = TextEmphasis.NONE
                for frag in text_line.fragments:
                    if markdown:
                        next_emphasis = TextEmphasis.coerce(
                            frag.font_style
                            + ("U" if frag.underline else "")
                            + ("S" if frag.strikethrough else "")
                        )
                        # If fragment has a link and link underline is true,
                        # the underline marker must not be added
                        if frag.link and self.MARKDOWN_LINK_UNDERLINE:
                            next_emphasis &= ~TextEmphasis.U
                        removed_emphasis = last_emphasis & ~next_emphasis
                        for te in reversed(TextEmphasis):
                            if removed_emphasis & te:
                                text_parts.append(emphasis_markers[te])
                        added_emphasis = next_emphasis & ~last_emphasis
                        for te in TextEmphasis:
                            if added_emphasis & te:
                                text_parts.append(emphasis_markers[te])
                        last_emphasis = next_emphasis
                    text = "".join(frag.characters)
                    # NOTE: Currently, markdown format inside of links is not handled
                    #       so only escape markdown markers outside of links
                    text_parts.append(
                        f"[{text:s}]({frag.link!s:s})"
                        if frag.link
                        else escape(text)
                    )
                next_emphasis = TextEmphasis.NONE
                removed_emphasis = last_emphasis & ~next_emphasis
                for te in reversed(TextEmphasis):
                    if removed_emphasis & te:
                        text_parts.append(emphasis_markers[te])
                output_lines.append("".join(text_parts))
        return output_lines

    def _parse_chars(self, text: str, markdown: bool) -> Iterator[Fragment]:
        if (
            not markdown
            and not self.text_shaping
            and not self._fallback_font_ids
        ):
            if self.str_alias_nb_pages:
                for seq, fragment_text in enumerate(
                    text.split(self.str_alias_nb_pages)
                ):
                    if seq > 0:
                        yield TotalPagesSubstitutionFragment(
                            self.str_alias_nb_pages,
                            self._get_current_graphics_state(),
                            self.k,
                        )
                    if fragment_text:
                        yield Fragment(
                            fragment_text,
                            self._get_current_graphics_state(),
                            self.k,
                        )
                return

            yield Fragment(text, self._get_current_graphics_state(), self.k)
            return
        txt_frag: list[str] = []
        in_bold: bool = "B" in self.font_style
        in_italics: bool = "I" in self.font_style
        in_strikethrough: bool = bool(self.strikethrough)
        in_underline: bool = bool(self.underline)
        current_fallback_font = None
        current_text_script = None

        def frag() -> Fragment:
            nonlocal txt_frag, current_fallback_font, current_text_script
            gstate = self._get_current_graphics_state()
            gstate.font_style = ("B" if in_bold else "") + (
                "I" if in_italics else ""
            )
            gstate.strikethrough = in_strikethrough
            gstate.underline = in_underline
            if current_fallback_font:
                style = "".join(c for c in current_fallback_font if c in ("BI"))
                family = current_fallback_font.replace("B", "").replace("I", "")
                gstate.font_family = family
                gstate.font_style = style
                gstate.current_font = self.fonts[current_fallback_font]
                current_fallback_font = None
                current_text_script = None
            fragment = Fragment(
                txt_frag,
                gstate,
                self.k,
            )
            txt_frag = []
            return fragment

        if self.is_ttf_font:
            font_glyphs = self.current_font.cmap  # type: ignore[union-attr]
        else:
            font_glyphs = []

        escape_next_marker = 0
        escape_run = 0

        while text:
            if markdown and text[0] == self.MARKDOWN_ESCAPE_CHARACTER:
                escape_run += 1
                text = text[1:]
                continue

            if markdown and escape_run:
                is_escape_target = text[:2] in (
                    self.MARKDOWN_BOLD_MARKER,
                    self.MARKDOWN_ITALICS_MARKER,
                    self.MARKDOWN_STRIKETHROUGH_MARKER,
                    self.MARKDOWN_UNDERLINE_MARKER,
                )
                if is_escape_target and escape_run % 2 == 1:
                    for _ in range(escape_run - 1):
                        txt_frag.append(self.MARKDOWN_ESCAPE_CHARACTER)
                    if current_fallback_font:
                        if txt_frag:
                            yield frag()
                        current_fallback_font = None
                    escape_next_marker = 2
                    escape_run = 0
                    continue
                for _ in range(escape_run):
                    txt_frag.append(self.MARKDOWN_ESCAPE_CHARACTER)
                escape_run = 0

            is_marker = text[:2] in (
                self.MARKDOWN_BOLD_MARKER,
                self.MARKDOWN_ITALICS_MARKER,
                self.MARKDOWN_STRIKETHROUGH_MARKER,
                self.MARKDOWN_UNDERLINE_MARKER,
            )
            if markdown and escape_next_marker:
                is_marker = False
            half_marker = text[0]
            text_script = get_unicode_script(text[0])
            if text_script not in (
                UnicodeScript.COMMON,
                UnicodeScript.UNKNOWN,
                current_text_script,
            ):
                if txt_frag and current_text_script:
                    yield frag()
                current_text_script = text_script

            if self.str_alias_nb_pages:
                if (
                    text[: len(self.str_alias_nb_pages)]
                    == self.str_alias_nb_pages
                ):
                    if txt_frag:
                        yield frag()
                    gstate = self._get_current_graphics_state()
                    gstate.font_style = ("B" if in_bold else "") + (
                        "I" if in_italics else ""
                    )
                    gstate.strikethrough = in_strikethrough
                    gstate.underline = in_underline
                    yield TotalPagesSubstitutionFragment(
                        self.str_alias_nb_pages,
                        gstate,
                        self.k,
                    )
                    text = text[len(self.str_alias_nb_pages) :]
                    continue

            # Check that previous & next characters are not identical to the marker:
            if markdown:
                if (
                    is_marker
                    and (not txt_frag or txt_frag[-1] != half_marker)
                    and (len(text) < 3 or text[2] != half_marker)
                ):
                    if txt_frag:
                        yield frag()
                    if text[:2] == self.MARKDOWN_BOLD_MARKER:
                        in_bold = not in_bold
                    if text[:2] == self.MARKDOWN_ITALICS_MARKER:
                        in_italics = not in_italics
                    if text[:2] == self.MARKDOWN_STRIKETHROUGH_MARKER:
                        in_strikethrough = not in_strikethrough
                    if text[:2] == self.MARKDOWN_UNDERLINE_MARKER:
                        in_underline = not in_underline
                    text = text[2:]
                    continue

                is_link = self.MARKDOWN_LINK_REGEX.match(text)
                if is_link:
                    link_text, link_dest, text = is_link.groups()
                    # BUGFIX: enable escaped square brackets in links
                    link_text = self._MARKDOWN_LINK_TEXT_UNESCAPE.sub(
                        r"\1", link_text
                    )
                    if txt_frag:
                        yield frag()
                    gstate = self._get_current_graphics_state()
                    # BUGFIX: https://github.com/py-pdf/fpdf2/issues/1826
                    gstate.font_style = ("B" if in_bold else "") + (
                        "I" if in_italics else ""
                    )
                    gstate.strikethrough = in_strikethrough
                    gstate.underline = (
                        self.MARKDOWN_LINK_UNDERLINE or in_underline
                    )
                    if self.MARKDOWN_LINK_COLOR:
                        gstate.text_color = convert_to_device_color(
                            self.MARKDOWN_LINK_COLOR
                        )
                    try:
                        page = int(link_dest)
                        link_dest = self.add_link(page=page)
                    except ValueError:
                        pass
                    yield Fragment(
                        list(link_text),
                        gstate,
                        self.k,
                        link=link_dest,
                    )
                    continue
            if (
                self.is_ttf_font
                and text[0] != "\n"
                and not ord(text[0]) in font_glyphs
            ):
                style = ("B" if in_bold else "") + ("I" if in_italics else "")
                fallback_font = self.get_fallback_font(text[0], style)
                if fallback_font:
                    if fallback_font == current_fallback_font:
                        txt_frag.append(text[0])
                        text = text[1:]
                        continue
                    if txt_frag:
                        yield frag()
                    current_fallback_font = fallback_font
                    txt_frag.append(text[0])
                    text = text[1:]
                    continue
            if current_fallback_font:
                if txt_frag:
                    yield frag()
                current_fallback_font = None
            txt_frag.append(text[0])
            text = text[1:]
            if markdown and escape_next_marker:
                escape_next_marker -= 1
                if escape_next_marker == 0:
                    yield frag()
        if markdown and escape_run:
            for _ in range(escape_run):
                txt_frag.append(self.MARKDOWN_ESCAPE_CHARACTER)
            escape_run = 0
        if txt_frag:
            yield frag()

    # BUGFIX: https://github.com/py-pdf/fpdf2/issues/1826
    def _render_styled_text_line(
        self,
        text_line: TextLine,
        h: Optional[float] = None,
        border: Union[str, int] = 0,
        new_x: XPos = XPos.RIGHT,
        new_y: YPos = YPos.TOP,
        fill: bool = False,
        link: Optional[str | int] = "",
        center: bool = False,
        padding: Optional[Padding] = None,
        prevent_font_change: bool = False,
    ) -> bool:
        if isinstance(border, int) and border not in (0, 1):
            warnings.warn(
                'Integer values for "border" parameter other than 1 are currently ignored',
                stacklevel=get_stack_level(),
            )
            border = 1
        elif isinstance(border, str) and set(border).issuperset("LTRB"):
            border = 1

        if padding is None:
            padding = Padding(0, 0, 0, 0)
        l_c_margin = r_c_margin = float(0)
        if padding.left == 0:
            l_c_margin = self.c_margin
        if padding.right == 0:
            r_c_margin = self.c_margin

        styled_txt_width = text_line.text_width
        if not styled_txt_width:
            for i, frag in enumerate(text_line.fragments):
                unscaled_width = frag.get_width(initial_cs=i != 0)
                styled_txt_width += unscaled_width

        w = text_line.max_width
        if w is None:
            if not text_line.fragments:
                raise ValueError(
                    "'text_line' must have fragments if 'text_line.text_width' is None"
                )
            w = styled_txt_width + l_c_margin + r_c_margin
        elif w == 0:
            w = self.w - self.r_margin - self.x
        if center:
            self.x = self.l_margin + (self.epw - w) / 2
        elif text_line.align == Align.X:
            self.x -= w / 2

        max_font_size: float = 0  # how much height we need to accommodate.
        # currently all font sizes within a line are vertically aligned on the baseline.
        fragments = text_line.get_ordered_fragments()
        for frag in fragments:
            if FloatTolerance.greater_than(frag.font_size, max_font_size):
                max_font_size = frag.font_size
        if h is None:
            h = max_font_size
        page_break_triggered = self._perform_page_break_if_need_be(h)
        sl: list[str] = []

        k = self.k

        # pre-calc border edges with padding

        left = (self.x - padding.left) * k
        right = (self.x + w + padding.right) * k
        top = (self.h - self.y + padding.top) * k
        bottom = (self.h - (self.y + h) - padding.bottom) * k

        if fill:
            op = "B" if border == 1 else "f"
            sl.append(
                f"{left:.2f} {top:.2f} {right - left:.2f} {bottom - top:.2f} re {op}"
            )
        elif border == 1:
            sl.append(
                f"{left:.2f} {top:.2f} {right - left:.2f} {bottom - top:.2f} re S"
            )
        # pylint: enable=invalid-unary-operand-type

        if isinstance(border, str):
            if "L" in border:
                sl.append(f"{left:.2f} {top:.2f} m {left:.2f} {bottom:.2f} l S")
            if "T" in border:
                sl.append(f"{left:.2f} {top:.2f} m {right:.2f} {top:.2f} l S")
            if "R" in border:
                sl.append(
                    f"{right:.2f} {top:.2f} m {right:.2f} {bottom:.2f} l S"
                )
            if "B" in border:
                sl.append(
                    f"{left:.2f} {bottom:.2f} m {right:.2f} {bottom:.2f} l S"
                )

        if self._record_text_quad_points:
            self._add_quad_points(self.x, self.y, w, h)

        s_start = self.x
        s_width: float = 0
        # We try to avoid modifying global settings for temporary changes.
        current_ws = frag_ws = 0.0
        current_lift = 0.0
        current_char_vpos = CharVPos.LINE
        current_font = self.current_font
        current_font_size_pt = self.font_size_pt
        current_font_style = self.font_style
        current_text_mode = self.text_mode
        current_font_stretching = self.font_stretching
        current_char_spacing = self.char_spacing
        fill_color_changed = False
        last_used_color = self.fill_color
        if fragments:
            if text_line.align == Align.R:
                dx = w - l_c_margin - styled_txt_width
            elif text_line.align in [Align.C, Align.X]:
                dx = (w - styled_txt_width) / 2
            else:
                dx = l_c_margin
            s_start += dx
            word_spacing: float = 0
            if text_line.align == Align.J and text_line.number_of_spaces:
                word_spacing = (
                    w - l_c_margin - r_c_margin - styled_txt_width
                ) / text_line.number_of_spaces
            sl.append(
                f"BT {(self.x + dx) * k:.2f} "
                f"{(self.h - self.y - 0.5 * h - 0.3 * max_font_size) * k:.2f} Td"
            )
            if (
                not prevent_font_change
                and not self.current_font_is_set_on_page
                and self.current_font is not None
                and fragments[0].font.fontkey in self._fallback_font_ids
                and self.current_font.fontkey not in self._fallback_font_ids
            ):
                # The first fragment uses a fallback font. Establish the current font for
                # the page in this text object to avoid promoting the fallback font.
                sl.append(
                    self._set_font_for_page(
                        self.current_font,
                        self.font_size_pt,
                        wrap_in_text_object=False,
                    )
                )
            underlines: list[
                tuple[
                    float,
                    float,
                    CoreFont | TTFFont,
                    float,
                    DeviceRGB | DeviceGray | DeviceCMYK | None,
                ]
            ] = []
            strikethroughs: list[
                tuple[
                    float,
                    float,
                    CoreFont | TTFFont,
                    float,
                    DeviceRGB | DeviceGray | DeviceCMYK | None,
                ]
            ] = []
            for i, frag in enumerate(fragments):
                if isinstance(frag, TotalPagesSubstitutionFragment):
                    self.pages[self.page].add_text_substitution(frag)
                if frag.text_color != last_used_color:
                    # allow to change color within the line of text.
                    last_used_color = frag.text_color
                    assert last_used_color is not None
                    sl.append(last_used_color.serialize().lower())
                    fill_color_changed = True
                if word_spacing and frag.font_stretching != 100:
                    # Space character is already stretched, extra spacing is absolute.
                    frag_ws = word_spacing * 100 / frag.font_stretching
                else:
                    frag_ws = word_spacing
                if current_font_stretching != frag.font_stretching:
                    current_font_stretching = frag.font_stretching
                    sl.append(f"{frag.font_stretching:.2f} Tz")
                if current_char_spacing != frag.char_spacing:
                    current_char_spacing = frag.char_spacing
                    sl.append(f"{frag.char_spacing:.2f} Tc")
                if not self.current_font_is_set_on_page:
                    if prevent_font_change:
                        # This is "local" to the current BT / ET context:
                        current_font = frag.font
                        current_font_size_pt = frag.font_size_pt
                        current_font_style = frag.font_style
                        sl.append(
                            f"/F{current_font.i} {current_font_size_pt:.2f} Tf"
                        )
                        self._resource_catalog.add(
                            PDFResourceType.FONT, current_font.i, self.page
                        )
                        current_char_vpos = frag.char_vpos
                    else:
                        # This is "global" to the page,
                        # as it is rendered in the content stream
                        # BEFORE the text_lines /fragments,
                        # wrapped into BT / ET operators:
                        current_font = self.current_font = frag.font
                        current_font_size_pt = self.font_size_pt = (
                            frag.font_size_pt
                        )
                        current_font_style = self.font_style = frag.font_style
                        self._out(
                            self._set_font_for_page(
                                current_font,
                                current_font_size_pt,
                            )
                        )
                        current_char_vpos = frag.char_vpos
                elif (
                    current_font != frag.font
                    or current_font_size_pt != frag.font_size_pt
                    or current_font_style != frag.font_style
                    or current_char_vpos != frag.char_vpos
                ):
                    # This is "local" to the current BT / ET context:
                    current_font = frag.font
                    current_font_size_pt = frag.font_size_pt
                    current_font_style = frag.font_style
                    sl.append(
                        self._set_font_for_page(
                            current_font,
                            current_font_size_pt,
                            wrap_in_text_object=False,
                        )
                    )
                    current_char_vpos = frag.char_vpos
                lift = frag.lift
                if lift != current_lift:
                    # Use text rise operator:
                    sl.append(f"{lift:.2f} Ts")
                    current_lift = lift
                if (
                    frag.text_mode != TextMode.FILL
                    or frag.text_mode != current_text_mode
                ):
                    current_text_mode = frag.text_mode
                    sl.append(f"{frag.text_mode} Tr {frag.line_width:.2f} w")

                r_text = frag.render_pdf_text(
                    frag_ws,
                    current_ws,
                    word_spacing,
                    self.x + dx + s_width,
                    self.y + (0.5 * h + 0.3 * max_font_size),
                    self.h,
                )
                if r_text:
                    sl.append(r_text)

                frag_width = frag.get_width(
                    initial_cs=i != 0
                ) + word_spacing * frag.characters.count(" ")
                if frag.underline:
                    underlines.append(
                        (
                            self.x + dx + s_width,
                            frag_width,
                            frag.font,
                            frag.font_size,
                            frag.text_color,
                        )
                    )
                if frag.strikethrough:
                    strikethroughs.append(
                        (
                            self.x + dx + s_width,
                            frag_width,
                            frag.font,
                            frag.font_size,
                            frag.text_color,
                        )
                    )
                if frag.link:
                    self.link(
                        x=self.x + dx + s_width,
                        y=self.y + (0.5 * h) - (0.5 * frag.font_size),
                        w=frag_width,
                        h=frag.font_size,
                        link=frag.link,
                    )
                if not frag.is_ttf_font:
                    current_ws = frag_ws
                s_width += frag_width

            sl.append("ET")

            # Underlines & strikethrough must be rendred OUTSIDE BT/ET contexts,
            # cf. https://github.com/py-pdf/fpdf2/issues/1456
            if underlines:
                for start_x, width, font, font_size, text_color in underlines:
                    # Change color of the underlines
                    if text_color != last_used_color:
                        last_used_color = text_color
                        assert last_used_color is not None
                        sl.append(last_used_color.serialize().lower())
                        fill_color_changed = True
                    sl.append(
                        self._do_underline(
                            start_x,
                            self.y + (0.5 * h) + (0.3 * font_size),
                            width,
                            font,
                        )
                    )
            if strikethroughs:
                for (
                    start_x,
                    width,
                    font,
                    font_size,
                    text_color,
                ) in strikethroughs:
                    # Change color of the strikethroughs
                    if text_color != last_used_color:
                        last_used_color = text_color
                        assert last_used_color is not None
                        sl.append(last_used_color.serialize().lower())
                        fill_color_changed = True
                    sl.append(
                        self._do_strikethrough(
                            start_x,
                            self.y + (0.5 * h) + (0.3 * font_size),
                            width,
                            font,
                        )
                    )
            if link:
                self.link(
                    self.x + dx,
                    self.y
                    + (0.5 * h)
                    - (
                        0.5 * frag.font_size  # pyright: ignore[reportPossiblyUnboundVariable]
                    ),
                    styled_txt_width,
                    frag.font_size,  # pyright: ignore[reportPossiblyUnboundVariable]
                    link,
                )

        if sl:
            # If any PDF settings have been left modified, wrap the line
            # in a local context.
            # pylint: disable=too-many-boolean-expressions
            if (
                current_ws != 0.0
                or current_lift != 0.0
                or current_char_vpos != CharVPos.LINE
                or current_font != self.current_font
                or current_font_size_pt != self.font_size_pt
                or current_font_style != self.font_style
                or current_text_mode != self.text_mode
                or fill_color_changed
                or current_font_stretching != self.font_stretching
                or current_char_spacing != self.char_spacing
            ):
                s = f"q {' '.join(sl)} Q"
            else:
                s = " ".join(sl)
            # pylint: enable=too-many-boolean-expressions
            self._out(s)
        # If the text is empty, h = max_font_size ends up as 0.
        # We still need a valid default height for self.ln() (issue #601).
        self._lasth = h or self.font_size

        # XPos.LEFT -> self.x stays the same
        if new_x == XPos.RIGHT:
            self.x += w
        elif new_x == XPos.START:
            self.x = s_start
        elif new_x == XPos.END:
            self.x = s_start + s_width
        elif new_x == XPos.WCONT:
            if s_width:
                self.x = s_start + s_width - r_c_margin
            else:
                self.x = s_start
        elif new_x == XPos.CENTER:
            self.x = s_start + s_width / 2.0
        elif new_x == XPos.LMARGIN:
            self.x = self.l_margin
        elif new_x == XPos.RMARGIN:
            self.x = self.w - self.r_margin

        # YPos.TOP:  -> self.y stays the same
        # YPos.LAST: -> self.y stays the same (single line)
        if new_y == YPos.NEXT:
            self.y += h
        if new_y == YPos.TMARGIN:
            self.y = self.t_margin
        if new_y == YPos.BMARGIN:
            self.y = self.h - self.b_margin

        return page_break_triggered

    @check_page
    @support_deprecated_txt_arg
    def multi_cell(
        self,
        w: float,
        h: Optional[float] = None,
        text: str = "",
        border: Literal[0, 1] | str = 0,
        align: str | Align = Align.J,
        fill: bool = False,
        split_only: bool = False,  # DEPRECATED
        link: Optional[int | str] = None,
        ln: Literal["DEPRECATED"] = "DEPRECATED",
        max_line_height: Optional[float] = None,
        markdown: bool = False,
        print_sh: bool = False,
        new_x: str | XPos = XPos.RIGHT,
        new_y: str | YPos = YPos.NEXT,
        wrapmode: WrapMode = WrapMode.WORD,
        dry_run: bool = False,
        output: str | MethodReturnValue = MethodReturnValue.PAGE_BREAK,
        center: bool = False,
        padding: int | Sequence[int] | Padding = 0,
    ) -> fpdf.fpdf.FPDF.MultiCellResult:
        padding = Padding.new(padding)
        wrapmode = WrapMode.coerce(wrapmode)

        if split_only:
            warnings.warn(
                (
                    'The parameter "split_only" is deprecated since v2.7.4.'
                    ' Use instead dry_run=True and output="LINES".'
                ),
                DeprecationWarning,
                stacklevel=get_stack_level(),
            )
        if dry_run or split_only:
            with self._disable_writing():
                return self.multi_cell(
                    w=w,
                    h=h,
                    text=text,
                    border=border,
                    align=align,
                    fill=fill,
                    link=link,
                    ln=ln,
                    max_line_height=max_line_height,
                    markdown=markdown,
                    print_sh=print_sh,
                    new_x=new_x,
                    new_y=new_y,
                    wrapmode=wrapmode,
                    dry_run=False,
                    split_only=False,
                    output=MethodReturnValue.LINES if split_only else output,
                    center=center,
                    padding=padding,
                )
        if not self.font_family:
            raise FPDFException(
                "No font set, you need to call set_font() beforehand"
            )
        if isinstance(w, str) or isinstance(h, str):
            raise ValueError(
                "Parameter 'w' and 'h' must be numbers, not strings."
                " You can omit them by passing string content with text="
            )
        new_x = XPos.coerce(new_x)
        new_y = YPos.coerce(new_y)
        if ln != "DEPRECATED":
            # For backwards compatibility, if "ln" is used we overwrite "new_[xy]".
            if ln == 0:
                new_x = XPos.RIGHT
                new_y = YPos.NEXT
            elif ln == 1:
                new_x = XPos.LMARGIN
                new_y = YPos.NEXT
            elif ln == 2:
                new_x = XPos.LEFT
                new_y = YPos.NEXT
            elif ln == 3:
                new_x = XPos.RIGHT
                new_y = YPos.TOP
            else:
                raise ValueError(
                    f'Invalid value for parameter "ln" ({ln}),'
                    " must be an int between 0 and 3."
                )
            warnings.warn(
                (
                    'The parameter "ln" is deprecated since v2.5.2.'
                    f" Instead of ln={ln} use new_x=XPos.{new_x.name}, new_y=YPos.{new_y.name}."
                ),
                DeprecationWarning,
                stacklevel=get_stack_level(),
            )
        align = Align.coerce(align)

        page_break_triggered = False

        if h is None:
            h = self.font_size

        # If width is 0, set width to available width between margins
        if w == 0:
            w = self.w - self.r_margin - self.x

        # Store the starting position before applying padding
        prev_x, prev_y = self.x, self.y

        # Apply padding to contents
        # decrease maximum allowed width by padding
        # shift the starting point by padding
        maximum_allowed_width = w = w - padding.right - padding.left
        clearance_margins: list[float] = []
        # If we don't have padding on either side, we need a clearance margin.
        if not padding.left:
            clearance_margins.append(self.c_margin)
        if not padding.right:
            clearance_margins.append(self.c_margin)
        if align != Align.X:
            self.x += padding.left
        self.y += padding.top

        # Center overrides padding
        if center:
            self.x = (
                self.w / 2
                if align == Align.X
                else self.l_margin + (self.epw - w) / 2
            )
            prev_x = self.x

        # Calculate text length
        text = self.normalize_text(text)
        normalized_string = text.replace("\r", "")
        styled_text_fragments = (
            self._preload_bidirectional_text(normalized_string, markdown)
            if self.text_shaping
            else self._preload_font_styles(normalized_string, markdown)
        )

        prev_current_font = self.current_font
        prev_font_style = self.font_style
        prev_underline = self.underline
        total_height: float = 0

        text_lines: list[TextLine] = []
        multi_line_break = MultiLineBreak(
            styled_text_fragments,
            maximum_allowed_width,
            clearance_margins,
            align=align,
            print_sh=print_sh,
            wrapmode=wrapmode,
        )
        text_line = multi_line_break.get_line()
        while (text_line) is not None:
            text_lines.append(text_line)
            text_line = multi_line_break.get_line()

        if (
            not text_lines
        ):  # ensure we display at least one cell - cf. issue #349
            text_lines = [
                TextLine(
                    [],
                    text_width=0,
                    number_of_spaces=0,
                    align=align,
                    height=h,
                    max_width=w,
                    trailing_nl=False,
                )
            ]

        if max_line_height is None or len(text_lines) == 1:
            line_height = h
        else:
            line_height = min(h, max_line_height)

        box_required = fill or border
        page_break_triggered = False

        for text_line_index, text_line in enumerate(text_lines):
            start_of_new_page = self._perform_page_break_if_need_be(
                h + padding.bottom
            )
            if start_of_new_page:
                page_break_triggered = True
                self.y += padding.top

            if box_required and (text_line_index == 0 or start_of_new_page):
                # estimate how many cells can fit on this page
                top_gap = self.y  # Top padding has already been added
                bottom_gap = padding.bottom + self.b_margin
                lines_before_break = int(
                    (self.h - top_gap - bottom_gap) // line_height
                )
                # check how many cells should be rendered
                num_lines = min(
                    lines_before_break, len(text_lines) - text_line_index
                )
                box_height = max(
                    h - text_line_index * line_height, num_lines * line_height
                )
                # render the box
                x = self.x - (w / 2 if align == Align.X else 0)
                draw_box_borders(
                    self,
                    x - padding.left,
                    self.y - padding.top,
                    x + w + padding.right,
                    self.y + box_height + padding.bottom,
                    border,
                    self.fill_color if fill else None,
                )
            is_last_line = text_line_index == len(text_lines) - 1
            self._render_styled_text_line(
                text_line,
                h=line_height,
                new_x=new_x if is_last_line else XPos.LEFT,
                new_y=new_y if is_last_line else YPos.NEXT,
                border=0,  # already rendered
                fill=False,  # already rendered
                link=link,
                padding=Padding(0, padding.right, 0, padding.left),
                prevent_font_change=markdown,
            )
            total_height += line_height
            if not is_last_line and align == Align.X:
                # prevent cumulative shift to the left
                self.x = prev_x

        if total_height < h:
            # Move to the bottom of the multi_cell
            if new_y == YPos.NEXT:
                self.y += h - total_height
            total_height = h

        if page_break_triggered and new_y == YPos.TOP:
            # When a page jump is performed and the requested y is TOP,
            # pretend we started at the top of the text block on the new page.
            # cf. test_multi_cell_table_with_automatic_page_break
            prev_y = self.y

        last_line = text_lines[-1]
        if (
            last_line
            and last_line.trailing_nl
            and new_y in (YPos.LAST, YPos.NEXT)
        ):
            # The line renderer can't handle trailing newlines in the text.
            self.ln()

        if new_y == YPos.TOP:  # We may have jumped a few lines -> reset
            self.y = prev_y
        elif new_y == YPos.NEXT:  # move down by bottom padding
            self.y += padding.bottom

        if markdown:
            self.font_style = prev_font_style
            self.current_font = prev_current_font
            self.underline = prev_underline

        if (
            new_x == XPos.RIGHT
        ):  # move right by right padding to align outer RHS edge
            self.x += padding.right
        elif (
            new_x == XPos.LEFT
        ):  # move left by left padding to align outer LHS edge
            self.x -= padding.left

        output = MethodReturnValue.coerce(output)
        return_value = ()
        if output & MethodReturnValue.PAGE_BREAK:
            return_value += (page_break_triggered,)  # type: ignore[assignment]
        if output & MethodReturnValue.LINES:
            # Bugfix: https://github.com/py-pdf/fpdf2/issues/1840, multi-cell-md-result
            output_lines = self._join_text_lines(text_lines, markdown=markdown)
            return_value += (output_lines,)  # type: ignore[assignment]
        if output & MethodReturnValue.HEIGHT:
            return_value += (total_height + padding.top + padding.bottom,)  # type: ignore[assignment]
        if len(return_value) == 1:
            return return_value[0]
        return return_value  # type: ignore[return-value]


# Monkey-patch
fpdf.fpdf.FPDF = FPDF  # type: ignore[misc]
fpdf.FPDF = FPDF  # type: ignore[misc]
