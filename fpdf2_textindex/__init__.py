"""
[![License](https://img.shields.io/badge/license-GPLv3-blue.svg?style=flat)](https://www.gnu.org/licenses/gpl-3.0)

.. include:: ../README.md
   :start-line: 8

The module gives direct access to some classes defined in submodules:

* :py:class:`fpdf2_textindex.Alias`
* :py:class:`fpdf2_textindex.CrossReference`
* :py:class:`fpdf2_textindex.CrossReferenceType`
* :py:class:`fpdf2_textindex.FPDF`
* :py:class:`fpdf2_textindex.LinkLocation`
* :py:class:`fpdf2_textindex.Reference`
* :py:class:`fpdf2_textindex.TextIndexEntry`
* :py:class:`fpdf2_textindex.TextIndexRenderer`
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

__all__ = (  # noqa: RUF022
    "Alias",
    "CrossReference",
    "CrossReferenceType",
    "FPDF",
    "LinkLocation",
    "Reference",
    "TextIndexEntry",
    "TextIndexRenderer",
    "__license__",
    "__version__",
)
