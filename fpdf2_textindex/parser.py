"""Text Index Parser."""

from collections.abc import Iterable, Iterator
import itertools
import logging
import re
from typing import Final, TYPE_CHECKING

from fpdf2_textindex import constants as const
from fpdf2_textindex.alias import AliasRegistry
from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.interface import Alias
from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import LinkLocation
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.md_emphasis import MDEmphasis
from fpdf2_textindex.utils import insert_at_match
from fpdf2_textindex.utils import join_label_path
from fpdf2_textindex.utils import remove_match_from_str
from fpdf2_textindex.utils import remove_quotes
from fpdf2_textindex.utils import split_label_path


class TextIndexParser:
    """Text Index Parser.

    Parses text(s), finds text index directives, creates the corresponding
    entries and replaces the directives by corresponding markdown links.
    """

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

    _CROSS_REF_IN_PARAMS_PATTERN: re.Pattern[str] = re.compile(r"\|(.+)$")
    _LABEL_PATH_IN_PARAMS_PATTERN: re.Pattern[str] = re.compile(
        rf"^((?:[^\|\[~]|{MDEmphasis.STRIKETHROUGH.marker:s})+)"
    )
    _SEARCH_WILDCARD_PATTERN: re.Pattern[str] = re.compile(r"\*\^(\-?)")
    _SORT_KEY_IN_PARAMS_PATTERN: re.Pattern[str] = re.compile(
        r"\s*\~(['\"]?)(.+)\1$"
    )
    _SUFFIX_IN_PARAMS_PATTERN: re.Pattern[str] = re.compile(
        r"\s*\[(?P<suffix>(?:[^\]\"]+|\"[^\"]+\")+)(?<!\\)\]\s*"
    )

    def __init__(
        self,
        *,
        strict: bool = True,
    ) -> None:
        """Initializes the parser.

        Args:
            strict: If ``True`` and an entry has a normal reference (locator)
                and a SEE cross reference, a ``ValueError`` will be raised.
                Else, it will just be warned. Defaults to ``True``.
        """
        self._alias_reg = AliasRegistry()
        self._enabled = True
        self._link_locations: dict[str, LinkLocation] = {}
        self._directive_id = -1
        self._root = TextIndexEntry(label="root")
        self._strict = bool(strict)

    def __iter__(self) -> Iterator[TextIndexEntry]:
        yield from itertools.islice(iter(self._root), 1, None)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __repr__(self) -> str:
        return f"{type(self).__name__:s}({len(self):d} entries)"

    @property
    def aliases(self) -> list[Alias]:
        """The parsed aliases."""
        return list(self._alias_reg.values())

    @property
    def entries(self) -> list[TextIndexEntry]:
        """The parsed entries."""
        return list(iter(self))

    @property
    def last_directive_id(self) -> int:
        """Last directive id."""
        return self._directive_id

    @property
    def last_index_id(self) -> str:
        """Last index id."""
        return f"{const.INDEX_ID_PREFIX:s}{self._directive_id:d}"

    def entry_at_label_path(
        self,
        label_path: Iterable[str],
        *,
        create: bool = False,
    ) -> tuple[TextIndexEntry | None, bool]:
        """Returns an entry by its label path.

        If ``create=True`` and the entry does not exist, it will be created.

        Args:
            label_path: The label path.
            create: Whether to create the entry if it does not exist already.
                Defaults to ``False``.

        Returns:
            The found :py:class:`TextIndexEntry` or ``None`` and whether the
            entry has existed before.
        """
        created = False
        node = self._root
        for label in label_path:
            child = node.get_child(label)
            if child is None:
                if not create:
                    LOGGER.warning("Failed to find %r", label)
                    return None, False
                LOGGER.debug(
                    "Making new entry %r (%s)",
                    label,
                    f"within {node.label!r:s}" if node.parent else "at root",
                )
                child = TextIndexEntry(label=label, parent=node)
                created = True
            node = child
        return node, not created

    def parse_text(self, text: str) -> str:
        """Parses a text, finds text index directives, creates the corresponding
        entries and replaces the directives by corresponding markdown links.

        Args:
            text: The text to parse.

        Returns:
            The parsed text.

        Raises:
            RuntimeError: If a directive cannot be parsed.
            ValueError:
                - If the label cannot be identified correctly.
                - If ``strict=True`` and and adding a SEE-cross reference to
                    an entry with former "normal" reference (locator) or
                    viceversa.
        """
        LOGGER.info("Parsing text by index parser")

        former_len = len(self)
        offset = 0  # Account for replacements

        for directive in self._DIRECTIVE_PATTERN.finditer(text):
            # Parse and encapsulate each entry, either as object or range-end
            LOGGER.debug("Directive found: %r", directive.group(0))
            self._directive_id += 1
            params = directive.group("params").strip()

            params, toggling, status_toggled = self._parse_toggling_directive(
                params
            )
            if toggling and (self._enabled or status_toggled):
                # This was a toggling mark, and we are either now enabled or we
                # were when we encountered it, remove the mark.
                text = remove_match_from_str(text, directive, offset=offset)
                offset += -len(directive.group(0))
                continue
            if not toggling and not self._enabled:
                LOGGER.debug(
                    "Disabled, ignoring directive: %r", directive.group(0)
                )
                continue

            label, content = self._parse_label(directive)

            params, closing, locator_emphasis = self._parse_final_marker(params)
            params, label_path, label, unreferenced_alias = (
                self._parse_label_path(
                    params, label, content, directive.group(0)
                )
            )
            # Found unreferenced alias
            if unreferenced_alias:
                LOGGER.log(
                    logging.INFO if label else logging.WARNING,
                    "\tUnreferenced alias %s; skipping rest of directive: %r",
                    "created" if label else "definition without a label",
                    directive.group(0),
                )
                # Replace directive in text
                text = insert_at_match(text, directive, content, offset=offset)
                offset += len(content) - len(directive.group(0))
                continue

            LOGGER.debug("\tLabel path: %s", label_path)
            LOGGER.debug("\tLabel: %r", label)
            if not label:
                LOGGER.warning(
                    "No entry label specified in directive, ignoring: %r",
                    directive.group(0),
                )
                continue

            params, suffix = self._parse_suffix(params)
            params, sort_key = self._parse_sort_key(params, content)
            params, create_ref, cross_references = self._parse_cross_ref(
                params, label_path, label, content
            )
            if params.strip():
                msg = f"Unparsed directive content: {params!r:s}"
                LOGGER.error(msg)
                raise RuntimeError(msg)

            # Insert into entries tree
            replace_directive = self._update_index(
                label_path,
                label,
                create_ref,
                cross_references,
                closing,
                directive.group(0),
                locator_emphasis,
                sort_key,
                suffix,
            )
            if not replace_directive:
                continue

            # Replace directive in text with suitable link
            link = self._create_link(content)
            text = insert_at_match(text, directive, link, offset=offset)
            offset += len(link) - len(directive.group(0))

        LOGGER.info("Parsed text: %d entries created", len(self) - former_len)
        LOGGER.debug(
            "Created text: %r",
            text if len(text) < 60 else text[:30] + "..." + text[-30:],
        )
        return text

    def _create_link(self, content: str) -> str:
        unstyled_label, label_emphasis = MDEmphasis.parse(content)
        return label_emphasis.format(
            f"[{unstyled_label:s}](#{self.last_index_id:s})"
        )

    def _parse_cross_ref(
        self,
        params: str,
        label_path: Iterable[str],
        label: str,
        content: str,
    ) -> tuple[str, bool, list[tuple[CrossReferenceType, list[str]]]]:
        create_ref = True
        cross_references: list[tuple[CrossReferenceType, list[str]]] = []
        params = params.strip()
        cross_match = self._CROSS_REF_IN_PARAMS_PATTERN.match(params)
        if cross_match is None:
            return params, create_ref, cross_references

        refs_string = cross_match.group(1).strip()

        # Process aliases before splitting path
        refs_string = self._alias_reg.replace_aliases(refs_string)

        # Handle wildcards in cross-refs
        refs_string = self._parse_wildcards(refs_string, content)

        refs = refs_string.split(const.REFS_DELIMITER)
        for ref in refs:
            ref = ref.strip()

            inbound = ref.startswith(const.INBOUND_MARKER)
            if inbound:
                ref = ref[len(const.INBOUND_MARKER) :]

            ref_type = (
                CrossReferenceType.ALSO
                if ref.startswith(const.ALSO_MARKER)
                else CrossReferenceType.SEE
            )
            if ref_type == CrossReferenceType.ALSO:
                ref = ref[len(const.ALSO_MARKER) :]
            elif not inbound:
                # Do not create a (page-) reference for this mark's entry if
                # there is a (non-also) cross reference.
                create_ref = False

            # Split reference label path
            ref_label_path = split_label_path(ref)

            # Cross-ref in different entry, referencing this mark's entry
            if inbound:
                source_entry, _ = self.entry_at_label_path(
                    ref_label_path, create=True
                )
                if TYPE_CHECKING:
                    assert isinstance(source_entry, TextIndexEntry)
                LOGGER.debug(
                    "\tCreating inbound %s cross reference from entry %r (%s)",
                    ref_type.upper(),
                    ref_label_path[-1],
                    f"Path: {source_entry.joined_label_path!r:s}"
                    if len(ref_label_path) > 1
                    else "at root",
                )
                source_entry.add_cross_reference(
                    self._directive_id,
                    ref_type,
                    [*label_path, label],
                    strict=self._strict,
                )

            # Cross-ref within this mark's entry
            else:
                cross_references.append((ref_type, ref_label_path))

        params = remove_match_from_str(params, cross_match)
        if len(cross_references) > 0:
            LOGGER.debug("\tCross references: %r", cross_references)
        return params, create_ref, cross_references

    def _parse_final_marker(self, params: str) -> tuple[str, bool, bool]:
        params = params.strip()
        closing = params.endswith(const.CLOSING_MARKER)
        locator_emphasis = params.endswith(const.EMPHASIS_MARKER)
        if closing:
            params = params[: -len(const.CLOSING_MARKER)]
            LOGGER.debug("\tClosing mark: %r", const.CLOSING_MARKER)
        elif locator_emphasis:
            params = params[: -len(const.EMPHASIS_MARKER)]
            LOGGER.debug("\tLocator Emphasis: %r", const.EMPHASIS_MARKER)
        return params, closing, locator_emphasis

    def _parse_label(
        self,
        directive: re.Match[str],
    ) -> tuple[str | None, str]:
        label = None
        #  Leading bracketed span "[x]{^}"
        if directive.group("leading_bracket_span"):
            label = directive.group("leading_bracket_span")
            if (
                directive.group("md_start") is not None
                and directive.group("md_start")
                == directive.group("md_end")[::-1]
            ):
                label = (
                    directive.group("md_start")
                    + label
                    + directive.group("md_end")
                )
        #  Leading implicit non-whitespace span  "X{^}"
        elif directive.group("leading_non_whitespace_span"):
            label = directive.group("leading_non_whitespace_span")
            for end in ("md_center", "md_end"):
                if (
                    directive.group("md_start") is not None
                    and directive.group("md_start")
                    == directive.group(end)[::-1]
                ):
                    label = (
                        directive.group("md_start")
                        + label
                        + directive.group(end)
                    )

        content = label or ""
        LOGGER.debug("\tContent: %r", content)
        return label, content

    def _parse_label_path(
        self,
        params: str,
        label: str | None,
        content: str,
        directive_str: str,
    ) -> tuple[str, list[str], str | None, bool]:
        label_path: list[str] = []
        label_path_match = self._LABEL_PATH_IN_PARAMS_PATTERN.match(params)
        if not label_path_match:
            return params, label_path, label, False

        label_path_str = label_path_match.group(0).strip()

        # Process aliases before splitting path.
        label_path_str = self._alias_reg.replace_aliases(label_path_str)

        # Handle wildcards in label path
        label_path_str = self._parse_wildcards(label_path_str, label)

        # Having already replaced alias references, check for alias
        # definition at end of label path
        label_path_str, alias_name, alias_start = self._alias_reg.strip_alias(
            label_path_str
        )

        # Split label path
        label_path = split_label_path(label_path_str)

        # Last item is now the label
        if label_path[-1] not in {"", const.PATH_DELIMITER}:
            label = label_path.pop()
        assert isinstance(label, str)

        # Remove empty last label
        if label_path and label_path[-1] == "":
            label_path.pop()

        # Assert label
        if label is None:
            msg = "cannot identify label: %r"
            LOGGER.error(msg, directive_str)
            raise ValueError(msg % directive_str)

        # Trim label path from params.
        params = remove_match_from_str(params, label_path_match)

        # Check for alias definition.
        label_path, label, unreferenced_alias = (
            self._alias_reg.define_or_replace_from_label_path(
                label_path,
                label,
                content,
                alias_name,
                alias_start,
                directive_str,
            )
        )

        return params, label_path, label, unreferenced_alias

    def _parse_sort_key(
        self,
        params: str,
        content: str,
    ) -> tuple[str, str | None]:
        params = params.strip()
        match = self._SORT_KEY_IN_PARAMS_PATTERN.search(params)
        if match is not None:
            sort_key = match.group(2)
            # Handle wildcards in sort key
            sort_key = self._parse_wildcards(
                sort_key,
                content,
                force_label_only=True,
            )
            params = remove_match_from_str(params, match)
            LOGGER.debug("\tSort key: %r", sort_key)
            return params, sort_key
        return params, None

    def _parse_suffix(self, params: str) -> tuple[str, str | None]:
        params = params.strip()
        match = self._SUFFIX_IN_PARAMS_PATTERN.search(params)
        if match is not None:
            suffix = match.group("suffix")
            suffix = remove_quotes(suffix)
            params = remove_match_from_str(params, match)
            LOGGER.debug("\tSuffix: %r", suffix)
            return params, suffix
        return params, None

    def _parse_toggling_directive(self, params: str) -> tuple[str, bool, bool]:
        params = params.strip()
        toggling = params in {const.DISABLE_MARKER, const.ENABLE_MARKER}
        if not toggling:
            return params, toggling, False

        status_toggled = False
        if params == const.ENABLE_MARKER and not self._enabled:
            self._enabled = True
            status_toggled = True
            LOGGER.info("============ Processing enabled.  ============")
        elif params == const.DISABLE_MARKER and self._enabled:
            self._enabled = False
            status_toggled = True
            LOGGER.info("============ Processing disabled. ============")
        return "", toggling, status_toggled

    def _parse_wildcards(
        self,
        directive_str: str,
        label: str | None,
        *,
        force_label_only: bool = False,
    ) -> str:
        if not label:
            return directive_str

        found_wildcards = list(
            self._SEARCH_WILDCARD_PATTERN.finditer(directive_str)
        )
        found_item = (
            self._prefix_search(label) if len(found_wildcards) > 0 else None
        )
        if isinstance(found_item, TextIndexEntry):
            replace_label = f'"{found_item.label:s}"'
            replace_path = found_item.joined_label_path
            for found_wildcard in reversed(found_wildcards):
                label_only = (found_wildcard.group(1) != "") or force_label_only
                replacement = replace_label if label_only else replace_path
                directive_str = (
                    directive_str[: found_wildcard.start()]
                    + replacement
                    + directive_str[found_wildcard.end() :]
                )
                LOGGER.debug(
                    "\tFound %sprefix match for %r: %r",
                    "(label-only) " if label_only else "",
                    label,
                    replacement,
                )
        else:
            for found_wildcard in reversed(found_wildcards):
                directive_str = (
                    directive_str[: found_wildcard.start()]
                    + "*"  # Fallback on basic wildcard functionality.
                    + directive_str[found_wildcard.end() :]
                )
        unstyled_label = MDEmphasis.parse(label)[0]
        directive_str = directive_str.replace("**", unstyled_label.lower())
        directive_str = directive_str.replace("*", unstyled_label)
        return directive_str

    def _prefix_search(self, text: str) -> TextIndexEntry | None:
        for entry in self:
            if entry.label.startswith(text):
                return entry
        return None

    def _update_index(
        self,
        label_path: Iterable[str],
        label: str,
        create_ref: bool,
        cross_references: list[tuple[CrossReferenceType, list[str]]],
        closing: bool,
        directive: str,
        locator_emphasis: bool,
        sort_key: str | None,
        suffix: str | None,
    ) -> bool:
        entry, existed = self.entry_at_label_path(
            [*label_path, label],
            create=not closing,
        )
        if not entry and closing:
            LOGGER.warning(
                "Attempted to close a non-existent entry %r; ignoring: %r",
                join_label_path([*label_path, label]),
                directive,
            )
            return False

        # Entry exists and we are closing its range,
        if entry and closing:
            if entry.references:
                # If it already has a closing ID, update it, but warn
                if entry.references[-1].end_id is not None:
                    LOGGER.warning(
                        "Altering existing end-location of reference %r: %r",
                        entry.joined_label_path,
                        directive,
                    )
                entry.update_latest_reference_end(
                    self._directive_id,
                    end_suffix=suffix,
                )
                LOGGER.debug(
                    "\tSet end-location for reference to %r",
                    entry.joined_label_path,
                )
            else:
                # Entry exists, but has no references, so we can't set a
                # closing id.
                LOGGER.warning(
                    "Attempted to close non-existent reference for "
                    "existing entry %r; ignoring: %r",
                    entry.joined_label_path,
                    directive,
                )
            return True

        # We now have the correct entry, whether it existed before or not
        if TYPE_CHECKING:
            assert isinstance(entry, TextIndexEntry)
        if create_ref:
            entry.add_reference(
                self._directive_id,
                locator_emphasis=locator_emphasis,
                strict=self._strict,
                suffix=suffix,
            )
        elif suffix or locator_emphasis:
            LOGGER.warning(
                "Ignoring suffix/locator emphasis in cross reference: %r",
                directive,
            )

        if sort_key:
            if entry.sort_key and entry.sort_key != sort_key:
                LOGGER.warning(
                    "Altering existing sort-key for reference %r: "
                    "before: %r, now: %r, directive: %r",
                    entry.joined_label_path,
                    entry.sort_key,
                    sort_key,
                    directive,
                )
            entry.sort_key = sort_key

        if len(cross_references) > 0:
            if existed:
                LOGGER.debug(
                    "\tAdding cross references to existing entry %r",
                    entry.joined_label_path,
                )
            for ref_type, ref_label_path in cross_references:
                entry.add_cross_reference(
                    self._directive_id,
                    ref_type,
                    ref_label_path,
                    strict=self._strict,
                )

        return True
