"""Node."""

from __future__ import annotations

import bisect
from collections.abc import Iterator
import dataclasses
from typing import ClassVar

from typing_extensions import Self

from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.interface.abc import _LabelPathABC
from fpdf2_textindex.interface.label_path import LabelPath


@dataclasses.dataclass(kw_only=True, repr=False, slots=True)
class Node(_LabelPathABC):
    """Node."""

    _next_id: ClassVar[int] = 0

    id: int = dataclasses.field(init=False)
    """The id."""

    label: str
    """The label."""

    parent: Self | None = None
    """The parent."""

    _children: list[Self] = dataclasses.field(default_factory=list, init=False)
    """The children."""

    def __post_init__(self) -> None:
        self.id = type(self)._next_id
        type(self)._next_id += 1

        if self.parent is not None:
            self.parent.add_child(self)  # type: ignore[arg-type]

    def __bool__(self) -> bool:
        return True

    def __iter__(self) -> Iterator[Self]:
        yield self
        yield from self.iter_children()

    def __hash__(self) -> int:
        return hash((self.id, self.label))

    def __repr__(self) -> str:
        kw: dict[str, int | str] = {}
        kw["id"] = self.id
        kw["label"] = repr(self.label)
        kw["depth"] = self.depth
        kw["label_path"] = repr(self.joined_label_path)
        n_children = len(self._children)
        kw["children"] = (
            f"[{n_children:d} child{'ren' if n_children > 1 else '':s}]"
        )
        kw_str = ", ".join(f"{k:s}: {v!s:s}" for k, v in kw.items())
        return f"{type(self).__name__:s}({kw_str:s})"

    def __str__(self) -> str:
        return self.label or ""

    @property
    def children(self) -> list[Self]:
        """The sorted children."""
        return self._children.copy()

    @property
    def depth(self) -> int:
        """The depth.

        Possible values are:
        - (invisible) root: 0,
        - entries: 1,
        - subentries: 2,
        - sub-subentries: 3.

        Deeper entries are not recommended.
        """
        return sum(1 for _ in self.iter_parents()) + 1

    @property
    def label_path(self) -> LabelPath:
        """The label path."""
        return LabelPath(
            reversed([self.label, *(p.label for p in self.iter_parents())])
        )

    def add_child(self, child: Self) -> None:
        """Adds a child.

        Args:
            child: The child to add.

        Raises:
            ValueError: If there is already a child with the same label.
        """
        if self.depth >= 3:
            LOGGER.warning(
                "Entries below sub-subentries (`depth >= 3`) are not "
                "recommended"
            )
        if self.get_child(child.label) is not None:
            msg = "cannot add second child with same label"
            raise ValueError(msg)
        if child.parent is None:
            child.parent = self
        elif child.parent is not self:
            msg = "cannot add child to second parent"
            raise ValueError(msg)
        child.parent = self
        bisect.insort(self._children, child, key=lambda c: c.label)

    def get_child(self, label: str) -> Self | None:
        """Returns a child by its label or `None` if not existing.

        Args:
            label: The label to search by.

        Returns:
            The child with the label or `None` if not existing.
        """
        idx = bisect.bisect_left(self._children, label, key=lambda c: c.label)
        if idx < len(self._children) and self._children[idx].label == label:
            return self._children[idx]
        return None

    def iter_children(self) -> Iterator[Self]:
        """Iterates over the children (going down).

        Yields:
            The first child, its grandchildren, great-grandchildren, ..., then
            the second child, its grandchildren, great-grandchildren, ..., and
            so forth.
        """
        for child in self._children:
            yield from iter(child)  # type: ignore[misc]

    def iter_parents(self) -> Iterator[Self]:
        """Iterates over the parents without the root (going up).

        Yields:
            The parent, grandparent, great-grandparent, ..., and so forth,
            stopping before root.
        """
        # Do not yield root
        if self.parent is None:
            return
        par = self.parent
        while par.parent is not None:
            yield par
            par = par.parent
