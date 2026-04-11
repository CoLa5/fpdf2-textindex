"""Test of Text Index."""

from collections.abc import Callable, Iterator
import pathlib
from typing import Any

import fpdf
import pytest

from fpdf2_textindex.pdf import FPDF
from fpdf2_textindex.renderer import TextIndexRenderer
from fpdf2_textindex.renderer import collect_index_links
from test.conftest import DATA
from test.conftest import assert_pdf_equal
from test.conftest import create_figure_test_cases


def create_ref_test_cases() -> Iterator[tuple[str, str, list[str]]]:
    yield (
        "entry ref",
        "[entry ref]{^ref-a}",
        [
            "ref-a, [1](#idx0t)",
        ],
    )
    yield (
        "entry - subentry ref",
        "[entry - subentry ref]{^ref-b>ref-c}",
        [
            "ref-b",
            "ref-c, [1](#idx0t)",
        ],
    )
    yield (
        "entry - sub-subentry ref",
        "[entry - sub-subentry ref]{^ref-d>ref-e>ref-f}",
        [
            "ref-d",
            "ref-e",
            "ref-f, [1](#idx0t)",
        ],
    )
    yield (
        "entry ref - subentry ref",
        "[entry ref]{^ref-g} [subentry ref]{^ref-g>ref-h}",
        [
            "ref-g, [1](#idx0t)",
            "ref-h, [1](#idx1t)",
        ],
    )
    yield (
        "entry ref - sub-subentry ref",
        "[entry ref]{^ref-i} [sub-subentry ref]{^ref-i>ref-j>ref-k}",
        [
            "ref-i, [1](#idx0t)",
            "ref-j",
            "ref-k, [1](#idx1t)",
        ],
    )
    yield (
        "entry ref - subentry ref - sub-subentry ref",
        "[entry ref]{^ref-l} [subentry ref]{^ref-l>ref-m} "
        "[sub-subentry ref]{^ref-l>ref-m>ref-n}",
        [
            "ref-l, [1](#idx0t)",
            "ref-m, [1](#idx1t)",
            "ref-n, [1](#idx2t)",
        ],
    )
    yield (
        "entry multi ref",
        "[entry ref 0]{^ref-o}\f[entry ref 1]{^ref-o}",
        [
            "ref-o, [1](#idx0t), [2](#idx1t)",
        ],
    )
    yield (
        "entry - subentry multi ref",
        "[entry - subentry ref 0]{^ref-q>ref-r}\f\f"
        "[entry - subentry ref 1]{^ref-q>ref-r}",
        [
            "ref-q",
            "ref-r, [1](#idx0t), [3](#idx1t)",
        ],
    )
    yield (
        "entry - sub-subentry multi ref",
        "[entry - sub-subentry ref 0]{^ref-s>ref-t>ref-u}\f"
        "[entry - sub-subentry ref 1]{^ref-s>ref-t>ref-u}\f\f"
        "[entry - sub-subentry ref 2]{^ref-s>ref-t>ref-u}\f",
        [
            "ref-s",
            "ref-t",
            "ref-u, [1](#idx0t), [2](#idx1t), [4](#idx2t)",
        ],
    )
    yield (
        "entry multi page ref",
        "[entry ref 0]{^ref-v}\f[entry ref 1]{^ref-v/}",
        [
            "ref-v, [1](#idx0t)-[2](#idx1t)",
        ],
    )


@pytest.mark.parametrize(
    ["msg", "text", "prepared_texts"],
    list(create_ref_test_cases()),
)
def test_renderer_prepare_ref(
    msg: str, text: str, prepared_texts: list[str]
) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)

    text_p = text.split("\f")
    for tp in text_p:
        pdf.add_page()
        pdf.multi_cell(w=0, text=tp, markdown=True)

    renderer = TextIndexRenderer(run_in_style=False)
    renderer._link_locations = collect_index_links(pdf)
    new_texts = [
        t
        for entry in pdf.index_entries
        for _, t in renderer._prepare_entry(pdf, entry, 3)
        if entry.depth == 1
    ]

    for new_text, prepared_text in zip(new_texts, prepared_texts, strict=True):
        kw = {}
        for i in range(4):
            if i >= len(pdf.index_entries):
                break
            if f"{{ent_id{i:d}:d}}" in prepared_text:
                kw[f"ent_id{i:d}"] = pdf.index_entries[i].id
        prepared_text = prepared_text.format(**kw)
        assert new_text == prepared_text, (
            msg,
            pdf.index_entries,
            "\n".join(new_texts),
        )


