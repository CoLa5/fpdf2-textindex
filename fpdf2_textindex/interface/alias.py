"""Alias."""

from __future__ import annotations

import dataclasses

from fpdf2_textindex.interface.abc import _LabelPathABC
from fpdf2_textindex.interface.label_path import LabelPath


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class Alias(_LabelPathABC):
    """Alias."""

    name: str
    """The name of the alias."""

    label_path: LabelPath
    """The label path of the alias."""

    def __post_init__(self) -> None:
        object.__setattr__(self, "label_path", LabelPath(self.label_path))

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}"
            f"(#{self.name:s} -> {self.joined_label_path!r:s})"
        )
