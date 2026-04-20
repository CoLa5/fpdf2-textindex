"""FPDF-Support for Text Index."""

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
import os
import pathlib
from typing import BinaryIO, Literal, NamedTuple, TYPE_CHECKING, overload
import warnings

import fpdf
from fpdf.enums import Align
from fpdf.enums import DocumentCompliance
from fpdf.enums import MethodReturnValue
from fpdf.enums import OutputIntentSubType
from fpdf.enums import PDFResourceType
from fpdf.enums import PageOrientation
from fpdf.enums import WrapMode
from fpdf.enums import XPos
from fpdf.enums import YPos
from fpdf.fonts import TTFFont
from fpdf.line_break import Fragment
from fpdf.line_break import MultiLineBreak
from fpdf.line_break import TextLine
from fpdf.linearization import LinearizedOutputProducer
from fpdf.output import OutputProducer
from fpdf.output import PDFICCProfile
from fpdf.output import ResourceTypes
from fpdf.table import draw_box_borders
from fpdf.unicode_script import get_unicode_script
from fpdf.util import Padding
from fpdf.util import builtin_srgb2014_bytes

from fpdf2_textindex import constants as const
from fpdf2_textindex.concordance import ConcordanceList
from fpdf2_textindex.interface import LinkLocation
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.parser import TextIndexParser


class IndexPlaceholder(NamedTuple):
    """Index Placeholder."""

    render_function: Callable[["FPDF", list["TextIndexEntry"]], None]
    start_page: int
    y: float
    page_orientation: str | PageOrientation
    pages: int = 1
    reset_page_indices: bool = True


