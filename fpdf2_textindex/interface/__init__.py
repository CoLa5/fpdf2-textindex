"""Interface."""

from fpdf2_textindex.interface.alias import Alias
from fpdf2_textindex.interface.cross_reference import CrossReference
from fpdf2_textindex.interface.entry import TextIndexEntry
from fpdf2_textindex.interface.entry import TextIndexEntryP
from fpdf2_textindex.interface.enums import CrossReferenceType
from fpdf2_textindex.interface.label_path import LabelPath
from fpdf2_textindex.interface.label_path import LabelPathT
from fpdf2_textindex.interface.link_location import LinkLocation
from fpdf2_textindex.interface.reference import Reference

__all__ = (
    "Alias",
    "CrossReference",
    "CrossReferenceType",
    "LabelPath",
    "LabelPathT",
    "LinkLocation",
    "Reference",
    "TextIndexEntry",
    "TextIndexEntryP",
)
