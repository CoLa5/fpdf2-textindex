"""Test of fpdf adaption."""

import logging
import pathlib

import fpdf
import pytest

from fpdf2_textindex import FPDF
from fpdf2_textindex import TextIndexEntry
from test.conftest import DATA
from test.conftest import assert_pdf_equal
from test.conftest import create_figure_test_cases


@pytest.mark.parametrize(
    ("text", "parsed_text"),
    [
        (
            "Single-tap iPad or double-tapped ipad",
            "[Single-tap](#idx0) [iPad](#idx1) or [double-tapped](#idx2) ipad",
        )
    ],
)
def test_reload_concordance_file(
    text: str,
    parsed_text: str,
) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", style="", size=12)
    pdf.add_page()

    # Without concordance file
    lines = pdf.multi_cell(
        w=pdf.epw,
        h=pdf.font_size,
        text=text,
        dry_run=True,
        markdown=True,
        output=fpdf.enums.MethodReturnValue.LINES,
    )
    new_text = "\n".join(lines)
    assert new_text == text

    # With concordance file
    pdf.CONCORDANCE_FILE = DATA / "concordance.tsv"
    lines = pdf.multi_cell(
        w=pdf.epw,
        h=pdf.font_size,
        text=text,
        dry_run=True,
        markdown=True,
        output=fpdf.enums.MethodReturnValue.LINES,
    )
    new_text = "\n".join(lines)
    assert new_text == parsed_text

    # Without concordance file
    pdf.CONCORDANCE_FILE = None
    lines = pdf.multi_cell(
        w=pdf.epw,
        h=pdf.font_size,
        text=text,
        dry_run=True,
        markdown=True,
        output=fpdf.enums.MethodReturnValue.LINES,
    )
    new_text = "\n".join(lines)
    assert new_text == text


@pytest.mark.parametrize("font_set", [False, True])
def test_last_gstate_leaking_into_index(
    font_set: bool, tmp_path: pathlib.Path
) -> None:
    def render_index_simple(
        pdf: FPDF,
        entries: list[TextIndexEntry],
    ) -> None:
        assert pdf.current_font_is_set_on_page == font_set
        assert pdf.font_family == "helvetica"
        assert pdf.font_size_pt == 12
        assert pdf.font_style == ""

    pdf = FPDF()
    pdf.set_font("Helvetica", style="", size=12)

    pdf.add_page()
    if font_set:
        pdf.cell(
            w=pdf.epw,
            h=pdf.font_size,
            text="Index Title",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    pdf.insert_index_placeholder(render_index_simple, allow_extra_pages=True)

    pdf.add_page()
    pdf.set_font("Courier", style="B", size=16)
    pdf.cell(
        w=pdf.epw,
        h=pdf.font_size,
        text="Trailing Page",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    # Not comparing, just triggering assert functions in `render_index_simple`
    pdf.output(tmp_path / "textindex_last_gstate_leaking_into_toc.pdf")


@pytest.mark.parametrize(
    ("msg", "text", "parsed_text", "entries", "warn_msg"),
    list(create_figure_test_cases()),
)
def test_multi_cell(
    caplog: pytest.LogCaptureFixture,
    msg: str,
    text: str,
    parsed_text: str,
    entries: list[TextIndexEntry],
    warn_msg: str | None,
) -> None:
    doc = FPDF()
    doc.set_font("Helvetica", size=12)
    doc.add_page()

    with caplog.at_level(logging.WARNING):
        doc.multi_cell(
            w=0,
            text=text,
            markdown=True,
            new_x=fpdf.XPos.LEFT,
            new_y=fpdf.YPos.NEXT,
        )

    assert len(doc.index_entries) == len(entries), msg
    for entry in entries:
        parsed_entry = doc.index_entry_at_label_path(entry.label_path)
        assert isinstance(parsed_entry, TextIndexEntry), (entry, msg)
        assert parsed_entry.label == entry.label, (entry, msg)
        assert parsed_entry.label_path == entry.label_path, (entry, msg)
        assert parsed_entry.references == entry.references, (entry, msg)
        assert parsed_entry.cross_references == entry.cross_references, (
            entry,
            msg,
        )
        assert parsed_entry.sort_key == entry.sort_key, (entry, msg)

    cap_warn_msgs = [
        r.message for r in caplog.records if r.levelno == logging.WARNING
    ]
    if cap_warn_msgs or warn_msg:
        assert warn_msg in cap_warn_msgs, (msg, warn_msg, cap_warn_msgs)


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