def create_see_test_cases() -> Iterator[tuple[str, str, list[str]]]:
    yield (
        "entry see-ref",
        "ref-x{^}\f[entry see-ref]{^see-a|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-a. __See__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry - subentry see-ref",
        "ref-x{^}\f[entry - subentry see-ref]{^see-b>see-c|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-b",
            "see-c (__see__ [ref-x](#ent{ent_id0:d}))",
        ],
    )
    yield (
        "entry - sub-subentry see-ref",
        "ref-x{^}\f[entry - sub-subentry see-ref]{^see-d>see-e>see-f|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-d",
            "see-e",
            "see-f (__see__ [ref-x](#ent{ent_id0:d}))",
        ],
    )
    yield (
        "entry see-ref - subentry see-ref",
        "ref-x{^}\f[entry see-ref]{^see-g|ref-x} "
        "[subentry see-ref]{^see-g>see-h|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-g. __See__ [ref-x](#ent{ent_id0:d})",
            "see-h (__see__ [ref-x](#ent{ent_id0:d}))",
        ],
    )
    yield (
        "entry see-ref - sub-subentry see-ref",
        "ref-x{^}\f[entry see-ref]{^see-i|ref-x} "
        "[sub-subentry see-ref]{^see-i>see-j>see-k|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-i. __See__ [ref-x](#ent{ent_id0:d})",
            "see-j",
            "see-k (__see__ [ref-x](#ent{ent_id0:d}))",
        ],
    )
    yield (
        "entry see-ref - subentry see-ref - sub-subentry see-ref",
        "ref-x{^}\f"
        "[entry see-ref]{^see-l|ref-x} "
        "[subentry see-ref]{^see-l>see-m|ref-x} "
        "[sub-subentry see-ref]{^see-l>see-m>see-n|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-l. __See__ [ref-x](#ent{ent_id0:d})",
            "see-m (__see__ [ref-x](#ent{ent_id0:d}))",
            "see-n (__see__ [ref-x](#ent{ent_id0:d}))",
        ],
    )
    yield (
        "entry multi see-ref",
        "ref-x{^}\fref-y{^}\f"
        # first y and then x to test alphabetical order
        "[entry see-ref 0]{^see-o|ref-y}\f"
        "[entry see-ref 1]{^see-o|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "see-o. __See__ [ref-x](#ent{ent_id0:d}); [ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - subentry multi see-ref",
        "ref-x{^}\fref-y{^}\f"
        # first y and then x to test alphabetical order
        "[entry - subentry see-ref 0]{^see-p>see-q|ref-y}\f\f"
        "[entry - subentry see-ref 1]{^see-p>see-q|ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "see-p",
            "see-q (__see__ "
            "[ref-x](#ent{ent_id0:d}); "
            "[ref-y](#ent{ent_id1:d}))",
        ],
    )
    yield (
        "entry - sub-subentry multi see-ref",
        "ref-x{^}\fref-y{^}\fref-z{^}\f"
        # first z, y and then x to test alphabetical order
        "[entry - sub-subentry see-ref 0]{^see-r>see-s>see-t|ref-z}\f"
        "[entry - sub-subentry see-ref 1]{^see-r>see-s>see-t|ref-x}\f"
        "[entry - sub-subentry see-ref 2]{^see-r>see-s>see-t|ref-y}\f",
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "ref-z, [3](#idx2t)",
            "see-r",
            "see-s",
            "see-t (__see__ "
            "[ref-x](#ent{ent_id0:d}); "
            "[ref-y](#ent{ent_id1:d}); "
            "[ref-z](#ent{ent_id2:d}))",
        ],
    )
    yield (
        "entry multi see-subentry ref",
        "ref-y{^ref-x>}\f[entry see-ref 0]{^see-u|ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-u. __See__ [ref-x: ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - subentry multi see-subentry ref",
        "ref-y{^ref-x>}\f"
        "[entry - subentry see-ref 0]{^see-v>see-w|ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-v",
            "see-w (__see__ [ref-x: ref-y](#ent{ent_id1:d}))",
        ],
    )
    yield (
        "entry - sub-subentry multi see-sub-subentry ref",
        "ref-z{^ref-x>ref-y>}\f"
        "[entry - sub-subentry see-ref 0]"
        "{^see-x>see-y>see-z|ref-x>ref-y>ref-z}",
        [
            "ref-x",
            "ref-y",
            "ref-z, [1](#idx0t)",
            "see-x",
            "see-y",
            "see-z (__see__ [ref-x: ref-y: ref-z](#ent{ent_id2:d}))",
        ],
    )
    yield (
        "entry - subentry see-under ref",
        "ref-y{^ref-x>}\f"
        "[entry - subentry see-ref 0]{^see-0>ref-y|ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-0",
            "ref-y (__see under__ [ref-x](#ent{ent_id1:d}))",
        ],
    )


