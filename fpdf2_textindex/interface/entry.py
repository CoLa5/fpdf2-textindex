"""Text Index Entry."""

from __future__ import annotations

import bisect
import dataclasses
from typing import Protocol, runtime_checkable

from fpdf2_textindex import constants as const
from fpdf2_textindex.constants import LOGGER
from fpdf2_textindex.interface.cross_reference import CrossReference
from fpdf2_textindex.interface.enums import CrossReferenceType
from fpdf2_textindex.interface.label_path import LabelPathT
from fpdf2_textindex.interface.node import Node
from fpdf2_textindex.interface.reference import Reference
from fpdf2_textindex.md_emphasis import MDEmphasis


@runtime_checkable
class TextIndexEntryP(Protocol):
    """Text Index Protocol."""

    @property
    def depth(self) -> int:
        """The depth of the entry."""
        ...

    @property
    def label(self) -> str | None:
        """The label of the entry."""
        ...

    @property
    def sort_label(self) -> str:
        """The sort label of the entry."""
        ...


@dataclasses.dataclass(kw_only=True, repr=False, slots=True)
class TextIndexEntry(Node):
    """Text Index Entry."""

    _references: list[Reference] = dataclasses.field(
        default_factory=list, init=False
    )
    """The references."""

    _cross_references: list[CrossReference] = dataclasses.field(
        default_factory=list, init=False
    )
    """The cross references."""

    sort_key: str | None = dataclasses.field(default=None, init=False)
    """The sort key."""

    def __hash__(self) -> int:
        return hash((self.id, self.label))

    @property
    def cross_references(self) -> list[CrossReference]:
        """The cross references."""
        return self._cross_references.copy()

    @property
    def references(self) -> list[Reference]:
        """The references."""
        return self._references.copy()

    @property
    def sort_label(self) -> str:
        """The sort label of the entry."""
        label = MDEmphasis.remove(self.label)
        if not label:
            label = const._LAST_SORT_LABEL
        if self.sort_key:
            label = self.sort_key + label
        return label.lower()

    @property
    def sorted_children(self) -> list[TextIndexEntry]:
        """The child entries sorted by its sort label."""
        return sorted(self._children, key=lambda c: c.sort_label)

    def add_cross_reference(
        self,
        id: int,
        cross_ref_type: CrossReferenceType,
        label_path: LabelPathT,
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
        cref = CrossReference(id=id, type=cross_ref_type, label_path=label_path)  # type: ignore[arg-type]
        if self._references and cref.type == CrossReferenceType.SEE:
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
            cref.type = CrossReferenceType.ALSO
        bisect.insort(
            self._cross_references,
            cref,
            key=lambda cr: (cr.type, *cr.label_path),
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
        ref = Reference(
            start_id=start_id,
            start_suffix=start_suffix,
            locator_emphasis=locator_emphasis,
        )
        if any(
            cref.type == CrossReferenceType.SEE
            for cref in self._cross_references
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
            for cref in self._cross_references:
                if cref.type == CrossReferenceType.SEE:
                    cref.type = CrossReferenceType.ALSO
            self._cross_references.sort(
                key=lambda cr: (cr.type, *cr.label_path)
            )
        # Note: Not sorting here because order of insertion matters for
        #       `update_latest_reference_end`
        self._references.append(ref)

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
        if len(self._references) == 0:
            msg = "cannot update latest reference end without reference"
            raise RuntimeError(msg)
        self._references[-1].end_id = end_id
        self._references[-1].end_suffix = end_suffix
