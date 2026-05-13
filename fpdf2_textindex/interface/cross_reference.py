"""Cross Reference."""

from __future__ import annotations

import dataclasses

from fpdf2_textindex import constants as const
from fpdf2_textindex.interface.abc import _LabelPathABC
from fpdf2_textindex.interface.enums import CrossReferenceType
from fpdf2_textindex.interface.label_path import LabelPath
from fpdf2_textindex.interface.link_location import LinkLocation


@dataclasses.dataclass(kw_only=True, slots=True)
class CrossReference(_LabelPathABC):
    """Cross Reference."""

    id: int
    """The id of the cross reference."""

    type: CrossReferenceType
    """The type of the cross reference."""

    label_path: LabelPath
    """The label path the cross reference points to."""

    location: LinkLocation | None = dataclasses.field(default=None, init=False)
    """The (link) location in the document the cross reference is set at."""

    def __post_init__(self) -> None:
        self.label_path = LabelPath(self.label_path)
        self.type = CrossReferenceType(self.type)

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self!s:s}')"

    def __str__(self) -> str:
        return f"{self.type.capitalize():s} {self.joined_label_path:s}"

    @property
    def link(self) -> str:
        """The link in the document that must be set in the text index to lead
        from the text to the text index.
        """
        return f"{const.INDEX_ID_PREFIX:s}{self.id:d}"
