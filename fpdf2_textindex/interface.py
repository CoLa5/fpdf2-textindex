"""Interface."""

from __future__ import annotations

import abc
from collections.abc import Iterable, Iterator
import dataclasses
import enum
from typing import Any, ClassVar

from typing_extensions import Self

from fpdf2_textindex import constants as const
from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.md_emphasis import MDEmphasis
from fpdf2_textindex.utils import join_label_path


class _LabelPathABC(abc.ABC):
    """Abstract Base class for dataclasses with `label_path`."""

    @property
    @abc.abstractmethod
    def label_path(self) -> tuple[str, ...]:
        """The label path."""
        ...

    @property
    def joined_label_path(self) -> str:
        """The joined label path."""
        return join_label_path(self.label_path)


@dataclasses.dataclass(frozen=True, kw_only=True, slots=True)
class Alias(_LabelPathABC):
    """Alias."""

    name: str
    """The name of the alias."""

    label_path: tuple[str, ...]
    """The label path of the alias."""

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}"
            f"(#{self.name:s} -> {self.joined_label_path!r:s})"
        )


@dataclasses.dataclass(kw_only=True, slots=True)
class LinkLocation:
    """Link Location."""

    page: int
    """The page the link is referened/used on."""

    x: float
    """The `x`-position on the page."""

    y: float
    """The `y`-position on the page."""

    w: float
    """The width the link has on the page."""

    h: float
    """The height the link has on the page."""


@dataclasses.dataclass(kw_only=True, slots=True)
class CrossReference(_LabelPathABC):
    """Cross Reference."""

    id: int
    """The id of the cross reference."""

    type: CrossReferenceType
    """The type of the cross reference."""

    label_path: tuple[str, ...]
    """The label path the cross reference points to."""

    location: LinkLocation | None = dataclasses.field(default=None, init=False)
    """The (link) location in the document the cross reference is set at."""

    def __str__(self) -> str:
        return f"{self.type.capitalize():s} {self.joined_label_path:s}"

    def __repr__(self) -> str:
        return f"{type(self).__name__}('{self!s:s}')"

    @property
    def link(self) -> str:
        """The link in the document that must be set in the text index to lead
        from the text to the text index.
        """
        return f"{const.INDEX_ID_PREFIX:s}{self.id:d}"


class CrossReferenceType(str, enum.Enum):
    """Cross Reference Type."""

    NONE = "none"
    """No cross reference."""

    SEE = "see"
    """SEE-cross reference."""

    ALSO = "see also"
    """SEE ALSO-cross reference."""

    def __str__(self) -> str:
        return self.value

    @classmethod
    def _missing_(cls, value: Any) -> Self | None:  # noqa: ANN401
        if value is None:
            return cls.NONE
        if isinstance(value, str):
            return cls(value.upper())
        return None


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
        n_children = len(self.children)
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
        return sorted(self._children, key=lambda c: c.label)

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
    def label_path(self) -> tuple[str, ...]:
        """The label path."""
        return tuple(
            reversed([self.label, *(p.label for p in self.iter_parents())])
        )

    def add_child(self, child: Self) -> None:
        """Adds a child.

        Args:
            child: The child to add.

        Raises:
            ValueError: If there is already a child with the same label.
        """
        if self.get_child(child.label) is not None:
            msg = "cannot add second child with same label"
            raise ValueError(msg)
        child.parent = self
        self._children.append(child)

    def get_child(self, label: str) -> Self | None:
        """Returns a child by its label or `None` if not existing.

        Args:
            label: The label to search by.

        Returns:
            The child with the label or `None` if not existing.
        """
        for child in self.children:
            if child.label == label:
                return child
        return None

    def iter_children(self) -> Iterator[Self]:
        """Iterates over the children (going down).

        Yields:
            The first child, its grandchildren, great-grandchildren, ..., then
            the second child, its grandchildren, great-grandchildren, ..., and
            so forth.
        """
        for child in self.children:
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


