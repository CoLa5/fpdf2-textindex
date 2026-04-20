"""Test of fpdf adaption."""

import pathlib

import fpdf

from fpdf2_textindex.pdf import FPDF
from test.conftest import DATA
from test.conftest import assert_pdf_equal
from test.conftest import create_figure_test_cases


def test_render_function_not_setting_link(tmp_path: pathlib.Path) -> None:
    msg_texts = (tc[:2] for tc in create_figure_test_cases())

    doc = FPDF()
    doc.MARKDOWN_LINK_COLOR = "#0000FF"
    doc.MARKDOWN_LINK_UNDERLINE = False
    doc.STRICT_INDEX_MODE = False
    doc.r_margin = 2 / 3 * doc.w - doc.r_margin
    doc.set_font("Helvetica", size=12)

    # Insert index doing nothing
    doc.add_page(label_style="R", label_start=1)
    doc.multi_cell(
        w=0,
        text="Empty Index",
        new_x=fpdf.XPos.LEFT,
        new_y=fpdf.YPos.NEXT,
    )
    doc.insert_index_placeholder(lambda pdf, entries: None)

    # Insert one example per page
    doc.set_page_label(label_style="D", label_start=1)
    for i, (msg, text) in enumerate(msg_texts):
        if i > 0:
            doc.add_page()
        doc.multi_cell(
            w=0,
            text=msg,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )
        doc.ln()
        doc.multi_cell(
            w=0,
            text=text,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )
        doc.ln()
        doc.multi_cell(
            w=0,
            text=text,
            markdown=True,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )

    assert_pdf_equal(doc, DATA / "textindex_not_setting_link.pdf", tmp_path)
