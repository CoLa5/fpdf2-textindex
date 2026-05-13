"""Label Path."""

from __future__ import annotations

from collections.abc import Iterable
from typing import SupportsIndex, TypeAlias, overload

from typing_extensions import Self

from fpdf2_textindex import constants as const
from fpdf2_textindex.utils import remove_quotes


class LabelPath(tuple[str, ...]):
    """Label Path."""

    def __new__(cls, labels: Self | Iterable[str] | str = ()) -> Self:
        """Initializes the `LabelPath`.

        Args:
            labels: The labels composing the label path.

        Raises:
            TypeError: If `labels` does not have type `LabelPath`,
                `Iterable[str]` or `str`.
        """
        if isinstance(labels, cls):
            return labels
        elif isinstance(labels, Iterable):
            labels_ = tuple(labels)
        elif isinstance(labels, str):
            labels_ = (labels,)
        elif labels is None:
            labels_ = tuple()
        else:
            msg = f"invalid type of `labels`: {type(labels).__name__:s}"
            raise TypeError(msg)
        if not all(isinstance(la, str) for la in labels_):
            msg = "invalid type of `labels`-elements: all must be `str`"
            raise TypeError(msg)
        return super().__new__(cls, (remove_quotes(la) for la in labels_))

    @overload
    def __getitem__(self, i: SupportsIndex) -> str: ...

    @overload
    def __getitem__(self, i: slice) -> Self: ...

    def __getitem__(self, i: SupportsIndex | slice) -> Self | str:
        result = super().__getitem__(i)
        if isinstance(result, tuple):
            return type(self)(result)
        return result

    def __repr__(self) -> str:
        return f"{type(self).__name__:s}({super().__repr__()[1:-1]:s})"

    def __str__(self) -> str:
        return self.join()

    def join(self) -> str:
        """Returns the joined label path.

        Returns:
            The label path, joined by the path delimiter.
        """
        return f" {const.PATH_DELIMITER:s} ".join(f'"{la:s}"' for la in self)

    @classmethod
    def split_str(cls, label_path_str: str) -> Self:
        """Splits a label path string by the path delimiter, removes quotes
        from its elements and returns the corresponding label path.

        Args:
            label_path_str: The label path string to split.

        Returns:
            The corresponding label path.
        """
        return cls(label_path_str.split(const.PATH_DELIMITER))


LabelPathT: TypeAlias = LabelPath | Iterable[str] | str
"""Label Path Type."""
