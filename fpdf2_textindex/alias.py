"""Alias Registry."""

from collections.abc import Iterator, Mapping
import logging
import re
from typing import Final, Literal

from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.interface import Alias
from fpdf2_textindex.interface import LabelPath
from fpdf2_textindex.interface import LabelPathT


class AliasRegistry(Mapping[str, Alias]):
    """Alias Registry.

    Maps an alias by a name `"#alias"` to an entry by its label path.
    """

    _ALIAS_PREFIX: Final[Literal["#"]] = "#"
    _ALIAS_TOKEN_PATTERN: re.Pattern[str] = re.compile(
        rf"(?<!{_ALIAS_PREFIX:s}){_ALIAS_PREFIX:s}([a-zA-Z0-9\-_]+)"
    )
    _ALIAS_DEFINITION_PATTERN: re.Pattern[str] = re.compile(
        rf"{_ALIAS_PREFIX:s}({_ALIAS_PREFIX:s}?[a-zA-Z0-9\-_]+)$"
    )

    def __init__(self) -> None:
        self._aliases: dict[str, Alias] = {}

    def __getitem__(self, name: str) -> Alias:
        return self._aliases[name]

    def __iter__(self) -> Iterator[str]:
        return iter(self._aliases)

    def __len__(self) -> int:
        return len(self._aliases)

    def __repr__(self) -> str:
        return f"{type(self).__name__:s}({len(self):d} aliases)"

    def define(self, name: str, label_path: LabelPathT) -> None:
        """Defines an alias.

        Args:
            name: The name of the alias.
            label_path: The label path the alias will be replaced by.

        Raises:
            ValueError: If the label path is empty.
        """
        label_path = LabelPath(label_path)
        if len(label_path) == 0:
            msg = f"cannot create alias {name!r:s} with empty label path"
            raise ValueError(msg)

        redefinition = False
        if (
            name in self._aliases
            and self._aliases[name].label_path != label_path
        ):
            redefinition = True

        self._aliases[name] = Alias(name=name, label_path=label_path)
        LOGGER.log(
            logging.WARNING if redefinition else logging.INFO,
            "\t%s alias '%s%s' as %r",
            "Redefined existing" if redefinition else "Defined new",
            self._ALIAS_PREFIX,
            name,
            self._aliases[name].joined_label_path,
        )

    def define_or_replace_from_label_path(
        self,
        label_path: LabelPathT,
        label: str | None,
        content: str,
        alias_name: str | None,
        alias_start: int,
        directive_str: str,
    ) -> tuple[LabelPath, str | None, bool]:
        """Defines an alias from a label path and label or replaces an alias in
        it.

        Args:
            label_path: The label path to use for the definition.
            label: The label of the parsed directive.
            content: The content of the parsed directive.
            alias_name: The name of the alias.
            alias_start: The start index of the alias in the directive.
            directive_str: The original directive.

        Returns:
            The label path, the label, and whether it has been an unreferenced
            alias. The label path and the label can differ from the input in
            case the alias existed before.
        """
        label_path = LabelPath(label_path)
        unreferenced_alias = False
        if alias_name is None:
            return label_path, label, unreferenced_alias

        if alias_name.startswith(self._ALIAS_PREFIX):
            unreferenced_alias = True
            alias_name = alias_name.lstrip(self._ALIAS_PREFIX)

        # Alias definition at end of an internally-specified label.
        if alias_start > 0:
            assert label is not None
            self.define(alias_name, LabelPath((*label_path, label)))

        # Alias found at start of label:
        # Either an alias reference, or a definition without an internal label
        # (foo>#bar or just #bar)
        elif len(label_path) == 0:
            # No path components. Could be an alias definition at root, or an
            # alias reference

            # Try to load the alias
            if alias_name in self._aliases:
                # Valid alias reference, load alias
                alias = self._aliases[alias_name]
                label_path = alias.label_path
                assert label is None
                label = label_path[-1]
                label_path = label_path[:-1]
                LOGGER.info(
                    "\tLoaded alias %r as %r for directive: %r",
                    alias_name,
                    alias.joined_label_path,
                    directive_str,
                )
            # No path components, and an alias reference to a non-existing
            # alias, define a new alias instead
            elif content:
                label = content
                self.define(alias_name, LabelPath(label))
            else:
                LOGGER.warning(
                    "Cannot load nor define alias %r for directive: %r",
                    alias_name,
                    directive_str,
                )

        # Path components exist, so this is an alias definition without an
        # internal label
        else:
            if content:
                # We already had a label from either a bracketed span, or
                # implicitly, define alias
                label = content
                self.define(alias_name, LabelPath((*label_path, label)))
            else:
                # No label specified either internally or previously;
                # can't define an alias.
                label = None
                LOGGER.warning(
                    "Alias definition %r without a label: %r",
                    alias_name,
                    directive_str,
                )
        return label_path, label, unreferenced_alias

    def _replace_match(self, match: re.Match[str]) -> str:
        name = match.group(1)
        replacement = match.group(0)
        if name and name in self._aliases:
            replacement = self._aliases[name].joined_label_path
        return replacement

    def replace_aliases(self, directive_str: str) -> str:
        """Replaces aliases in a directive by its defined label path.

        Args:
            directive_str: The original directive.

        Returns:
            The directive with replaced aliases.
        """
        if len(self._aliases) == 0 or len(directive_str) == 0:
            return directive_str
        return self._ALIAS_TOKEN_PATTERN.sub(self._replace_match, directive_str)

    def strip_alias(self, directive_str: str) -> tuple[str, str | None, int]:
        """Strips an alias definition from the end of a directive.

        Args:
            directive_str: The original directive.

        Returns:
            A tuple comprising the directive without the alias,
            the found alias name (or `None` in case of no alias directive),
            and the start index of the alias (or `-1` in case of no alias
            directive).
        """
        match = self._ALIAS_DEFINITION_PATTERN.search(directive_str)
        alias_start = -1
        alias_name = None
        if match:
            alias_start = match.start()
            alias_name = match.group(1)
            directive_str = directive_str[: match.start()]
        return directive_str, alias_name, alias_start
