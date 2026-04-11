"""Text Index Renderer."""

from collections import deque
from collections.abc import Iterable, Iterator
import contextlib
import dataclasses
import logging
from typing import Literal, Protocol, TYPE_CHECKING

import fpdf

from fpdf2_textindex import constants as const
from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import LinkLocation
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.md_emphasis import MDEmphasis
from fpdf2_textindex.pdf import FPDF
from fpdf2_textindex.utils import md_link


def _collect_index_links(pdf: fpdf.FPDF) -> dict[str, LinkLocation]:
    link_locs = {}
    for page_num, pdf_page in pdf.pages.items():
        if pdf_page.annots is None:
            continue

        for a in pdf_page.annots:
            link_name = str(a.dest)
            if not (
                link_name.startswith(const.INDEX_ID_PREFIX)
                or link_name.startswith(const.ENTRY_ID_PREFIX)
            ):
                continue
            assert a.rect.startswith("[") and a.rect.endswith("]"), a.rect
            x, y_h, x_w, y = map(
                lambda x: float(x) / pdf.k,
                a.rect[1:-1].split(" ", maxsplit=3),
            )
            w = x_w - x
            h = y - y_h
            y = pdf.h - y
            link_locs[link_name] = LinkLocation(
                name=link_name, page=page_num, x=x, y=y, w=w, h=h
            )
    return link_locs


class TextIndexEntryP(Protocol):
    """Text Index Protocol."""

    @property
    def depth(self) -> int:
        """The depth of the entry."""
        ...

    @property
    def label(self) -> str | None:
        """The label of the entry."""
        ...

    @property
    def sort_label(self) -> str:
        """The sort label of the entry."""
        ...


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class _AlsoPseudoEntry:
    """A pseudo entry for printing an ALSO reference as separate subentry."""

    depth: int

    @property
    def label(self) -> str | None:
        return None

    @property
    def sort_label(self) -> str:
        return ""


