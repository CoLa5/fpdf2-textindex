"""Concordance List."""

from collections.abc import Iterable, Sequence
import os
import pathlib
import re
from typing import Final, Self, TextIO, overload

from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.md_emphasis import MDEmphasis
from fpdf2_textindex.utils import insert_at_match


class ConcordanceList(Sequence[tuple[str, str]]):
    """Concordance List."""

    _LEADING_BRACKET_SPAN: Final[str] = (
        r"(?<!\\)\[(?P<leading_bracket_span>[^\]<>]+)(?<!\\)\]"
    )
    _LEADING_NON_WHITESPACE_SPAN: Final[str] = (
        r"(?P<leading_non_whitespace_span>[^\s\[\]\{\}<>]+?)"
        rf"{MDEmphasis.MARKER_PATTERN.format(name='md_center'):s}"
    )
    _PARAMS: Final[str] = r"\{\^(?P<params>[^\}<\n]*)\}"
    _DIRECTIVE_PATTERN: re.Pattern[str] = re.compile(
        rf"{MDEmphasis.MARKER_PATTERN.format(name='md_start'):s}"
        rf"(?:{_LEADING_NON_WHITESPACE_SPAN:s}|{_LEADING_BRACKET_SPAN:s})?"
        rf"(?<!>){_PARAMS:s}"
        rf"{MDEmphasis.MARKER_PATTERN.format(name='md_end'):s}"
    )
    _EXCLUDE_PATTERN: re.Pattern[str] = re.compile(
        rf"(?:{_DIRECTIVE_PATTERN.pattern:s})|<.*?>"
    )

    def __init__(self, concordance: Iterable[tuple[str, str]]) -> None:
        self._concordance = tuple(concordance)

    @overload
    def __getitem__(self, index: int, /) -> tuple[str, str]: ...

    @overload
    def __getitem__(self, index: slice, /) -> Sequence[tuple[str, str]]: ...

    def __getitem__(
        self,
        index: slice | int,
    ) -> Sequence[tuple[str, str]] | tuple[str, str]:
        return self._concordance[index]

    def __len__(self) -> int:
        return len(self._concordance)

    def __repr__(self) -> str:
        return f"{type(self).__name__!r:s}()"

    @classmethod
    def from_file(
        cls,
        filepath: os.PathLike[str] | str,
        separator: str = "\t",
    ) -> Self:
        r"""Creates a :py:class:`ConcordanceList` from a file.

        Args:
            filepath: The filepath.
            separator: The separator. Defaults to ``"\t"``.

        Returns:
            The corresponding :py:class:`ConcordanceList`-instance.

        Raises:
            OSError: If the concordance file cannot be opened.
        """
        filepath = pathlib.Path(filepath)
        LOGGER.info("Reading file %r", filepath.as_posix())
        try:
            with filepath.open(mode="r") as f:
                concordance = cls._parse_file(f, separator)
        except OSError as e:
            LOGGER.error(
                "cannot open concordance file %r: %s",
                filepath.as_posix(),
                e,
            )
            raise
        LOGGER.info("Read %d rules from file", len(concordance))
        if not concordance:
            LOGGER.warning(
                "File %r does not comprise rules", filepath.as_posix()
            )
        return cls(concordance)

    @staticmethod
    def _parse_file(
        text_io: TextIO,
        separator: str,
    ) -> list[tuple[str, str]]:
        data = []
        for i, line in enumerate(text_io):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            line = re.sub(rf"{separator:s}+", separator, line)
            comp = line.split(separator)
            if len(comp) == 0:
                continue

            case_sensitive = False
            if comp[0].startswith("\\="):
                # Since we use '=' as a prefix for case-sensitive,
                # allow '\=' for literal equals by stripping '\'
                comp[0] = comp[0][1:]
            elif comp[0].startswith("="):
                # Explicitly case-sensitive
                comp[0] = comp[0][1:]
                case_sensitive = True
            elif comp[0] != comp[0].lower():
                # Implicitly case-sensitive because not all-lowercase
                case_sensitive = True
            if not case_sensitive:
                comp[0] = "(?i)" + comp[0]
            if len(comp) == 1:
                comp.append("")
            data.append((comp[0].strip(), comp[1].strip()))
            LOGGER.debug("\tL%03d %r -> %r", i, *data[-1])
        return data

    def parse_text(self, text: str) -> str:
        """Parses a text and replaces found terms from the concordance list by
        the corresponding directive.

        Args:
            text: The text to parse.

        Returns:
            The parsed text.
        """
        LOGGER.info("Parsing text by concordance list")
        excluded_ranges = self._exclude_ranges(text)
        term_matches = self._match_terms(text, excluded_ranges)

        # Insert suitable index marks.
        offset = 0
        for term, replacement in term_matches:
            mark = f"[{term.group(0):s}]{{^{replacement:s}}}"
            text = insert_at_match(text, term, mark, offset=offset)
            offset += len(mark) - len(term.group(0))

        LOGGER.info(
            "Parsed text by concordance list: %d rules generated %d index "
            "marks",
            len(self._concordance),
            len(term_matches),
        )
        return text

    def _exclude_ranges(self, text: str) -> list[tuple[int, int]]:
        # Parse text for index directive and HTML tag ranges to exclude
        LOGGER.debug("Excluding text index patterns")
        excluded_ranges = []
        for excl in self._EXCLUDE_PATTERN.finditer(text):
            excluded_ranges.append((excl.start(), excl.end()))
            LOGGER.debug(
                "\tExcluded %r at (%d, %d)",
                excl.group(0),
                excl.start(),
                excl.end(),
            )
        return excluded_ranges

    def _match_terms(
        self,
        text: str,
        excluded_ranges: list[tuple[int, int]],
    ) -> list[tuple[re.Match[str], str]]:
        term_matches = []
        for pattern, replacement in self:
            # Match and replace this term expression wherever it does not
            # intersect excluded ranges
            new_exclusions = []
            last_checked = 0
            LOGGER.info("Matching pattern %r on text", pattern)
            for term in re.finditer(pattern, text):
                # Check this is not an excluded range.
                is_excluded = False
                for i in range(last_checked, len(excluded_ranges)):
                    start, end = excluded_ranges[i]
                    if end <= term.start():  # Excluded range ends before term
                        last_checked = i
                        continue
                    elif not (
                        end <= term.start() or term.end() <= start
                    ):  # Intersection, abort replacement
                        is_excluded = True
                        LOGGER.debug(
                            "Excluded range %r intersects %r",
                            text[start:end],
                            term.group(0),
                        )
                        break
                    # Excluded range ends after term
                    else:  # if start >= term.end():
                        break

                if not is_excluded:
                    LOGGER.debug(
                        "\tMatched %r at (%d, %d) in text '...%s...'",
                        pattern,
                        term.start(),
                        term.end(),
                        term.group(0),
                    )
                    term_matches.append((term, replacement))
                    new_exclusions.append((term.start(), term.end()))

            # Exclude found terms for this concordance from future matching
            excluded_ranges += new_exclusions
            excluded_ranges.sort(key=lambda e: e[0])

        # Sort all term ranges by order of appearance
        term_matches.sort(key=lambda tm: tm[0].start())
        return term_matches
