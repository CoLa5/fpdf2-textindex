"""Abstract Classes."""

from __future__ import annotations

import abc

from fpdf2_textindex.interface.label_path import LabelPath


class _LabelPathABC(abc.ABC):
    """Abstract Base class for dataclasses with `label_path`."""

    @property
    @abc.abstractmethod
    def label_path(self) -> LabelPath:
        """The label path."""
        ...

    @property
    def joined_label_path(self) -> str:
        """The joined label path."""
        return self.label_path.join()