class TextIndexRenderer:
    """Text Index (Writer).

    A reference implementation of a Text Index to use with :py:mod:`fpdf2`.

    This class provides a customizable Text Index that can be used directly or
    subclassed for additional functionality. To use this class, create an
    instance of `TextIndex`, configure it as needed, and pass its
    ``render_index``-method as ``render_index_function``-argument to
    :py:meth:`fpdf.FPDF.insert_index_placeholder`.
    """

    if TYPE_CHECKING:
        _cur_header: str | None
        _link_locations: dict[str, LinkLocation]

    def __init__(
        self,
        *,
        border: bool = False,
        ignore_same_page_refs: bool = True,
        level_indent: float | None = 7.5,
        line_spacing: float | None = None,
        max_outline_level: int | None = None,
        outline_level: int | None = None,
        run_in_style: bool = True,
        show_header: bool = False,
        sort_emph_first: bool = False,
        text_styles: Iterable[fpdf.TextStyle] | fpdf.TextStyle | None = None,
    ) -> None:
        """Initializes the renderer.

        Args:
            border: Whether to show borders around the entries and headers.
                Mainly for debugging purposes. Defaults to ``False``.
            ignore_same_page_refs: Whether to ignore references (locators) to
                the same PDF page (default), else same pages will be printed
                multiple times.
            level_indent: The indent to add per entry depth to the left of the
                entry. Defaults to ``7.5`` times the :py:attr:`fpdf.FPDF.unit`.
            line_spacing: The spacing between lines as multiple of the font
                size. Defaults to ``None``, meaning ``1.0``.
            max_outline_level: If ``outline_level`` >= 0, ``max_outline_level``
                will decide how many deeper entries will be added to the PDF
                outline. Defaults to ``None``, meaning that no liimit is set.
            outline_level: If ``outline_level`` >= 0, the first entry depth will
                be added at this outline level to the PDF. If
                ``show_header=True``, the headers will be added at this outline
                level to the PDF. Defaults to ``None``, meaning to not show the
                entries (or headers) in the PDF outline.
            run_in_style: Whether to print the deepest entry levels at "run-in"-
                style (>2). Defaults to ``True``.
            show_header: Whether to show the headers. Defaults to ``False``.
            sort_emph_first: Whether to show emphasized references (locators)
                first. Defaults to ``False``.
            text_styles: The text styles to use to print the entries at the
                different depths. If ``show_header=True``, the first text style
                refers to the style of the headers. If an entry is "deeper" than
                there are text styles, the renderer will fall back to deepest
                given text style. Defaults to ``None``, meaning to use an empty
                text style and thus the last used one before rendering the text
                index.
        """
        self.border = border
        self.ignore_same_page_refs = bool(ignore_same_page_refs)
        self.level_indent = 0.0 if level_indent is None else float(level_indent)
        self.line_spacing = 1.0 if line_spacing is None else float(line_spacing)
        self.max_outline_level = (
            -1 if max_outline_level is None else int(max_outline_level)
        )
        self.outline_level = -1 if outline_level is None else int(outline_level)
        self.run_in_style = bool(run_in_style)
        self.show_header = bool(show_header)
        self.sort_emph_first = bool(sort_emph_first)

        if text_styles is None:
            self.text_styles = [fpdf.TextStyle()]
        elif isinstance(text_styles, Iterable):
            self.text_styles = list(text_styles)
        elif isinstance(text_styles, fpdf.TextStyle):
            self.text_styles = [text_styles]
        else:
            msg = f"invalid type of text_styles: {type(text_styles):__name__:s}"
            raise TypeError(msg)

        self._cur_header = None
        self._h_header_min = None
        self._link_locations = {}

    def render_text_index(
        self,
        pdf: FPDF,
        entries: list[TextIndexEntry],
    ) -> None:
        """Renders the text index.

        Note:
            Use this method as ``render_index_function``-argument in
            :py:meth:`fpdf.FPDF.insert_index_placeholder`.

        Args:
            pdf: The :py:class:`fpdf.FPDF`-instance to render in.
            entries: The list of entries to render.

        Raises:
            ValueError: If a textstyle has a :py:class:`fpdf.Align`-value as
                left margin.
        """
        assert pdf.index_placeholder is not None

        LOGGER.info("Rendering text index")
        if not entries:
            LOGGER.warning("No entries defined")
            return

        self._link_locations = _collect_index_links(pdf)

        max_depth = max(e.depth for e in entries)
        if max_depth > 2:
            if self.run_in_style:
                LOGGER.warning(
                    "Deep index (>2 levels): Level %d entries will be run-in "
                    "to level %d (see docs to disable)",
                    max_depth,
                    max_depth - 1,
                )
            else:
                LOGGER.warning(
                    "Deep index (>2 levels): Consider reducing depth, or "
                    "enable run-in (see docs)"
                )

        # Reset section title styles to guarantee adding to outline without add
        # section title
        prev_section_title_styles = pdf.section_title_styles
        pdf.section_title_styles = {}

        for entry in entries:
            if entry.depth > 1:
                continue

            prepared_entries: list[tuple[TextIndexEntryP, str]] = list(
                self._prepare_entry(pdf, entry, max_depth)
            )
            self._render_header(pdf, entry, prepared_entries[0][1])
            for e, text in prepared_entries:
                x_entry, y_entry = pdf.x, pdf.y
                self._render_entry(pdf, e, text)
                w_entry, h_entry = self._calc_entry_size(pdf, e.depth, text)
                if isinstance(e, TextIndexEntry):
                    self._set_links(pdf, e, x_entry, y_entry, w_entry, h_entry)

        pdf.section_title_styles = prev_section_title_styles

        LOGGER.info("Rendered text index")

    def _render_entry(
        self,
        pdf: FPDF,
        entry: TextIndexEntryP,
        entry_text: str,
    ) -> None:
        # Do not fit half an entry
        text_style = self._get_text_style(entry.depth)
        h_entry = self._calc_entry_size(pdf, entry.depth, entry_text)[1]
        pdf._perform_page_break_if_need_be(h_entry)

        # Consider level indent
        if TYPE_CHECKING:
            assert not isinstance(text_style.l_margin, fpdf.Align)
        l_margin = (
            text_style.l_margin or pdf.l_margin
        ) + self.level_indent * entry.depth
        with (
            self._add_to_outline(pdf, entry.depth, entry.label),
            pdf.use_text_style(text_style.replace(l_margin=l_margin)),
        ):
            pdf.multi_cell(
                w=0,
                h=pdf.font_size * self.line_spacing,
                text=entry_text,
                align=fpdf.Align.L,
                border=int(self.border),  # type: ignore[arg-type]
                first_line_indent=-self.level_indent,
                markdown=True,
                new_x=fpdf.XPos.LMARGIN,
                new_y=fpdf.YPos.NEXT,
            )

    def _render_header(
        self,
        pdf: FPDF,
        entry: TextIndexEntryP,
        first_entry_text: str,
    ) -> None:
        if not self.show_header or entry.depth > 1:
            return

        if entry.sort_label == "\uffff":  # Empty label and sort key
            return

        next_header = entry.sort_label[0].upper()
        if next_header == self._cur_header:
            return

        # Do not fit a single header without an entry at page bottom
        h_header_min = self._calc_min_header_height(pdf, first_entry_text)
        pdf._perform_page_break_if_need_be(h_header_min)

        with (
            self._add_to_outline(pdf, entry.depth, next_header, header=True),
            pdf.use_text_style(self._get_text_style(0)),
        ):
            h = pdf.font_size * self.line_spacing
            pdf.cell(
                h=h,
                text=next_header,
                border=int(self.border),  # type: ignore[arg-type]
                new_x=fpdf.XPos.LMARGIN,
                new_y=fpdf.YPos.NEXT,
            )

        self._cur_header = next_header

    @contextlib.contextmanager
    def _add_to_outline(
        self,
        pdf: FPDF,
        entry_depth: int,
        entry_label: str | None,
        *,
        header: bool = False,
    ) -> Iterator[None]:
        if entry_label is None or self.outline_level < 0:
            yield
            return

        level = (
            self.outline_level
            + int(self.show_header and not header)
            + entry_depth
            - 1
        )
        if self.max_outline_level > -1 and level > self.max_outline_level:
            yield
            return

        name = MDEmphasis.remove(entry_label)
        pdf.start_section(name, level=level)
        with pdf._marked_sequence(title=name) as struct_elem:
            outline_struct_elem = struct_elem
            yield
        pdf._outline[-1].struct_elem = outline_struct_elem

    def _calc_entry_size(
        self,
        pdf: FPDF,
        entry_depth: int,
        entry_text: str,
    ) -> tuple[float, float]:
        text_style = self._get_text_style(entry_depth)
        if isinstance(text_style.l_margin, (fpdf.Align | str)):
            align = fpdf.Align.coerce(text_style.l_margin)
            msg = (
                f"TextStyle with l_margin as align value {align!r} cannot be "
                f"used in {type(self).__name__:s}"
            )
            raise ValueError(msg)

        prev_x, prev_y = pdf.x, pdf.y
        # Consider level indent
        l_margin = (
            text_style.l_margin or pdf.l_margin
        ) + self.level_indent * entry_depth

        with pdf.use_text_style(
            text_style.replace(t_margin=0, l_margin=l_margin, b_margin=0)
        ):
            if TYPE_CHECKING:
                lines: list[str]
                h: float
            lines, h = pdf.multi_cell(  # type: ignore[assignment, misc]
                w=0,
                h=pdf.font_size * self.line_spacing,
                text=entry_text,
                align=fpdf.Align.L,
                dry_run=True,
                first_line_indent=-self.level_indent,
                markdown=True,
                output=fpdf.enums.MethodReturnValue.LINES
                | fpdf.enums.MethodReturnValue.HEIGHT,
                padding=fpdf.util.Padding(
                    top=text_style.t_margin or 0,
                    bottom=text_style.b_margin or 0,
                ),
            )
            w = max(
                pdf.get_string_width(
                    line,
                    normalized=True,
                    markdown=True,
                )
                for line in lines
            )
            w += 2 * pdf.c_margin

        assert pdf.x == prev_x and pdf.y == prev_y, (
            "position changed during calculation of entry height"
        )
        return w, h

    def _calc_min_header_height(
        self,
        pdf: FPDF,
        entry_text: str,
    ) -> float:
        # Header
        text_style = self.text_styles[0]
        h_min = text_style.t_margin
        h_min += (
            (text_style.size_pt or pdf.font_size_pt) * self.line_spacing / pdf.k
        )
        h_min += text_style.b_margin

        # First entry
        text_style = self.text_styles[min(1, len(self.text_styles) - 1)]
        h_min += self._calc_entry_size(pdf, 1, entry_text)[1]
        return h_min

    @staticmethod
    def _entry_at_label_path(
        entry: TextIndexEntry,
        label_path: Iterable[str],
    ) -> TextIndexEntry | None:
        # Go to root
        d = deque(entry.iter_parents(), maxlen=1)
        node: TextIndexEntry | None = (d[0] if d else entry).parent  # root
        if node is None:
            return None

        # Iterate down according to label path
        for label in label_path:
            node = node.get_child(label)
            if node is None:
                return None
        return node

    def _get_text_style(self, entry_depth: int) -> fpdf.TextStyle:
        d = min(
            int(self.show_header) + entry_depth - 1,
            len(self.text_styles) - 1,
        )
        return self.text_styles[d]

    def _prepare_entry(
        self,
        pdf: FPDF,
        entry: TextIndexEntry,
        max_depth: int,
        *,
        _run_in: bool = False,
    ) -> Iterator[tuple[TextIndexEntryP, str]]:
        running_in = entry.parent and self._run_in_children(
            entry.parent, max_depth
        )
        if running_in and not _run_in:
            return

        has_refs = len(entry.references) > 0
        has_see_refs = any(
            cr.type == CrossReferenceType.SEE for cr in entry.cross_references
        )
        assert not (has_see_refs and has_refs), (
            f"Entry {entry.joined_label_path!r} has a reference (locator) "
            f"and a SEE cross reference"
        )
        has_also_refs = any(
            cr.type == CrossReferenceType.ALSO for cr in entry.cross_references
        )

        # Label
        text_pts = [entry.label]

        # See Cross references
        if has_see_refs:
            text_pts.extend(
                self._prepare_cross_references(
                    pdf,
                    entry,
                    CrossReferenceType.SEE,
                    "running_in" if running_in or entry.depth > 1 else "entry",
                )
            )

        # References (locators)
        if has_refs:
            text_pts.extend(
                self._prepare_references(
                    pdf,
                    entry,
                    const.CATEGORY_SEPARATOR
                    if has_see_refs
                    else const.FIELD_SEPARATOR,
                )
            )

        # Run-In Style
        run_in_children = self._run_in_children(entry, max_depth)
        if run_in_children and entry.children:
            if has_refs:
                separator: str = const.LIST_SEPARATOR
            elif has_see_refs:  # and not has_refs
                separator = const.CATEGORY_SEPARATOR
            else:  # not has_see_refs
                separator = const.PATH_SEPARATOR
            text_pts.append(separator)

            for i, child in enumerate(entry.children):
                if i > 0:
                    text_pts.append(const.LIST_SEPARATOR)
                text_pts.extend(
                    t
                    for _, t in self._prepare_entry(
                        pdf, child, max_depth, _run_in=True
                    )
                )

        # Own Also Cross-References
        # Check whether we lack children and thus potentially need to inline our
        # own see-also references.
        # This provides run-in style for such references.
        if has_also_refs and (not entry.children or run_in_children):
            text_pts.extend(
                self._prepare_cross_references(
                    pdf,
                    entry,
                    CrossReferenceType.ALSO,
                    "running_in" if running_in else "entry",
                )
            )

        text = "".join(text_pts)
        LOGGER.debug(
            "%sEntry %r (Level%d): %r",
            "  " * (entry.depth - 1),
            entry.label,
            entry.depth,
            text,
        )
        yield entry, text

        if not run_in_children:
            for child in entry.children:
                yield from self._prepare_entry(
                    pdf, child, max_depth, _run_in=False
                )

        if (
            not running_in
            and entry.parent
            and any(
                cr.type == CrossReferenceType.ALSO
                for cr in entry.parent.cross_references
            )
        ):
            text = "".join(
                self._prepare_cross_references(
                    pdf,
                    entry.parent,
                    CrossReferenceType.ALSO,
                    "sub_entry",
                )
            )
            LOGGER.debug(
                "%sEntry %r (Level%d): %r",
                "  " * (entry.depth - 1),
                entry.label,
                entry.depth,
                text,
            )
            yield _AlsoPseudoEntry(depth=entry.depth), text

    def _prepare_cross_references(
        self,
        pdf: FPDF,
        entry: TextIndexEntry,
        cross_ref_type: CrossReferenceType,
        mode: Literal["entry", "running_in", "sub_entry"],
    ) -> Iterator[str]:
        # Sort by type and label path
        entry.cross_references.sort(key=lambda cr: (cr.type, *cr.label_path))

        # See (also) under
        under_mode = (
            len(entry.cross_references) == 1
            and sum(cr.type == cross_ref_type for cr in entry.cross_references)
            == 1
            and entry.label == entry.cross_references[-1].label_path[-1]
        )

        match mode:
            case "entry":
                yield const.CATEGORY_SEPARATOR
            case "running_in":
                yield " ("
            case "sub_entry":
                pass
            case _:
                msg = f"invalid mode: {mode!r}"
                raise ValueError(msg)

        cross_ref_type_str = str(cross_ref_type)
        cross_ref_type_str = (
            cross_ref_type_str.lower()
            if mode == "running_in"
            else cross_ref_type_str.capitalize()
        )
        if under_mode:
            cross_ref_type_str = f"{cross_ref_type_str:s} under"
        cross_ref_type_str = MDEmphasis.ITALICS.format(cross_ref_type_str)
        yield f"{cross_ref_type_str:s} "

        i = 0
        for cross_ref in entry.cross_references:
            if cross_ref.type != cross_ref_type:
                continue

            # Try to find cross referenced entry
            cross_ref_entry = self._entry_at_label_path(
                entry, cross_ref.label_path
            )
            if cross_ref_entry is None:
                msg = "In entry %s, cross referenced entry %s does not exist"
                log_level = (
                    logging.WARNING
                    if len(cross_ref.label_path) == 1
                    else logging.ERROR
                )
                LOGGER.log(
                    log_level,
                    msg,
                    entry.joined_label_path,
                    cross_ref.joined_label_path,
                )
                if log_level == logging.ERROR:
                    raise RuntimeError(
                        msg
                        % (entry.joined_label_path, cross_ref.joined_label_path)
                    )
            elif sum(len(e.references) for e in iter(cross_ref_entry)) == 0:
                msg = (
                    "In entry %s, cross referenced entry %s has no own "
                    "reference(s) (blind cross reference)"
                )
                LOGGER.warning(
                    msg, entry.joined_label_path, cross_ref.joined_label_path
                )
            elif len(cross_ref_entry.cross_references) > 0:
                msg = (
                    "In entry %s, cross referenced entry %s leads to other "
                    "cross reference(s) (blind cross reference)"
                )
                LOGGER.warning(
                    msg, entry.joined_label_path, cross_ref.joined_label_path
                )

            # Write delimiter
            if i > 0:
                yield f"{const.REFS_DELIMITER:s} "
            i += 1

            # Write cross reference
            cross_link = None
            if cross_ref_entry is not None:
                cross_link = f"{const.ENTRY_ID_PREFIX:s}{cross_ref_entry.id:d}"
                if cross_link not in self._link_locations:
                    # Reserve link if not existing before
                    pdf.set_link(name=cross_link)
            label_path = cross_ref.label_path
            if under_mode:
                label_path = label_path[:-1]
            content = const.PATH_SEPARATOR.join(label_path)
            if cross_link:
                content = md_link(content, f"#{cross_link}")
            yield content

        if mode == "running_in":
            yield ")"

    def _prepare_references(
        self,
        pdf: FPDF,
        entry: TextIndexEntry,
        first_separator: str,
    ) -> Iterator[str]:
        if len(entry.references) == 0:
            return

        # Respect emphasis-first option
        refs = sorted(
            entry.references,
            key=(
                (lambda r: (not r.locator_emphasis, r.start_id))
                if self.sort_emph_first
                else (lambda r: r.start_id)
            ),
        )

        # Warn about too many references
        if len(refs) >= const.REFERENCES_LIMIT:
            LOGGER.warning(
                "Entry %r has %d locators, consider reorganising or being more "
                "selective",
                entry.joined_label_path,
                len(refs),
            )

        # TODO: merge pages if consecutive references end up on same page
        self._last_page = -1
        for i, ref in enumerate(refs):
            # Render page of start id
            start_text_to_index_link = (
                f"{const.INDEX_ID_PREFIX:s}{ref.start_id:d}"
            )
            yield from self._prepare_referenced_page(
                pdf,
                entry,
                ref.locator_emphasis,
                first_separator if i == 0 else const.FIELD_SEPARATOR,
                start_text_to_index_link,
            )

            # Render page of end id
            end_text_to_index_link = None
            if ref.end_id:
                end_text_to_index_link = (
                    f"{const.INDEX_ID_PREFIX:s}{ref.end_id:d}"
                )
                yield from self._prepare_referenced_page(
                    pdf,
                    entry,
                    ref.locator_emphasis,
                    const.RANGE_SEPARATOR,
                    end_text_to_index_link,
                )

            # Render suffix of start id
            separator = ""
            if isinstance(ref.suffix, str):
                yield separator
                yield md_link(
                    ref.suffix,
                    f"#{start_text_to_index_link:s}{const.TEXT_ID_SUFFIX:s}",
                )
                separator = " "

            # Render suffix of end id
            if isinstance(ref.end_suffix, str):
                if end_text_to_index_link is None:
                    msg = (
                        f"entry's {entry.joined_label_path!r:s} "
                        f"(id={entry.id:d}) reference with start id "
                        f"{ref.start_id:d} has end suffix "
                        f"{ref.end_suffix!r:s}, but no end id"
                    )
                    raise RuntimeError(msg)
                yield separator
                yield md_link(
                    ref.end_suffix,
                    f"#{end_text_to_index_link:s}{const.TEXT_ID_SUFFIX:s}",
                )

    def _prepare_referenced_page(
        self,
        pdf: FPDF,
        entry: TextIndexEntry,
        locator_emphasis: bool,
        separator: str,
        text_to_index_link: str,
    ) -> Iterator[str]:
        if text_to_index_link not in self._link_locations:
            LOGGER.warning(
                "cannot find link location of reference with start/end id %s "
                "of entry %r to locate referenced page; reference will be "
                "skipped in index",
                text_to_index_link[len(const.INDEX_ID_PREFIX) :],
                entry.joined_label_path,
            )
            return

        # Ignore consecutive references to same page
        link_loc = self._link_locations[text_to_index_link]
        if self.ignore_same_page_refs and link_loc.page == self._last_page:
            return

        # Catch that font does not support unicode characters
        if separator == const.RANGE_SEPARATOR:
            try:
                pdf.normalize_text(separator)
            except fpdf.errors.FPDFUnicodeEncodingException:
                separator = "-"

        # Write separator
        yield separator

        # Point link of page number in index to text page
        index_to_text_link = f"{text_to_index_link:s}{const.TEXT_ID_SUFFIX:s}"
        pdf.add_link(
            name=index_to_text_link,
            page=link_loc.page,
            x=link_loc.x,
            y=link_loc.y,
        )

        # Write page number
        self._last_page = link_loc.page
        content = pdf.pages[link_loc.page].get_label()
        text = md_link(content, f"#{index_to_text_link:s}")
        yield MDEmphasis.BOLD.format(text) if locator_emphasis else text

    def _run_in_children(self, entry: TextIndexEntry, max_depth: int) -> bool:
        """Returns whether the entry should render its children in run-in style.

        Top-level entries are at level 1, and are considered children of the
        index (root) itself. Depths 1 and 2 (top-level entries and their sub-
        -entries) are always indented. Thereafter, for practical reasons, only
        the deepest level is run-in.

        Note:
            Please don't make indexes deeper than 3 levels (sub-sub-entries)
            though, for your readers' sake!
        """
        if self.run_in_style:
            return entry.depth > 1 and entry.depth == max_depth - 1
        return False

    def _set_links(
        self,
        pdf: FPDF,
        entry: TextIndexEntry,
        x_entry: float,
        y_entry: float,
        w_entry: float,
        h_entry: float,
    ) -> None:
        # Add link to entry label into link locations
        entry_link = f"{const.ENTRY_ID_PREFIX:s}{entry.id:d}"
        assert entry_link not in self._link_locations, (
            repr(entry),
            self._link_locations[entry_link],
        )
        pdf.add_link(name=entry_link, x=x_entry, y=y_entry)
        link_loc = LinkLocation(
            name=entry_link,
            page=pdf.page,
            x=x_entry,
            y=y_entry,
            w=w_entry,
            h=h_entry,
        )
        self._link_locations[entry_link] = link_loc

        # Point links on text page to index entry
        # References
        for ref in entry.references:
            text_to_index_link = f"{const.INDEX_ID_PREFIX:s}{ref.start_id:d}"
            # dest = pdf.named_destinations[text_to_index_link]
            # fpdf_link_idx = reverse_dict_items(pdf.links.items())[dest]
            fpdf_link_idx = pdf._index_links[text_to_index_link]
            pdf.set_link(
                link=fpdf_link_idx,
                name=text_to_index_link,
                page=link_loc.page,
                x=link_loc.x,
                y=link_loc.y,
            )

            if isinstance(ref.end_id, int):
                text_to_index_link = f"{const.INDEX_ID_PREFIX:s}{ref.end_id:d}"
                pdf.set_link(
                    name=text_to_index_link,
                    page=link_loc.page,
                    x=link_loc.x,
                    y=link_loc.y,
                )

        # Cross-References
        for cross_ref in entry.cross_references:
            text_to_index_link = f"{const.INDEX_ID_PREFIX:s}{cross_ref.id:d}"
            pdf.set_link(
                name=text_to_index_link,
                page=link_loc.page,
                x=link_loc.x,
                y=link_loc.y,
            )
