"""fpdf2 Text Index."""

from fpdf2_textindex.interface import Alias
from fpdf2_textindex.interface import CrossReference
from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import LinkLocation
from fpdf2_textindex.interface import Reference
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.pdf import FPDF
from fpdf2_textindex.renderer import TextIndexRenderer

__all__ = (
    "FPDF",
    "Alias",
    "CrossReference",
    "CrossReferenceType",
    "LinkLocation",
    "Reference",
    "TextIndexEntry",
    "TextIndexRenderer",
)