@pytest.mark.parametrize(
    ["msg", "text", "prepared_texts"],
    list(create_see_test_cases()),
)
def test_renderer_prepare_see(
    msg: str, text: str, prepared_texts: list[str]
) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)

    text_p = text.split("\f")
    for tp in text_p:
        pdf.add_page()
        pdf.multi_cell(w=0, text=tp, markdown=True)

    renderer = TextIndexRenderer(run_in_style=False)
    renderer._link_locations = collect_index_links(pdf)
    new_texts = [
        t
        for entry in pdf.index_entries
        for _, t in renderer._prepare_entry(pdf, entry, 3)
        if entry.depth == 1
    ]

    for new_text, prepared_text in zip(new_texts, prepared_texts, strict=True):
        kw = {}
        for i in range(4):
            if i >= len(pdf.index_entries):
                break
            if f"{{ent_id{i:d}:d}}" in prepared_text:
                kw[f"ent_id{i:d}"] = pdf.index_entries[i].id
        prepared_text = prepared_text.format(**kw)
        assert new_text == prepared_text, (
            msg,
            pdf.index_entries,
            "\n".join(new_texts),
        )


def create_see_also_test_cases() -> Iterator[tuple[str, str, list[str]]]:
    yield (
        "entry also-ref",
        "ref-x{^}\f[entry also-ref]{^see-also-a|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-also-a, [2](#idx1t). __See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry - subentry also-ref",
        "ref-x{^}\f[entry - subentry also-ref]{^see-also-b>see-also-c|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-also-b",
            "see-also-c, [2](#idx1t). __See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry - sub-subentry also-ref",
        "ref-x{^}\f"
        "[entry - sub-subentry also-ref]{^see-also-d>see-also-e>see-also-f|+ref-x}",  # noqa: E501
        [
            "ref-x, [1](#idx0t)",
            "see-also-d",
            "see-also-e",
            "see-also-f, [2](#idx1t). __See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry also-ref - subentry also-ref",
        "ref-x{^}\f"
        "[entry also-ref]{^see-also-g|+ref-x}\f"
        "[subentry also-ref]{^see-also-g>see-also-h|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-also-g, [2](#idx1t)",
            "see-also-h, [3](#idx2t). __See also__ [ref-x](#ent{ent_id0:d})",
            "__See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry also-ref - sub-subentry also-ref",
        "ref-x{^}\f"
        "[entry also-ref]{^see-also-i|+ref-x}\f"
        "[sub-subentry also-ref]{^see-also-i>see-also-j>see-also-k|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-also-i, [2](#idx1t)",
            "see-also-j",
            "see-also-k, [3](#idx2t). __See also__ [ref-x](#ent{ent_id0:d})",
            "__See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry also-ref - subentry also-ref - sub-subentry also-ref",
        "ref-x{^}\f"
        "[entry also-ref]{^see-also-l|+ref-x}\f"
        "[subentry also-ref]{^see-also-l>see-also-m|+ref-x}\f"
        "[sub-subentry also-ref]{^see-also-l>see-also-m>see-also-n|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "see-also-l, [2](#idx1t)",
            "see-also-m, [3](#idx2t)",
            "see-also-n, [4](#idx3t). __See also__ [ref-x](#ent{ent_id0:d})",
            "__See also__ [ref-x](#ent{ent_id0:d})",
            "__See also__ [ref-x](#ent{ent_id0:d})",
        ],
    )
    yield (
        "entry multi also-ref",
        "ref-x{^}\fref-y{^}\f"
        # first y and then x to test alphabetical order
        "[entry also-ref 0]{^see-also-o|+ref-y}\f"
        "[entry also-ref 1]{^see-also-o|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "see-also-o, [3](#idx2t), [4](#idx3t). "
            "__See also__ [ref-x](#ent{ent_id0:d}); "
            "[ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - subentry multi also-ref",
        "ref-x{^}\fref-y{^}\f"
        # first y and then x to test alphabetical order
        "[entry - subentry also-ref 0]{^see-also-p>see-also-q|+ref-y}\f\f"
        "[entry - subentry also-ref 1]{^see-also-p>see-also-q|+ref-x}",
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "see-also-p",
            "see-also-q, [3](#idx2t), [5](#idx3t). __See also__ "
            "[ref-x](#ent{ent_id0:d}); "
            "[ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - sub-subentry multi also-ref",
        "ref-x{^}\fref-y{^}\fref-z{^}\f"
        # first z, y and then x to test alphabetical order
        "[entry - sub-subentry also-ref 0]{^see-also-r>see-also-s>see-also-t|+ref-z}\f"  # noqa: E501
        "[entry - sub-subentry also-ref 1]{^see-also-r>see-also-s>see-also-t|+ref-x}\f"  # noqa: E501
        "[entry - sub-subentry also-ref 2]{^see-also-r>see-also-s>see-also-t|+ref-y}\f",  # noqa: E501
        [
            "ref-x, [1](#idx0t)",
            "ref-y, [2](#idx1t)",
            "ref-z, [3](#idx2t)",
            "see-also-r",
            "see-also-s",
            "see-also-t, [4](#idx3t), [5](#idx4t), [6](#idx5t). "
            "__See also__ [ref-x](#ent{ent_id0:d}); "
            "[ref-y](#ent{ent_id1:d}); "
            "[ref-z](#ent{ent_id2:d})",
        ],
    )
    yield (
        "entry multi also-subentry ref",
        "ref-y{^ref-x>}\f[entry also-ref 0]{^see-also-u|+ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-also-u, [2](#idx1t). "
            "__See also__ [ref-x: ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - subentry multi also-subentry ref",
        "ref-y{^ref-x>}\f"
        "[entry - subentry also-ref 0]{^see-also-v>see-also-w|+ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-also-v",
            "see-also-w, [2](#idx1t). "
            "__See also__ [ref-x: ref-y](#ent{ent_id1:d})",
        ],
    )
    yield (
        "entry - sub-subentry multi also-sub-subentry ref",
        "ref-z{^ref-x>ref-y>}\f"
        "[entry - sub-subentry also-ref 0]{^see-also-x>see-also-y>see-also-z|+ref-x>ref-y>ref-z}",  # noqa: E501
        [
            "ref-x",
            "ref-y",
            "ref-z, [1](#idx0t)",
            "see-also-x",
            "see-also-y",
            "see-also-z, [2](#idx1t). "
            "__See also__ [ref-x: ref-y: ref-z](#ent{ent_id2:d})",
        ],
    )
    yield (
        "entry - subentry also-under ref",
        "ref-y{^ref-x>}\f"
        "[entry - subentry also-ref 0]{^see-also-0>ref-y|+ref-x>ref-y}",
        [
            "ref-x",
            "ref-y, [1](#idx0t)",
            "see-also-0",
            "ref-y, [2](#idx1t). __See also under__ [ref-x](#ent{ent_id1:d})",
        ],
    )


@pytest.mark.parametrize(
    ["msg", "text", "prepared_texts"],
    list(create_see_also_test_cases()),
)
def test_renderer_prepare_see_also(
    msg: str, text: str, prepared_texts: list[str]
) -> None:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=12)

    text_p = text.split("\f")
    for tp in text_p:
        pdf.add_page()
        pdf.multi_cell(w=0, text=tp, markdown=True)

    renderer = TextIndexRenderer(run_in_style=False)
    renderer._link_locations = collect_index_links(pdf)
    new_texts = [
        t
        for entry in pdf.index_entries
        for _, t in renderer._prepare_entry(pdf, entry, 3)
        if entry.depth == 1
    ]

    for new_text, prepared_text in zip(new_texts, prepared_texts, strict=True):
        kw = {}
        for i in range(4):
            if i >= len(pdf.index_entries):
                break
            if f"{{ent_id{i:d}:d}}" in prepared_text:
                kw[f"ent_id{i:d}"] = pdf.index_entries[i].id
        prepared_text = prepared_text.format(**kw)
        assert new_text == prepared_text, (
            msg,
            pdf.index_entries,
            "\n".join(new_texts),
        )