class FPDF(fpdf.FPDF):  # noqa: D101
    if TYPE_CHECKING:
        _index_allow_page_insertion: bool
        _index_links: dict[str, int]
        _index_parser: TextIndexParser
        index_placeholder: IndexPlaceholder | None

    CONCORDANCE_FILE: os.PathLike[str] | str | None = None
    """The path to a concordance file."""

    STRICT_INDEX_MODE: bool = True
    """If ``True`` and an entry has a normal reference (locator) and a SEE-cross
    reference, a ``ValueError`` will be raised. Else, it will just be a warning.
    Defaults to ``True``.
    """

    def __init__(
        self,
        orientation: PageOrientation | str = PageOrientation.PORTRAIT,
        unit: str | float = "mm",
        format: str | tuple[float, float] = "A4",
        font_cache_dir: Literal["DEPRECATED"] = "DEPRECATED",
        *,
        enforce_compliance: DocumentCompliance | str | None = None,
    ) -> None:
        super().__init__(
            orientation=orientation,
            unit=unit,
            format=format,
            font_cache_dir=font_cache_dir,
            enforce_compliance=enforce_compliance,
        )
        self._concordance_list = None
        if self.CONCORDANCE_FILE is not None:
            self._concordance_list = ConcordanceList.from_file(
                self.CONCORDANCE_FILE
            )
        self._index_allow_page_insertion = False
        self._index_links = {}
        self._index_parser = TextIndexParser(strict=self.STRICT_INDEX_MODE)
        self.index_placeholder = None

    def _set_index_link_locations(self) -> None:
        link_locations = {}

        # Collect index locations
        for page_num, pdf_page in self.pages.items():
            if pdf_page.annots is None:
                continue

            h_page = pdf_page.dimensions()[1] / self.k
            for a in pdf_page.annots:
                link_name = str(a.dest)
                if not (
                    link_name.startswith(const.INDEX_ID_PREFIX)
                    or link_name.startswith(const.ENTRY_ID_PREFIX)
                ):
                    continue
                assert a.rect.startswith("[") and a.rect.endswith("]"), a.rect
                x, y_h, x_w, y = map(
                    lambda x: float(x) / self.k,
                    a.rect[1:-1].split(" ", maxsplit=3),
                )
                w = x_w - x
                h = y - y_h
                y = h_page - y
                link_locations[link_name] = LinkLocation(
                    page=page_num, x=x, y=y, w=w, h=h
                )

        # Add link locations to entries
        for entry in self._index_parser.entries:
            for ref in entry.references:
                ref.start_location = link_locations[ref.start_link]
                if ref.end_link:
                    ref.end_location = link_locations[ref.end_link]
            for cross_ref in entry.cross_references:
                cross_ref.location = link_locations[cross_ref.link]

    def _insert_index(self) -> None:
        # NOTE: Text Index reuses functionality of ToC

        # Collect links locations and add them to entries
        self._set_index_link_locations()

        # Doc has been closed but we want to write to self.pages[self.page]
        # instead of self.buffer:
        indexp = self.index_placeholder
        assert indexp is not None
        prev_page, prev_y = self.page, self.y
        prev_toc_placeholder = self.toc_placeholder
        prev_toc_allow_page_insertion = self._toc_allow_page_insertion

        self.page, self.y = indexp.start_page, indexp.y
        self.toc_placeholder = fpdf.fpdf.ToCPlaceholder(
            lambda pdf, outlines: None,
            indexp.start_page,
            indexp.y,
            indexp.page_orientation,
            pages=indexp.pages,
            reset_page_indices=indexp.reset_page_indices,
        )
        self._toc_allow_page_insertion = self._index_allow_page_insertion
        # flag rendering ToC for page breaking function
        self.in_toc_rendering = True
        # Reset toc inserted counter to 0
        self._toc_inserted_pages = 0
        self._set_orientation(indexp.page_orientation, self.dw_pt, self.dh_pt)
        indexp.render_function(self, self._index_parser.entries)
        self.in_toc_rendering = False  # set ToC rendering flag off
        expected_final_page = indexp.start_page + indexp.pages - 1
        if (
            self.page != expected_final_page
            and not self._index_allow_page_insertion
        ):
            too = "many" if self.page > expected_final_page else "few"
            error_msg = (
                f"The rendering function passed to "
                f"'FPDF.insert_index_placeholder' triggered too {too:s} page "
                f"breaks: ToC ended on page {self.page:d} while it was "
                f"expected to span exactly {indexp.pages:d} pages"
            )
            raise fpdf.errors.FPDFException(error_msg)
        if self._toc_inserted_pages:
            # Generating final page footer after more pages were inserted:
            self._render_footer()
            # We need to reorder the pages, because some new pages have been
            # inserted in the Index, but they have been inserted at the end of
            # self.pages:
            new_pages = [
                self.pages.pop(len(self.pages))
                for _ in range(self._toc_inserted_pages)
            ]
            new_pages = list(reversed(new_pages))
            indices_remap: dict[int, int] = {}
            for page_index in range(
                indexp.start_page + 1, self.pages_count + len(new_pages) + 1
            ):
                if page_index in self.pages:
                    new_pages.append(self.pages.pop(page_index))
                page = self.pages[page_index] = new_pages.pop(0)
                # Fix page indices:
                indices_remap[page.index()] = page_index
                page.set_index(page_index)
                # Fix page labels:
                if indexp.reset_page_indices is False:
                    page.get_page_label().st = page_index  # type: ignore[union-attr]
            assert len(new_pages) == 0, f"#new_pages: {len(new_pages)}"
            # Fix links:
            for dest in self.links.values():
                assert dest.page_number is not None
                new_index = indices_remap.get(dest.page_number)
                if new_index is not None:
                    dest.page_number = new_index
            # Fix outline:
            for section in self._outline:
                new_index = indices_remap.get(section.page_number)
                if new_index is not None:
                    section.dest = section.dest.replace(page=new_index)
                    section.page_number = new_index
                    if section.struct_elem:
                        # pylint: disable=protected-access
                        section.struct_elem._page_number = (  # pyright: ignore[reportPrivateUsage]
                            new_index
                        )
            # Fix resource catalog:
            resources_per_page = self._resource_catalog.resources_per_page
            new_resources_per_page: dict[
                tuple[int, PDFResourceType], set[ResourceTypes]
            ] = defaultdict(set)
            for (
                page_number,
                resource_type,
            ), resource in resources_per_page.items():
                key = (
                    indices_remap.get(page_number, page_number),
                    resource_type,
                )
                new_resources_per_page[key] = resource
            self._resource_catalog.resources_per_page = new_resources_per_page

        self._toc_allow_page_insertion = prev_toc_allow_page_insertion
        self._toc_inserted_pages = 0
        self.toc_placeholder = prev_toc_placeholder
        self.page, self.y = prev_page, prev_y

    def _preload_font_styles(
        self,
        text: str | None,
        markdown: bool,
    ) -> Sequence[Fragment]:
        """Preloads the font styles by markdown parsing.

        When Markdown styling is enabled, we require secondary fonts to
        render text in bold & italics. This function ensure that those fonts are
        available. It needs to perform Markdown parsing, so we return the
        resulting `styled_txt_frags` tuple to avoid repeating this processing
        later on.

        Args:
            text: The text to parse the markdown of.
            markdown: Whether markdown is enabled.

        Returns:
            The preloaded text fragments.
        """
        if not self.in_toc_rendering and text and markdown:
            # Load concordance list if not done in init
            if (
                self.CONCORDANCE_FILE is not None
                and self._concordance_list is None
            ):
                self._concordance_list = ConcordanceList.from_file(
                    self.CONCORDANCE_FILE
                )
            # Replace concordance entries by entry annotations
            if self._concordance_list:
                text = self._concordance_list.parse_text(text)
            # Replace entry annotations by markdown link
            first_id = self._index_parser.last_directive_id + 1
            text = self._index_parser.parse_text(text)
            last_id = self._index_parser.last_directive_id + 1
            # Reserve the links (named destinations)
            for text_to_index_id in range(first_id, last_id):
                link_name = f"{const.INDEX_ID_PREFIX:s}{text_to_index_id:d}"
                link_idx = self.add_link(name=link_name)
                self._index_links[link_name] = link_idx
        return super()._preload_font_styles(text, markdown)

    @property
    def index_entries(self) -> list[TextIndexEntry]:
        """Returns the parsed index entries."""
        return self._index_parser.entries

    def add_index_entry(
        self,
        label_path: Iterable[str],
        sort_key: str | None = None,
    ) -> TextIndexEntry:
        """Adds manually a text index entry.

        Note: References (locators) to pages cannot be added manually, only
            cross references.

        Args:
            label_path: The label path of the entry.
            sort_key: The sort key of the entry. Defaults to ``None``.

        Returns:
            The text index entry.
        """
        entry = self._index_parser.entry_at_label_path(label_path, create=True)
        assert isinstance(entry, TextIndexEntry)
        entry.sort_key = sort_key
        return entry

    @fpdf.fpdf.check_page
    def insert_index_placeholder(
        self,
        render_index_function: Callable[["FPDF", list[TextIndexEntry]], None],
        *,
        pages: int = 1,
        allow_extra_pages: bool = False,
        reset_page_indices: bool = True,
    ) -> None:
        """Configures Text Index rendering at the end of the document
        generation, and reserves some vertical space right now in order to
        insert it. At least one page break is triggered by this method.

        Args:
            render_index_function: A function that will be invoked to  render
                the Index. This function will receive 2 parameters:
                - `pdf`, an instance of FPDF,
                - `entries`, a list of `TextIndexEntry`.
            pages: the number of pages that the Index will span, including the
                current one. As many page breaks as the value of this argument
                will occur immediately after calling this method. Defaults to
                ``1``.
            allow_extra_pages: If set to ``True``, allows for an unlimited
                number of extra pages in the Text Index, which may cause
                discrepancies with pre-rendered page numbers.
                For consistent numbering, using page labels to create a separate
                numbering style for the Index is recommended. Defaults to
                ``False``.
            reset_page_indices : Whether to reset the pages indices after the
                Text Index. Defaults to ``True``.

        Raises:
            FPDFException: If an index placeholder has been inserted before.
            TypeError: If ``render_index_function`` is not callable.
            ValueError: If ``pages`` is less than ``1``.
        """
        if not callable(render_index_function):
            msg = (
                f"The first argument must be a callable, got: "
                f"{type(render_index_function)!s:s}"
            )
            raise TypeError(msg)
        if pages < 1:
            msg = (
                f"'pages' parameter must be equal or greater than 1: {pages:d}"
            )
            raise ValueError(msg)
        if self.index_placeholder:
            msg = (
                "A placeholder for the index has already been defined on page "
                f"{self.index_placeholder.start_page}"
            )
            raise fpdf.errors.FPDFException(msg)
        self.index_placeholder = IndexPlaceholder(
            render_index_function,
            self.page,
            self.y,
            self.cur_orientation,
            pages,
            reset_page_indices,
        )
        self._index_allow_page_insertion = allow_extra_pages
        for _ in range(pages):
            self._perform_page_break()

    @fpdf.fpdf.check_page
    @fpdf.deprecation.support_deprecated_txt_arg
    def multi_cell(
        self,
        w: float,
        h: float | None = None,
        text: str = "",
        border: Literal[0, 1] | str = 0,
        align: Align | str = Align.J,
        fill: bool = False,
        split_only: bool = False,  # DEPRECATED
        link: int | str | None = None,
        ln: Literal["DEPRECATED"] = "DEPRECATED",
        max_line_height: float | None = None,
        markdown: bool = False,
        print_sh: bool = False,
        new_x: XPos | str = XPos.RIGHT,
        new_y: YPos | str = YPos.NEXT,
        wrapmode: WrapMode = WrapMode.WORD,
        dry_run: bool = False,
        output: MethodReturnValue | str = MethodReturnValue.PAGE_BREAK,
        center: bool = False,
        padding: Padding | Sequence[int] | int = 0,
        first_line_indent: float = 0,
    ) -> fpdf.FPDF.MultiCellResult:
        r"""This method allows printing text with line breaks.

        They can be automatic (breaking at the most recent space or soft-hyphen
        character) as soon as the text reaches the right border of the cell, or
        explicit (via the ``"\\n"`` character). As many cells as necessary are
        stacked, one below the other. Text can be aligned, centered or
        justified. The cell block can be framed and the background painted. A
        cell has an horizontal padding, on the left & right sides, defined by
        the :py:attr:`FPDF.c_margin`-property.

        Note:
            Using
            ``new_x=XPos.RIGHT, new_y=XPos.TOP, maximum height=pdf.font_size``
            is useful to build tables with multiline text in cells.

        Args:
            w: Cell width. If ``0``, they extend up to the right margin of the
                page.
            h: Height of a single line of text. Defaults to ``None``, meaning to
                use the current font size.
            text: Text to print.
            border: Indicates if borders must be drawn around the cell.
                The value can be either a number (``0``: no border; ``1``:
                frame) or a string containing some or all of the following
                characters (in any order):
                - ``"L"``: left,
                - ``"T"``: top,
                - ``"R"``: right,
                - ``"B"``: bottom.
                Defaults to ``0``.
            align: Sets the text alignment inside the cell.
                Possible values are:
                - ``"J"``: justify (default value),
                - ``"L"`` / ``""``: left align,
                - ``"C"``: center,
                - ``"X"``: center around current x position, or
                - ``"R"``: right align-
            fill: Indicates if the cell background must be painted (``True``)
                or transparent (``False``). Defaults to ``False``.
            split_only: **DEPRECATED since 2.7.4**: Use ``dry_run=True`` and
                ``output=("LINES",)`` instead.
            link: Optional link to add on the cell, internal (identifier
                returned by :py:meth:`FPDF.add_link`) or external URL.
            new_x: New current position in x after the call. Defaults to
                :py:attr:`fpdf.XPos.RIGHT`.
            new_y: New current position in y after the call. Defaults to
                :py:attr:`fpdf.YPos.NEXT`.
            ln: **DEPRECATED since 2.5.1**: Use ``new_x`` and ``new_y`` instead.
            max_line_height: Optional maximum height of each sub-cell generated.
                Defaults to ``None``.
            markdown: Enables minimal markdown-like markup to render part
                of text as bold / italics / strikethrough / underlined.
                Supports ``"\\"`` as escape character. Defaults to ``False``.
            print_sh: Treat a soft-hyphen (``"\\u00ad"``) as a normal printable
                character, instead of a line breaking opportunity. Defaults to
                ``False``.
            wrapmode: :py:attr:`fpdf.enums.WrapMode.WORD` for word based line
                wrapping (default) or :py:attr:`fpdf.enums.WrapMode.CHAR` for
                character based line wrapping.
            dry_run: If ``True``, does not output anything in the document.
                Can be useful when combined with ``output``. Defaults to
                ``False``.
            output: Defines what this method returns. If several enum values are
                joined, the result will be a tuple.
            txt: [**DEPRECATED since v2.7.6**] string to print.
            center: Center the cell horizontally on the page. Defaults to
                ``False``.
            padding: Padding to apply around the text. Defaults to ``0``.
                When one value is specified, it applies the same padding to all
                four sides.
                When two values are specified, the first padding applies to the
                top and bottom, the second to the left and right.
                When three values are specified, the first padding applies to
                the top, the second to the right and left, the third to the
                bottom.
                When four values are specified, the paddings apply to the top,
                right, bottom, and left in that order (clockwise)
                If padding for left or right ends up being non-zero then the
                respective :py:attr:`FPDF.c_margin` is ignored.
                Center overrides values for horizontal padding
            first_line_indent: The indent of the first line. Defaults to ``0``.

        Returns:
            A single value or a tuple, depending on the ``output`` parameter
            value.

        Raises:
            FPDFException: If no font has been set before.
            ValueError: If ``w`` or ``h`` is a string.
        """  # noqa: DOC102
        padding = Padding.new(padding)
        wrapmode = WrapMode.coerce(wrapmode)

        if split_only:
            warnings.warn(
                (
                    'The parameter "split_only" is deprecated since v2.7.4.'
                    ' Use instead dry_run=True and output="LINES".'
                ),
                DeprecationWarning,
                stacklevel=fpdf.deprecation.get_stack_level(),
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
                    # CHANGE
                    first_line_indent=first_line_indent,
                )
        if not self.font_family:
            raise fpdf.errors.FPDFException(
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
            # For backwards compatibility, if "ln" is used we overwrite
            # "new_[xy]".
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
                    f'The parameter "ln" is deprecated since v2.5.2.'
                    f" Instead of ln={ln} use new_x=XPos.{new_x.name}, "
                    f"new_y=YPos.{new_y.name}."
                ),
                DeprecationWarning,
                stacklevel=fpdf.errors.get_stack_level(),
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
            # CHANGE
            first_line_indent=first_line_indent,
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
            # CHANGE
            if text_line_index == 0:
                self.x += first_line_indent
            # END CHANGE

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
                    # CHANGE
                    x + w + padding.right + max(0, -first_line_indent),
                    # END CHANGE
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
            # CHANGE
            if text_line_index == 0:
                self.x -= first_line_indent
            # END CHANGE

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
            output_lines: list[str] = []
            for text_line in text_lines:
                characters: list[str] = []
                for frag in text_line.fragments:
                    characters.extend(frag.characters)
                output_lines.append("".join(characters))
            return_value += (output_lines,)  # type: ignore[assignment]
        if output & MethodReturnValue.HEIGHT:
            return_value += (total_height + padding.top + padding.bottom,)  # type: ignore[assignment]
        if len(return_value) == 1:
            return return_value[0]
        return return_value  # type: ignore[return-value]

    @overload
    def output(  # type: ignore[overload-overlap]
        self,
        name: Literal[""] | None = "",
        *,
        linearize: bool = False,
        output_producer_class: type[OutputProducer] = OutputProducer,
    ) -> bytearray: ...

    @overload
    def output(
        self,
        name: os.PathLike[str] | str | BinaryIO,
        *,
        linearize: bool = False,
        output_producer_class: type[OutputProducer] = OutputProducer,
    ) -> None: ...

    def output(  # noqa: D417
        self,
        name: os.PathLike[str] | BinaryIO | str | Literal[""] | None = "",
        *,
        linearize: bool = False,
        output_producer_class: type[OutputProducer] = OutputProducer,
    ) -> bytearray | None:
        """Output PDF to some destination.

        The method first calls [close](close.md) if necessary to terminate the
        document. After calling this method, content cannot be added to the
        document anymore.

        By default the bytearray buffer is returned.
        If a `name` is given, the PDF is written to a new file.

        Args:
            name (str): optional File object or file path where to save the PDF
                under.
            output_producer_class (class): use a custom class for PDF file
                generation.

        Returns:
            If a `name` is given, the PDF will be written to a new file and
            ``None`` will be returned. Else, a bytearray buffer is returned,
            compirsing the PDF.

        Raises:
            PDFAComplianceError: If the compliance requires at least one
                embedded file.
        """
        # Clear cache of cached functions to free up memory after output
        get_unicode_script.cache_clear()
        # Finish document if necessary:
        if not self.buffer:
            if self.page == 0:
                self.add_page()
            # Generating final page footer:
            self._render_footer()
            # Generating .buffer based on .pages:
            if self.toc_placeholder:
                self._insert_table_of_contents()
            # CHANGE
            if self.index_placeholder:
                self._insert_index()
            # CHANGE
            if self.str_alias_nb_pages:
                for page in self.pages.values():
                    for substitution_item in page.get_text_substitutions():
                        page.contents = page.contents.replace(  # type: ignore[union-attr]
                            substitution_item.get_placeholder_string().encode(
                                "latin-1"
                            ),
                            substitution_item.render_text_substitution(
                                str(self.pages_count)
                            ).encode("latin-1"),
                        )
            for _, font in self.fonts.items():
                if isinstance(font, TTFFont) and font.color_font:
                    font.color_font.load_glyphs()
            if self._compliance and self._compliance.profile == "PDFA":
                if len(self._output_intents) == 0:
                    self.add_output_intent(
                        OutputIntentSubType.PDFA,
                        output_condition_identifier="sRGB",
                        output_condition="IEC 61966-2-1:1999",
                        registry_name="http://www.color.org",
                        dest_output_profile=PDFICCProfile(
                            contents=builtin_srgb2014_bytes(),
                            n=3,
                            alternate="DeviceRGB",
                        ),
                        info="sRGB2014 (v2)",
                    )
                if (
                    self._compliance.part == 4
                    and self._compliance.conformance == "F"
                    and len(self.embedded_files) == 0
                ):
                    msg = (
                        f"{self._compliance.label} requires at least one "
                        "embedded file"
                    )
                    raise fpdf.errors.PDFAComplianceError(msg)
            if linearize:
                output_producer_class = LinearizedOutputProducer
            output_producer = output_producer_class(self)
            self.buffer = output_producer.bufferize()
        if name:
            if isinstance(name, (str, os.PathLike)):
                pathlib.Path(name).write_bytes(self.buffer)
            else:
                name.write(self.buffer)
            return None
        return self.buffer
