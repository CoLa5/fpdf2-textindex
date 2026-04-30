"""Test of :py:mod:`fpdf2`-monkey patch."""

import sys


def test_monkeypatch() -> None:
    # Clean former imports
    for name in list(sys.modules):
        if name.startswith("fpdf"):
            sys.modules.pop(name, None)

    # Import original module
    import fpdf

    assert not hasattr(fpdf.FPDF, "__PATCHED__")
    assert not hasattr(fpdf.fpdf.FPDF, "__PATCHED__")
    assert not hasattr(fpdf.fpdf.MultiLineBreak, "__PATCHED__")

    # Apply patch
    import fpdf2_textindex  # noqa: F401

    assert hasattr(fpdf.FPDF, "__PATCHED__")
    assert fpdf.FPDF.__PATCHED__

    assert hasattr(fpdf.fpdf.FPDF, "__PATCHED__")
    assert fpdf.fpdf.FPDF.__PATCHED__

    assert hasattr(fpdf.fpdf.MultiLineBreak, "__PATCHED__")
    assert fpdf.fpdf.MultiLineBreak.__PATCHED__