kwargs = {"line_spacing": [None]}


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"level_indent": 15.0},
        {"line_spacing": 1.2},
        {"outline_level": 0},
        {"max_outline_level": 0, "outline_level": 0},
        {"run_in_style": False},
        {"show_header": True},
        {"sort_emph_first": True},
        {
            "text_styles": [
                fpdf.TextStyle(
                    font_style="B",
                    color="#ff0000",
                    l_margin=11.0,  # 10 is r_margin
                    t_margin=0.5 * 12 / 72 * 25.4,
                ),
                fpdf.TextStyle(),
            ],
            "show_header": True,
        },
    ],
)
def test_renderer_arguments(
    kw: dict[str, Any],
    tmp_path: pathlib.Path,
) -> None:
    msg_texts = (tc[:2] for tc in create_figure_test_cases())

    doc = FPDF()
    doc.MARKDOWN_LINK_COLOR = "#0000FF"
    doc.MARKDOWN_LINK_UNDERLINE = False
    doc.r_margin = 2 / 3 * doc.w - doc.r_margin
    doc.set_font("Helvetica", size=12)

    # Insert Index
    doc.add_page(label_style="R", label_start=1)
    index = TextIndexRenderer(**kw)
    doc.insert_index_placeholder(
        index.render_text_index,
        allow_extra_pages=True,
    )

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

    key = next(iter(kw.keys())) if kw else "plain"
    assert_pdf_equal(doc, DATA / f"textindex_{key:s}.pdf", tmp_path)