@dataclasses.dataclass(kw_only=True, repr=False, slots=True)
class TextIndexEntry(Node):
    """Text Index Entry."""

    references: list[Reference] = dataclasses.field(
        default_factory=list, init=False
    )
    """The references."""

    cross_references: list[CrossReference] = dataclasses.field(
        default_factory=list, init=False
    )
    """The cross references."""

    sort_key: str | None = dataclasses.field(default=None, init=False)
    """The sort key."""

    def __hash__(self) -> int:
        return hash((self.id, self.label))

    @property
    def children(self) -> list[TextIndexEntry]:
        """The child entries."""
        return sorted(self._children, key=lambda c: c.sort_label)

    @property
    def sort_label(self) -> str:
        """The sort label of the entry."""
        label = self.label
        label = MDEmphasis.remove(self.label) if self.label else "\uffff"
        if self.sort_key:
            label = self.sort_key + label
        return label.lower()

    def add_cross_reference(
        self,
        id: int,
        cross_ref_type: CrossReferenceType,
        label_path: Iterable[str],
        *,
        strict: bool = True,
    ) -> None:
        """Adds a cross reference to the entry.

        Args:
            id: The id of the cross reference.
            cross_ref_type: The type of the cross reference.
            label_path: The label path of the cross reference.
            strict: Whether to raise a `ValueError` if adding a SEE-cross
                reference to an entry with former "normal" reference (locator).
                Else, it will just be a warning and the SEE-cross reference will
                be automatically converted to SEE ALSO. Defaults to `True`.

        Raises:
            ValueError: If `strict=True` and adding a SEE-cross reference to
                an entry with former "normal" reference (locator).
        """
        if self.references and cross_ref_type == CrossReferenceType.SEE:
            if strict:
                msg = (
                    f"cannot add a SEE-cross reference to entry "
                    f"{self.joined_label_path!r} with former reference "
                    f"(locator)"
                )
                raise ValueError(msg)
            LOGGER.warning(
                "Adding a SEE-cross reference to entry %r with former "
                "reference (locator); cross reference will be converted to SEE "
                "ALSO",
                self.joined_label_path,
            )
            cross_ref_type = CrossReferenceType.ALSO
        label_path = tuple(label_path)
        if len(self.cross_references) > 0:
            for cr in self.cross_references:
                if cr.type == cross_ref_type and cr.label_path == label_path:
                    return
        self.cross_references.append(
            CrossReference(id=id, type=cross_ref_type, label_path=label_path)
        )

    def add_reference(
        self,
        start_id: int,
        *,
        locator_emphasis: bool = False,
        start_suffix: str | None = None,
        strict: bool = True,
    ) -> None:
        """Adds a reference (locator) to the entry.

        Args:
            start_id: The start id of the reference.
            locator_emphasis: Whether to emphasize the locator of the reference.
                Defaults to `False`.
            start_suffix: The start suffix of the reference. Defaults to
                `None`.
            strict: Whether to raise a `ValueError` if adding a SEE-cross
                reference to an entry with former "normal" reference (locator).
                Else, it will just be a warning and the SEE-cross reference will
                be automatically converted to SEE ALSO. Defaults to `True`.

        Raises:
            ValueError: If `strict=True` and adding a reference locator to an
                entry with former SEE-cross reference.
        """
        if any(
            cr.type == CrossReferenceType.SEE for cr in self.cross_references
        ):
            if strict:
                msg = (
                    f"cannot add a reference (locator) to entry "
                    f"{self.joined_label_path!r} with former SEE-cross "
                    f"reference"
                )
                raise ValueError(msg)
            LOGGER.warning(
                "Adding a reference (locator) to entry %r with former SEE-"
                "cross reference(s); cross reference(s) will be converted to "
                "SEE ALSO",
                self.joined_label_path,
            )
            for cr in self.cross_references:
                if cr.type == CrossReferenceType.SEE:
                    cr.type = CrossReferenceType.ALSO

        self.references.append(
            Reference(
                start_id=start_id,
                start_suffix=start_suffix,
                locator_emphasis=locator_emphasis,
            )
        )

    def update_latest_reference_end(
        self,
        end_id: int,
        end_suffix: str | None = None,
    ) -> None:
        """Updates the end of the latest reference.

        Args:
            end_id: The end id of the latest reference.
            end_suffix: The end suffix of the latest reference. Defaults to
                `None`.

        Raises:
            RuntimeError: If there has been no reference before.
        """
        if len(self.references) == 0:
            msg = "cannot update latest reference end without reference"
            raise RuntimeError(msg)
        self.references[-1].end_id = end_id
        if end_suffix:
            self.references[-1].end_suffix = end_suffix
