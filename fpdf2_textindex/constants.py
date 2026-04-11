"""Constants."""

import logging
from typing import Final, Literal

LOGGER: logging.Logger = logging.getLogger(__name__.rsplit(".", maxsplit=1)[0])

# ID prefix/suffix
ENTRY_ID_PREFIX: Final[Literal["ent"]] = "ent"
INDEX_ID_PREFIX: Final[Literal["idx"]] = "idx"
TEXT_ID_SUFFIX: Final[Literal["t"]] = "t"  # text

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

CATEGORY_SEPARATOR: Final[Literal[". "]] = ". "
FIELD_SEPARATOR: Final[Literal[", "]] = ", "
LIST_SEPARATOR: Final[Literal["; "]] = "; "
PATH_SEPARATOR: Final[Literal[": "]] = ": "
RANGE_SEPARATOR: Final[Literal["–"]] = "–"  # noqa: RUF001
