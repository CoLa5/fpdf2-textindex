"""Reference."""

from __future__ import annotations

import dataclasses

from fpdf2_textindex import constants as const
from fpdf2_textindex.interface.link_location import LinkLocation


@dataclasses.dataclass(kw_only=True, slots=True)
class Reference:
    """Reference."""

    start_id: int
    """The start id of the reference."""

    start_suffix: str | None = None
    """The start suffix of the reference or `None`."""

    start_location: LinkLocation | None = dataclasses.field(
        default=None, init=False
    )
    """The start (link) location in the document the reference is set at."""

    end_id: int | None = dataclasses.field(default=None, init=False)
    """The end id of the reference or `None`."""

    end_suffix: str | None = dataclasses.field(default=None, init=False)
    """The end suffix of the reference or `None`."""

    end_location: LinkLocation | None = dataclasses.field(
        default=None, init=False
    )
    """The end (link) location in the document the reference is set at."""

    locator_emphasis: bool = False
    """Whether to emphasize the locator (page number) of the reference in the
    text index (`True`) or not (`False`)."""

    @property
    def start_link(self) -> str:
        """The start link in the document that must be set in the text index to
        lead from the text to the text index.
        """
        return f"{const.INDEX_ID_PREFIX:s}{self.start_id:d}"

    @property
    def end_link(self) -> str | None:
        """The end link in the document that must be set in the text index to
        lead from the text to the text index. In case of no end id, the end link
        will be `None`.
        """
        if self.end_id is None:
            return None
        return f"{const.INDEX_ID_PREFIX:s}{self.end_id:d}"
