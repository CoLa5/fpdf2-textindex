"""
.. include:: ../README.md
   :start-line: 8

The module gives direct access to some classes defined in submodules:

* :py:class:`fpdf2_textindex.interface.Alias`
* :py:class:`fpdf2_textindex.interface.CrossReference`
* :py:class:`fpdf2_textindex.interface.CrossReferenceType`
* :py:class:`fpdf2_textindex.interface.LinkLocation`
* :py:class:`fpdf2_textindex.interface.Reference`
* :py:class:`fpdf2_textindex.interface.TextIndexEntry`
* :py:class:`fpdf2_textindex.pdf.FPDF`
* :py:class:`fpdf2_textindex.renderer.TextIndexRenderer`
"""  # noqa: D212, D415

from fpdf2_textindex.interface import Alias
from fpdf2_textindex.interface import CrossReference
from fpdf2_textindex.interface import CrossReferenceType
from fpdf2_textindex.interface import LinkLocation
from fpdf2_textindex.interface import Reference
from fpdf2_textindex.interface import TextIndexEntry
from fpdf2_textindex.pdf import FPDF
from fpdf2_textindex.renderer import TextIndexRenderer
from fpdf2_textindex.version import FPDF2_TEXTINDEX_VERSION

__docformat__ = "google"
__license__ = "GPL 3.0"
__version__ = FPDF2_TEXTINDEX_VERSION

__all__ = (
    "FPDF",
    "Alias",
    "CrossReference",
    "CrossReferenceType",
    "LinkLocation",
    "Reference",
    "TextIndexEntry",
    "TextIndexRenderer",
    "__license__",
    "__version__",
)
