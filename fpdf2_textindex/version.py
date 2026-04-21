"""Version."""

import importlib.metadata
import pathlib
from typing import Final

FPDF2_TEXTINDEX_VERSION: Final[str] = importlib.metadata.version(
    pathlib.Path(__file__).parent.name
)
