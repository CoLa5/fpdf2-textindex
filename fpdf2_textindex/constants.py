"""Constants."""

import logging
from typing import Final, Literal

LOGGER: logging.Logger = logging.getLogger(__name__.rsplit(".", maxsplit=1)[0])

# ID prefix/suffix
ENTRY_ID_PREFIX: Final[Literal["ent"]] = "ent"
INDEX_ID_PREFIX: Final[Literal["idx"]] = "idx"
TEXT_ID_SUFFIX: Final[Literal["t"]] = "t"  # from index to text

# Directives
PATH_DELIMITER: Final[Literal[">"]] = ">"
REFS_DELIMITER: Final[Literal[";"]] = ";"

ALSO_MARKER: Final[Literal["+"]] = "+"
CLOSING_MARKER: Final[Literal["/"]] = "/"
DISABLE_MARKER: Final[Literal["-"]] = "-"
EMPHASIS_MARKER: Final[Literal["!"]] = "!"
ENABLE_MARKER: Final[Literal["+"]] = "+"
INBOUND_MARKER: Final[Literal["@"]] = "@"

# Output
REFERENCES_LIMIT: Final[int] = 10
"""The limit of references per entry before a warning is shown."""

CATEGORY_SEPARATOR: Final[Literal[". "]] = ". "
"""Category separator."""

FIELD_SEPARATOR: Final[Literal[", "]] = ", "
"""Field separator."""

LIST_SEPARATOR: Final[Literal["; "]] = "; "
"""List separator."""

PATH_SEPARATOR: Final[Literal[": "]] = ": "
"""Path separator."""

RANGE_SEPARATOR: Final[Literal["–"]] = "–"  # noqa: RUF001
"""Range separator."""