@pytest.mark.parametrize(
    "kw",
    [
        {"allow_extra_pages": True},
        {"pages": 2},
    ],
)
def test_index_placeholder_arguments(
    kw: dict[str, Any],
    tmp_path: pathlib.Path,
) -> None:
    msg_texts = (tc[:2] for tc in create_figure_test_cases())

    doc = FPDF()
    doc.MARKDOWN_LINK_COLOR = "#0000FF"
    doc.MARKDOWN_LINK_UNDERLINE = False
    doc.r_margin = 2 / 3 * doc.w - doc.r_margin
    doc.set_font("Helvetica", size=12)

    # Insert Index
    doc.add_page(label_style="R", label_start=1)
    index = TextIndexRenderer(
        show_header=True
    )  # To get more than a single page
    doc.insert_index_placeholder(
        index.render_text_index,
        **kw,
    )

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

    key = next(iter(kw.keys())) if kw else "plain"
    assert_pdf_equal(doc, DATA / f"textindex_{key:s}.pdf", tmp_path)


@pytest.mark.parametrize(
    ["key", "create_fn"],
    [
        ("ref", create_ref_test_cases),
        ("see", create_see_test_cases),
        ("see also", create_see_also_test_cases),
    ],
)
def test_renderer_references(
    key: str,
    create_fn: Callable[[], Iterator[tuple[str, str, list[str]]]],
    tmp_path: pathlib.Path,
) -> None:
    msg_texts = (tc[:2] for tc in create_fn())

    doc = FPDF()
    doc.MARKDOWN_LINK_COLOR = "#0000FF"
    doc.MARKDOWN_LINK_UNDERLINE = False
    doc.r_margin = 2 / 3 * doc.w - doc.r_margin
    doc.set_font("Helvetica", size=12)

    # Insert Index
    doc.add_page(label_style="R", label_start=1)
    index = TextIndexRenderer(show_header=True)
    doc.insert_index_placeholder(
        index.render_text_index,
    )

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

    assert_pdf_equal(doc, DATA / f"textindex_{key:s}.pdf", tmp_path)
